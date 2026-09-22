"""Mutation check of #108 (2026-09-21): applies each mutation, runs the targeted tests, restores the file.
Run from the repository root: .venv/bin/python scripts/dev/mutations/issue_108_2026-09-21.py
"""
import subprocess, re, shutil
MUT=[
 ("default deny (verify_scopes does nothing)","app/api/scopes.py","    if missing:\n        raise RuntimeError(","    if False:\n        raise RuntimeError("),
 ("scope check removed","app/api/scopes.py","        if principal.scope < self.scope:","        if False:"),
 ("host allow-list removed","app/api/protect.py","        if _host_name(headers.get(\"host\", \"\")) not in hosts:","        if False:"),
 ("origin check removed","app/api/protect.py","            if origin_host not in hosts:","            if False:"),
 ("content-length limit removed","app/api/protect.py","        if declared is not None and declared.isdigit() and int(declared) > limit:","        if False:"),
 ("streamed body limit removed","app/api/protect.py","                if received > limit:","                if False:"),
 ("timeout removed","app/api/protect.py","                timeout=settings.api_request_timeout_seconds,","                timeout=None,"),
 ("error handler leaks the exception text","app/api/app.py","content={\"detail\": \"Internal server error\", \"error_id\": error_id}","content={\"detail\": str(exc), \"error_id\": error_id}"),
 ("extra fields allowed","app/api/schemas.py","class UserCreate(BaseModel):\n    model_config = ConfigDict(extra=\"forbid\")","class UserCreate(BaseModel):\n    model_config = ConfigDict(extra=\"ignore\")"),
]
for name,path,old,new in MUT:
    src=open(path).read(); assert old in src,(name,old[:40])
    open(path,"w").write(src.replace(old,new,1))
    try:
        r=subprocess.run([".venv/bin/python","-m","pytest","tests/test_api_scopes.py","-q","--no-header","-p","no:cacheprovider"],capture_output=True,text=True,timeout=120)
        failed=re.findall(r"^FAILED tests/test_api_scopes.py::(\S+)",r.stdout,re.M)
        print(f"{name}: {len(failed)} failed -> {', '.join(f.split('[')[0] for f in failed)[:110]}")
    except subprocess.TimeoutExpired:
        print(f"{name}: TIMEOUT (counts as detected)")
    finally:
        open(path,"w").write(src)
