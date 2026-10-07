import ssl
import unittest
from unittest.mock import patch
from upstream import PinnedHTTPS

class HTTP2Tests(unittest.TestCase):
    def test_bootstrap_ip_does_not_replace_verified_hostname(self):
        with patch('upstream.httpx.Client') as factory:
            client = factory.return_value
            client.send.return_value.http_version = 'HTTP/2'
            conn = PinnedHTTPS('resolver.example', '1.1.1.1', 443, ssl.create_default_context())
            conn.request('POST', '/dns-query', b'test', {'Connection': 'close'})
            settings = factory.call_args.kwargs
            self.assertTrue(settings['http2'])
            self.assertFalse(settings['http1'])
            self.assertFalse(settings['trust_env'])
            self.assertFalse(settings['follow_redirects'])
            sent = client.build_request.call_args
            self.assertEqual(sent.args[1], 'https://1.1.1.1/dns-query')
            self.assertEqual(sent.kwargs['headers']['Host'], 'resolver.example')
            self.assertEqual(sent.kwargs['extensions']['sni_hostname'], 'resolver.example')
            conn.close()

    def test_unverified_tls_is_forbidden(self):
        with self.assertRaises(ValueError):
            PinnedHTTPS('resolver.example', '1.1.1.1', 443, ssl._create_unverified_context())

    def test_plaintext_port_is_forbidden(self):
        with self.assertRaises(ValueError):
            PinnedHTTPS('resolver.example', '1.1.1.1', 80, ssl.create_default_context())

    def test_http_one_is_not_silently_accepted(self):
        with patch('upstream.httpx.Client') as factory:
            factory.return_value.send.return_value.http_version = 'HTTP/1.1'
            conn = PinnedHTTPS('resolver.example', '1.1.1.1', 443, ssl.create_default_context())
            try:
                with self.assertRaises(ValueError):
                    conn.request('POST', '/dns-query', b'test', {})
            finally:
                conn.close()

if __name__ == '__main__':
    unittest.main(verbosity=2)
