"""End-to-end local TLS tests using the real server and controlled resolver replies.

These prove the test TLS service's behavior, not a public Codespace deployment.
"""
import datetime as dt
import http.client
import ipaddress
import json
from pathlib import Path
import ssl
import tempfile
import threading
import time
import unittest
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import dns.message
import dns.rcode
from server import Engine, TLSServer
from tests import P, answer

class ControlTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory(prefix='blackcat-tls-test-')
        root=Path(cls.folder.name)
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')])
        now=dt.datetime.now(dt.timezone.utc)
        cert=(x509.CertificateBuilder().subject_name(name).issuer_name(name)
              .public_key(key.public_key()).serial_number(x509.random_serial_number())
              .not_valid_before(now-dt.timedelta(minutes=5)).not_valid_after(now+dt.timedelta(days=1))
              .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),False)
              .sign(key,hashes.SHA256()))
        cp=root/'cert.pem';kp=root/'key.pem'
        cp.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        kp.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        cls.tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);cls.tls.minimum_version=ssl.TLSVersion.TLSv1_2
        cls.tls.load_cert_chain(cp,kp)
        cls.client=ssl.create_default_context(cafile=str(cp))
        cls.client.minimum_version=ssl.TLSVersion.TLSv1_2

    @classmethod
    def tearDownClass(cls):cls.folder.cleanup()

    def setUp(self):
        self.mode='match'
        def query(p,n,q,context=None):
            row=answer(n,q,p,variant=self.mode=='mismatch' and p.name=='three')
            if self.mode=='unavailable' and p.name=='three':row['error']='controlled timeout'
            return row
        self.engine=Engine(P,300,query=query)
        self.http=TLSServer(('127.0.0.1',0),self.engine,self.tls)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True)
        self.thread.start()

    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.engine.close();self.thread.join(2)

    def request(self,path,body=None,kind='application/dns-message',context=None):
        c=http.client.HTTPSConnection('127.0.0.1',self.http.server_port,timeout=3,context=context or self.client)
        try:
            c.request('POST' if body is not None else 'GET',path,body=body,headers={'Content-Type':kind})
            r=c.getresponse();return r.status,r.read()
        finally:c.close()

    def doh(self):
        q=dns.message.make_query('example.com.','A',want_dnssec=True)
        code,body=self.request(self.engine.prefix+'/working/dns',q.to_wire())
        self.assertEqual(code,200)
        a=dns.message.from_wire(body);self.assertTrue(q.is_response(a));return a

    def test_https_positive_dns_roundtrip(self):
        a=self.doh();self.assertEqual(a.rcode(),dns.rcode.NOERROR);self.assertTrue(a.answer)

    def test_tls_certificate_validation_not_bypassed(self):
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.request('/healthz',context=ssl.create_default_context())

    def test_plain_http_is_rejected_by_tls_listener(self):
        c=http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=3)
        try:
            with self.assertRaises((ConnectionResetError,ConnectionAbortedError,http.client.RemoteDisconnected)):
                c.request('GET','/healthz');c.getresponse()
        finally:c.close()

    def test_mismatch_blocks_and_https_report_is_available(self):
        self.mode='mismatch';a=self.doh()
        self.assertEqual(a.rcode(),dns.rcode.SERVFAIL);self.assertFalse(a.answer)
        code,raw=self.request(self.engine.prefix+'/api/check',json.dumps({'name':'example.com'}).encode(),'application/json')
        self.assertEqual(code,200);report=json.loads(raw)
        self.assertEqual(report['status'],'mismatch');self.assertFalse(report['allowed'])
        code,body=self.request(self.engine.prefix+'/api/reports/'+report['id'])
        self.assertEqual(code,200);self.assertEqual(json.loads(body)['id'],report['id'])

    def test_upstream_timeout_fails_closed(self):
        self.mode='unavailable';a=self.doh()
        self.assertEqual(a.rcode(),dns.rcode.SERVFAIL);self.assertFalse(a.answer)

    def test_wrong_capability_has_no_access(self):
        code,_=self.request('/s/not-the-session/api/check',b'{"name":"example.com"}','application/json')
        self.assertEqual(code,404)

    def test_expired_session_stops_serving(self):
        self.engine.expires=time.monotonic()-1
        code,_=self.request(self.engine.prefix+'/working/dns',dns.message.make_query('example.com','A').to_wire())
        self.assertEqual(code,410)

if __name__=='__main__':unittest.main(verbosity=2)
