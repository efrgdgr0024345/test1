import unittest
from verify import redirect_is_https

class HTTPSUpgradeTests(unittest.TestCase):
    def test_measured_dashboard_slash_normalization(self):
        self.assertTrue(redirect_is_https('https://host/s/invalid-transport-probe/',
                                         'https://host/s/invalid-transport-probe'))

    def test_another_session_is_never_accepted(self):
        self.assertFalse(redirect_is_https('https://host/s/first/', 'https://host/s/second'))

    def test_dns_route_changes_are_never_accepted(self):
        self.assertFalse(redirect_is_https('https://host/s/token/working/dns/',
                                          'https://host/s/token/working/dns'))
        self.assertFalse(redirect_is_https('https://host/s/token/working/dns?dns=abc',
                                          'https://host/s/token/working/dns'))

    def test_no_cross_origin_or_plaintext_exception(self):
        for bad in ('http://host/s/token','https://evil/s/token','https://host:80/s/token',
                    'https://user@host/s/token','https://host/s/token#fragment',
                    'https://host/s/token?added=true'):
            self.assertFalse(redirect_is_https('https://host/s/token/',bad))

if __name__=='__main__':
    unittest.main(verbosity=2)
