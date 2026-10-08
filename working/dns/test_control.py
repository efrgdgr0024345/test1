"""No credentials or real Codespaces required. Network behavior is tested separately."""
import copy
import json
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parent / 'control'))
import controller
import remote
from lease import remaining
from protocol import ControlError, REPO, TAG, select, seal, tagged_deadline, unseal, validate
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.exceptions import InvalidTag


def item(name='test-space', state='Available', display='Black Cat DNS'):
    return {'name': name, 'state': state, 'display_name': display,
            'repository': {'full_name': REPO}, 'owner': {'login': REPO.split('/')[0]}}


def session(now=1000):
    base = 'https://test-space-8080.app.github.dev'
    dash = base + '/s/' + 'a' * 43 + '/'
    return {'dashboard': dash, 'doh': dash + 'working/dns', 'public_origin': base,
            'expires_at_epoch': int(now) + 3600, 'code_commit': 'a' * 40,
            'request_id': 'b' * 32, 'managed_by_chat': True}


class ControlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        cls.pem = cls.private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        cls.pub = cls.private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()

    def command(self, op='start'):
        now = int(time.time())
        return {'version': 2, 'operation': op, 'request_id': 'b'*32, 'lifetime_seconds': 3600,
                'issued_at': now, 'valid_until': now+1800, 'reply_public_key': self.pub}

    def test_valid_command(self):
        self.assertEqual(validate(self.command())['operation'], 'start')

    def test_command_rejects_extra_fields(self):
        c=self.command();c['shell']='rm -rf /'
        with self.assertRaises(ControlError): validate(c)

    def test_expired_request_cannot_replay(self):
        c=self.command();c['issued_at']-=3600;c['valid_until']-=3600
        with self.assertRaises(ControlError): validate(c)

    def test_duration_must_be_one_two_or_three_hours(self):
        for value in (True, '3600', 60, 14400, -1):
            c=self.command();c['lifetime_seconds']=value
            with self.assertRaises(ControlError): validate(c)

    def test_codespace_name_not_shell_input(self):
        for value in ('-x', 'name; echo bad', 'https://github.com', 'a/b'):
            c=self.command();c['codespace']=value
            with self.assertRaises(ControlError): validate(c)

    def test_invalid_operation(self):
        with self.assertRaises(ControlError): validate(self.command('delete'))

    def test_future_request_rejected(self):
        c=self.command();c['issued_at']+=600;c['valid_until']+=600
        with self.assertRaises(ControlError): validate(c)

    def test_reply_has_no_plaintext_capability(self):
        data=session(); enc=seal(data,self.pub,'b'*32)
        self.assertNotIn(data['doh'],json.dumps(enc))
        self.assertEqual(unseal(enc,self.pem,'b'*32),data)

    def test_wrong_request_binding_rejected(self):
        enc=seal(session(),self.pub,'b'*32)
        with self.assertRaises(ControlError):unseal(enc,self.pem,'c'*32)

    def test_ciphertext_tampering_rejected(self):
        import base64
        enc=seal(session(),self.pub,'b'*32)
        raw=bytearray(base64.b64decode(enc['ciphertext']));raw[0]^=1
        enc['ciphertext']=base64.b64encode(raw).decode()
        with self.assertRaises(InvalidTag):unseal(enc,self.pem,'b'*32)

    def test_relabelled_request_breaks_oaep(self):
        enc=seal(session(),self.pub,'b'*32);enc['request_id']='c'*32
        with self.assertRaises(ValueError):unseal(enc,self.pem,'c'*32)

    def test_weak_reply_key_is_rejected(self):
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        c=self.command();c['reply_public_key']=key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        with self.assertRaises(ControlError):validate(c)

    def test_private_key_is_not_a_public_reply_key(self):
        c=self.command();c['reply_public_key']=self.pem.decode()
        with self.assertRaises(ControlError):validate(c)

    def test_duplicate_codespaces_are_not_guessed(self):
        with self.assertRaises(ControlError):select([item(),item('other')])

    def test_duplicate_managed_codespaces_are_not_guessed(self):
        with self.assertRaises(ControlError):select([item(display=TAG+'1799999999'),item('other',display=TAG+'1799999998')])

    def test_explicit_codespace_selection(self):
        self.assertEqual(select([item(),item('other')],'other')['name'],'other')

    def test_other_repository_is_not_adopted(self):
        x=item();x['repository']['full_name']='someone/else'
        self.assertIsNone(select([x]))

    def test_managed_codespace_preferred_without_deleting_old(self):
        managed=item('managed',display=TAG+'1799999999')
        self.assertEqual(select([item(),managed]),managed)

    def test_missing_secret_fails_before_network(self):
        with self.assertRaisesRegex(ControlError,'MISSING_BLACKCAT_CODESPACES_PAT'):
            controller.Cloud('')

    def test_session_validation(self):
        self.assertEqual(controller.check_session(session(),'test-space',now=1000)['expires_at_epoch'],4600)

    def test_http_session_url_rejected(self):
        x=session();x['dashboard']=x['dashboard'].replace('https:','http:')
        with self.assertRaises(ControlError):controller.check_session(x,'test-space',now=1000)

    def test_wrong_host_rejected(self):
        with self.assertRaises(ControlError):controller.check_session(session(),'other-space',now=1000)

    def test_wrong_dns_path_rejected(self):
        x=session();x['doh']+='/other'
        with self.assertRaises(ControlError):controller.check_session(x,'test-space',now=1000)

    def test_expired_session_is_never_live(self):
        with self.assertRaises(ControlError):controller.check_session(session(),'test-space',now=5000)

    def test_fixed_deadline_does_not_extend_on_reboot(self):
        self.assertEqual(remaining({'expires_at_epoch':4600},1000),3600)
        self.assertEqual(remaining({'expires_at_epoch':4600},2000),2600)
        with self.assertRaises(ValueError):remaining({'expires_at_epoch':4600},4600)

    def test_invalid_lease_type_rejected(self):
        with self.assertRaises(ValueError):remaining({'expires_at_epoch':'4600'},1000)

    def test_status_does_not_start_stopped_machine(self):
        cloud=Mock();cloud.owned.return_value=[item(state='Shutdown')];cloud.get.return_value=item(state='Shutdown')
        self.assertEqual(controller.execute(cloud,self.command('status'))['state'],'STOPPED')
        cloud.api.assert_not_called();cloud.remote.assert_not_called()

    def test_repeated_start_preserves_live_session(self):
        cloud=Mock();cloud.owned.return_value=[item()];cloud.get.return_value=item();s=session(time.time())
        cloud.remote.return_value={'session':s,'ok':True}
        with patch('controller.acceptance',return_value=s):
            result=controller.execute(cloud,self.command())
        self.assertTrue(result['reused']);cloud.api.assert_not_called();cloud.visibility.assert_not_called()

    def test_replayed_restart_does_not_extend_session(self):
        cloud=Mock();cloud.owned.return_value=[item()];cloud.get.return_value=item();s=session(time.time())
        cloud.remote.return_value={'session':s,'ok':True}
        with patch('controller.acceptance',return_value=s):
            result=controller.execute(cloud,self.command('restart'))
        self.assertTrue(result['reused']);cloud.api.assert_not_called()

    def test_consumed_request_cannot_restart_ended_session(self):
        cloud=Mock();cloud.owned.return_value=[item()];cloud.get.return_value=item()
        cloud.remote.return_value={'session':None,'ok':True,'lease_request_id':'b'*32}
        with self.assertRaisesRegex(ControlError,'REQUEST_ALREADY_CONSUMED'):
            controller.execute(cloud,self.command('restart'))
        cloud.api.assert_not_called()

    def test_dirty_workspace_not_replaced(self):
        cloud=Mock();cloud.owned.return_value=[item()];cloud.get.return_value=item()
        cloud.remote.return_value={'ok':True,'session':None,'dirty':True}
        with self.assertRaisesRegex(ControlError,'WORKTREE_DIRTY'):
            controller.execute(cloud,self.command())
        cloud.api.assert_not_called();cloud.stop.assert_not_called()

    def test_plain_api_redirect_rejected(self):
        with self.assertRaises(ControlError):controller.NoRedirect().redirect_request(None,None,None,None,None,None)

    def test_remote_script_accepts_injected_json_not_shell(self):
        source=(Path(controller.HERE)/'remote.py').read_text()
        compile('CONTROL_REQUEST = '+repr({'operation':'inspect'})+'\n'+source,'remote-pipe','exec')

    def test_expiry_tag_is_strict(self):
        self.assertIsNone(tagged_deadline(item(display='Black Cat DNS')))
        self.assertIsNone(tagged_deadline(item(display=TAG+'1;rm')))
        self.assertEqual(tagged_deadline(item(display=TAG+'1799999999')),1799999999)

    def test_reaper_only_stops_expired_managed_instances(self):
        cloud=Mock();cloud.owned.return_value=[item('expired',display=TAG+'1700000000'),item('future',display=TAG+'1900000000'),item('legacy')]
        with patch('controller.time.time',return_value=1800000000):controller.reap(cloud)
        cloud.stop.assert_called_once_with('expired')

if __name__=='__main__':unittest.main(verbosity=2)
