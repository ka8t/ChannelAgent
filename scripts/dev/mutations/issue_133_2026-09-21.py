"""Mutation check of #133 (2026-09-21): applies each mutation, runs the targeted tests, restores the file.
Run from the repository root: .venv/bin/python scripts/dev/mutations/issue_133_2026-09-21.py
"""
import subprocess, re
MUT=[
 ("offset/limit slicing removed","app/api/routes.py","    return items[offset : offset + limit]","    return items"),
 ("total header removed","app/api/routes.py",'    response.headers["X-Total-Count"] = str(len(items))\n','    pass\n'),
 ("limit bounds removed","app/api/routes.py","LIMIT = Query(default=200, ge=1, le=1000,","LIMIT = Query(default=200,"),
 ("a tag removed","app/api/routes.py",'tags=["requests"],','tags=[],'),
 ("documented errors removed","app/api/errors.py","    codes = (401, 403, 429, *extra)","    codes = ()"),
 ("version not declared","app/api/app.py","    version=API_VERSION,\n","    version=\"0.1.0\",\n"),
 ("engine failure raises","app/api/status.py","    except (httpx.HTTPError, ValueError, AttributeError):","    except ZeroDivisionError:"),
 ("full model path leaked","app/api/status.py","            model=os.path.basename(model_path) if model_path else None,","            model=model_path,"),
 ("scope name wrong in whoami","app/api/status.py","scope=principal.scope.name.lower()","scope=principal.scope.name"),
]
for name,path,old,new in MUT:
    src=open(path).read(); assert old in src,(name,old[:40])
    open(path,"w").write(src.replace(old,new,1))
    try:
        r=subprocess.run([".venv/bin/python","-m","pytest","tests/test_api_completeness.py","tests/test_api_scopes.py","-q","--no-header","-p","no:cacheprovider"],capture_output=True,text=True,timeout=150)
        failed=re.findall(r"^FAILED tests/(\S+)",r.stdout,re.M)
        print(f"{name}: {len(failed)} failed -> {', '.join(f.split('::')[1].split('[')[0] for f in failed)[:100]}")
    except subprocess.TimeoutExpired: print(f"{name}: TIMEOUT")
    finally: open(path,"w").write(src)
