"""Mutation check of #134 (2026-09-21): applies each mutation, runs the targeted tests, restores the file.
Run from the repository root: .venv/bin/python scripts/dev/mutations/issue_134_2026-09-21.py
"""
import subprocess, re
MUT=[
 ("http allowed","app/security/outbound.py",'        if parts.scheme == "http" and not self.allow_http:','        if False:'),
 ("credentials allowed","app/security/outbound.py","        if parts.username or parts.password:","        if False:"),
 ("allow-list ignored","app/security/outbound.py","        if not self.host_allowed(host):","        if False:"),
 ("private addresses allowed","app/security/outbound.py","        if not self.allow_private:","        if False:"),
 ("lookalike host accepted (suffix without the dot)","app/security/outbound.py",'host.endswith("." + h)','host.endswith(h)'),
 ("connection not pinned to the checked address","app/security/outbound.py","        address = addresses[0]","        address = host"),
 ("name resolved twice","app/security/outbound.py","                addresses = self.resolver(host, port)","                self.resolver(host, port)\n                addresses = self.resolver(host, port)"),
 ("TLS server name dropped","app/security/outbound.py",'        sni = host if parts.scheme == "https" else None','        sni = None'),
 ("hub host not added to the allow-list","app/security/outbound.py","    if hub:\n        hosts.add(hub.lower())","    pass"),
]
for name,path,old,new in MUT:
    src=open(path).read(); assert old in src,(name,old[:45])
    open(path,"w").write(src.replace(old,new,1))
    try:
        r=subprocess.run([".venv/bin/python","-m","pytest","tests/test_outbound_guard.py","-q","--no-header","-p","no:cacheprovider"],capture_output=True,text=True,timeout=120)
        failed=sorted({f.split('[')[0] for f in re.findall(r"^FAILED tests/\S+::(\S+)",r.stdout,re.M)})
        print(f"{name}: {len(failed)} failed -> {', '.join(failed)[:100]}")
    finally: open(path,"w").write(src)
