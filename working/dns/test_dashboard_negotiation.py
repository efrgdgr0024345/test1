import unittest
from unittest.mock import MagicMock, patch
from email.message import Message
import smoke
import verify

PAGE = b'<title>Black Cat DNS Consensus</title><code id="endpoint"></code>'
NOTICE = b'<title>GitHub Codespaces</title>You are about to access a development port. Continue'

class DashboardNegotiationTests(unittest.TestCase):
    @patch('verify.request')
    def test_direct_dashboard(self, request):
        request.return_value=PAGE
        self.assertFalse(verify.dashboard_document('https://host/s/token/')['browser_first_visit_notice'])
        request.assert_called_once()

    @patch('verify.request')
    def test_notice_alone_is_never_success(self, request):
        request.side_effect=[NOTICE, NOTICE]
        with self.assertRaises(ValueError):
            verify.dashboard_document('https://host/s/token/')

    @patch('verify.request')
    def test_actual_dashboard_is_required_after_notice(self, request):
        request.side_effect=[NOTICE, PAGE]
        result=verify.dashboard_document('https://host/s/token/')
        self.assertTrue(result['dashboard_verified'])
        self.assertTrue(result['browser_first_visit_notice'])
        self.assertEqual(request.call_args.kwargs, {'kind':'text/html', 'accept':'*/*'})

    def mock_opener(self, media, body):
        opener=MagicMock(); response=opener.open.return_value.__enter__.return_value
        response.status=200; response.headers=Message(); response.headers['Content-Type']=media
        response.read.return_value=body
        return opener

    @patch('smoke.urllib.request.build_opener')
    def test_doh_does_not_require_a_browser_workaround(self, build):
        opener=self.mock_opener('application/dns-message',b'packet'); build.return_value=opener
        smoke.request('https://host/s/token/working/dns',body=b'query')
        req=opener.open.call_args.args[0]
        self.assertEqual(req.get_header('Accept'),'application/dns-message')
        self.assertIsNone(req.get_header('Cookie'))
        self.assertIsNone(req.get_header('Authorization'))
        self.assertIsNone(req.get_header('X-tunnel-authorization'))
        self.assertIsNone(req.get_header('X-tunnel-skip-antiphishing-page'))

    @patch('smoke.urllib.request.build_opener')
    def test_accept_override_does_not_relax_response_type(self, build):
        build.return_value=self.mock_opener('application/json',b'{}')
        with self.assertRaises(ValueError):
            smoke.request('https://host/s/token/',kind='text/html',accept='*/*')

    def test_no_arbitrary_header_injection(self):
        with self.assertRaises(ValueError):
            smoke.request('https://host/',kind='text/html',accept='*/*\r\nCookie: secret')

if __name__=='__main__':
    unittest.main(verbosity=2)
