import sys
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch
sys.path.insert(0,str(Path(__file__).resolve().parent/'control'))
import edge_probe
from diagnose import DIAGNOSTICS

class EdgeProbeTests(unittest.TestCase):
    def setUp(self):
        edge_probe.PROBED.clear(); DIAGNOSTICS.clear()

    @patch('smoke.run')
    @patch('edge_probe.http.client.HTTPConnection')
    def test_http_uses_invalid_token_only(self, http, doh):
        session={'public_origin':'https://runtime-8080.app.github.dev',
                 'doh':'https://runtime-8080.app.github.dev/s/live-secret-must-not-leak/working/dns'}
        response=http.return_value.getresponse.return_value
        response.status=301
        response.getheader.side_effect=lambda key,default='': {'Location':'https://runtime-8080.app.github.dev/','Content-Type':'text/html'}.get(key,default)
        doh.return_value={'A':['89.233.43.71'],'AAAA':['2a01:3a0:53:53::']}
        edge_probe.probe(session)
        for call in http.return_value.request.call_args_list:
            self.assertNotIn('live-secret',str(call))
            self.assertIn('invalid-transport-probe',call.args[1])
        self.assertNotIn('live-secret',str(DIAGNOSTICS))
        self.assertEqual(http.return_value.request.call_count,3)
        self.assertTrue(DIAGNOSTICS[-1]['passed'])
        edge_probe.probe(session)
        self.assertEqual(http.return_value.request.call_count,3)

    @patch('edge_probe.http.client.HTTPConnection')
    def test_non_session_inputs_do_not_cause_network_requests(self,http):
        edge_probe.probe({'doh':'private-test'})
        http.assert_not_called()

if __name__=='__main__':
    unittest.main(verbosity=2)
