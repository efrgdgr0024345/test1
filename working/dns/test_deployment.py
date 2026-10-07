import unittest
from unittest.mock import patch
import dns.flags
import dns.message
import dns.rcode
import dns.rrset
from smoke import https_url, validate_answer
from verify import redirect_is_https, reject_http

class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.query = dns.message.make_query('test.example.', 'A')
        self.answer = dns.message.make_response(self.query)

    def test_positive_answer(self):
        self.answer.answer.append(dns.rrset.from_text('test.example.', 20, 'IN', 'A', '192.0.2.1'))
        self.assertEqual(validate_answer(self.query, self.answer.to_wire()), ['192.0.2.1'])

    def test_servfail_is_not_success(self):
        self.answer.set_rcode(dns.rcode.SERVFAIL)
        with self.assertRaises(ValueError):
            validate_answer(self.query, self.answer.to_wire())

    def test_nxdomain_is_not_positive_success(self):
        self.answer.set_rcode(dns.rcode.NXDOMAIN)
        with self.assertRaises(ValueError):
            validate_answer(self.query, self.answer.to_wire())

    def test_empty_response_fails(self):
        with self.assertRaises(ValueError):
            validate_answer(self.query, self.answer.to_wire())

    def test_wrong_question_fails(self):
        wrong = dns.message.make_query('other.example.', 'A')
        with self.assertRaises(ValueError):
            validate_answer(wrong, self.answer.to_wire())

    def test_truncated_response_fails(self):
        self.answer.flags |= dns.flags.TC
        with self.assertRaises(ValueError):
            validate_answer(self.query, self.answer.to_wire())

    def test_plaintext_or_credentials_are_rejected(self):
        for url in ['http://example.com/dns', 'https://user@example.com/dns',
                    'https://example.com:80/dns', 'https://example.com/dns#fragment']:
            with self.assertRaises(ValueError):
                https_url(url)

    def test_redirect_cannot_change_host_path_query_or_scheme(self):
        original = 'https://unit.example/s/test/working/dns?dns=AAAA'
        self.assertTrue(redirect_is_https(original, original))
        for target in ['https://other.example/s/test/working/dns?dns=AAAA',
                       'http://unit.example/s/test/working/dns?dns=AAAA',
                       'https://unit.example/login', None,
                       'https://unit.example/s/test/working/dns?dns=BBBB']:
            self.assertFalse(redirect_is_https(original, target))

    def test_http_probe_never_sends_session_token(self):
        with patch('verify.http.client.HTTPConnection') as factory:
            conn = factory.return_value
            response = conn.getresponse.return_value
            response.status = 308
            response.getheader.side_effect = lambda key, default=None: (
                'https://unit.example/s/invalid-transport-probe/working/dns'
                if key == 'Location' else 'text/html')
            reject_http('https://unit.example/s/SECRET-CAPABILITY/working/dns')
            sent_path = conn.request.call_args.args[1]
            self.assertNotIn('SECRET-CAPABILITY', sent_path)
            self.assertIn('invalid-transport-probe', sent_path)

    def test_http_timeout_is_not_proof_of_https_only(self):
        with patch('verify.http.client.HTTPConnection') as factory:
            factory.return_value.request.side_effect = TimeoutError()
            with self.assertRaises(TimeoutError):
                reject_http('https://unit.example/s/SECRET/working/dns')

if __name__ == '__main__':
    unittest.main(verbosity=2)
