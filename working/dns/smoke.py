#!/usr/bin/env python3
import os, ssl, urllib.request
import dns.flags, dns.message, dns.rcode
url=os.environ["DOH"]
q=dns.message.make_query("example.com.", "A", want_dnssec=True)
req=urllib.request.Request(url,data=q.to_wire(),headers={
    "Content-Type":"application/dns-message","Accept":"application/dns-message",
    "User-Agent":"BlackCat-DoH-Smoke/0.1"},method="POST")
ctx=ssl.create_default_context(); ctx.minimum_version=ssl.TLSVersion.TLSv1_2
with urllib.request.urlopen(req,context=ctx,timeout=12) as r:
    if r.status != 200 or r.headers.get_content_type()!="application/dns-message":
        raise SystemExit("Invalid DoH HTTP response")
    a=dns.message.from_wire(r.read(65536))
if not (a.flags & dns.flags.QR) or a.id!=q.id:
    raise SystemExit("Invalid DNS response")
if a.rcode() not in (dns.rcode.NOERROR,dns.rcode.SERVFAIL,dns.rcode.NXDOMAIN):
    raise SystemExit("Unexpected DNS rcode "+dns.rcode.to_text(a.rcode()))
print("DoH response:",dns.rcode.to_text(a.rcode()),"answers",len(a.answer))
