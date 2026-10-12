"""Bounded diagnostics for this service only; never sends a real capability over HTTP."""
from __future__ import annotations
import base64
import http.client
import sys
from urllib.parse import urljoin, urlsplit
import controller
import diagnose

PROBED = set()


def probe(session):
    if not session.get('public_origin') or session.get('doh') in PROBED:
        return
    PROBED.add(session['doh'])
    sys.path.insert(0, str(controller.ROOT))
    import dns.message
    from smoke import run
    host=urlsplit(session['public_origin']).hostname
    wire=dns.message.make_query('unicast.uncensoreddns.org.', 'A').to_wire()
    encoded=base64.urlsafe_b64encode(wire).rstrip(b'=').decode()
    root='/s/invalid-transport-probe/'
    for method, path, body in [('GET', root, None),
                               ('GET', root+'working/dns?dns='+encoded, None),
                               ('POST', root+'working/dns', wire)]:
        conn=http.client.HTTPConnection(host, 80, timeout=10)
        try:
            conn.request(method,path,body=body,headers={'Accept':'application/dns-message',
                         'Content-Type':'application/dns-message','Connection':'close'})
            response=conn.getresponse()
            location=response.getheader('Location','')
            target=urlsplit(urljoin('http://'+host+path,location))
            diagnose.note('http_edge_probe', method=method, status=response.status,
                          content_type=response.getheader('Content-Type',''),
                          requested_path=path.split('?')[0],
                          redirect_scheme=target.scheme, redirect_host=target.hostname,
                          redirect_port=target.port, redirect_path=target.path,
                          redirect_query=target.query, has_location=bool(location))
        except Exception as exc:
            diagnose.note('http_edge_probe_error',method=method,
                          error_type=type(exc).__name__,reason=diagnose.redact(str(exc)))
        finally:
            conn.close()
    try:
        evidence=run(session['doh'])
        diagnose.note('independent_doh_probe', passed=True, addresses=evidence,
                      transport='Verified HTTPS; ordinary DoH GET and POST; no cookies or auth headers')
    except Exception as exc:
        diagnose.note('independent_doh_probe',passed=False,error_type=type(exc).__name__,
                      reason=diagnose.redact(str(exc)))
