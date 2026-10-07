#!/usr/bin/env python3
import copy, unittest
import dns.flags, dns.message, dns.rrset, dns.rdatatype
from server import Engine, Provider, fingerprint, hostname, parse_query, verdict

P=[
    Provider("one","https://one.example/dns-query","1.1.1.1","test"),
    Provider("two","https://two.example/dns-query","9.9.9.9","test"),
    Provider("three","https://three.example/dns-query","8.8.8.8","test")
]

def answer(name,qtype,provider,variant=False):
    q=dns.message.make_query(name,qtype)
    a=dns.message.make_response(q); a.flags|=dns.flags.AD|dns.flags.RA
    if qtype==dns.rdatatype.A:
        ip="203.0.113.9" if variant else "93.184.216.34"
        a.answer.append(dns.rrset.from_text(name,300,"IN","A",ip))
    elif qtype==dns.rdatatype.AAAA:
        ip="2001:db8::9" if variant else "2606:2800:220:1:248:1893:25c8:1946"
        a.answer.append(dns.rrset.from_text(name,300,"IN","AAAA",ip))
    ips=[r.address for rr in a.answer for r in rr if hasattr(r,"address")]
    return {"provider":provider.name,"endpoint":provider.url,"bootstrap_ip":provider.ip,
            "location":provider.location,"location_basis":"test","qtype":dns.rdatatype.to_text(qtype),
            "checked_at":"test","rcode":"NOERROR","ips":ips,"records":[],"ad_reported":True,
            "ttl":300,"milliseconds":1,"error":None,"_message":a,"_fingerprint":fingerprint(a)}

class Tests(unittest.TestCase):
    def test_hostname(self):
        self.assertEqual(hostname("Example.COM"),"example.com.")
        for bad in ("127.0.0.1","localhost","x.local","https://example.com"):
            with self.assertRaises(ValueError): hostname(bad)

    def test_parse(self):
        q=dns.message.make_query("example.com","A")
        self.assertEqual(parse_query(q.to_wire()).question[0].rdtype,dns.rdatatype.A)

    def test_verdict(self):
        rows=[answer("example.com.",dns.rdatatype.A,p) for p in P]
        self.assertEqual(verdict(rows),"match")
        rows[2]=answer("example.com.",dns.rdatatype.A,P[2],True)
        self.assertEqual(verdict(rows),"mismatch")
        rows[2]=copy.deepcopy(rows[1]); rows[2]["provider"]="three"; rows[2]["error"]="timeout"
        self.assertEqual(verdict(rows),"unavailable")

    def test_gate_match_and_mismatch(self):
        def same(p,n,q,context=None): return answer(n,q,p)
        e=Engine(P,300,query=same)
        try:
            r=e.gate("example.com.")
            self.assertEqual(r["status"],"match"); self.assertTrue(r["allowed"])
        finally:e.close()

        def different(p,n,q,context=None):
            return answer(n,q,p,variant=(p.name=="three" and q==dns.rdatatype.A))
        e=Engine(P,300,query=different)
        try:
            r=e.gate("example.com.")
            self.assertEqual(r["status"],"mismatch"); self.assertFalse(r["allowed"])
        finally:e.close()

if __name__=="__main__": unittest.main(verbosity=2)
