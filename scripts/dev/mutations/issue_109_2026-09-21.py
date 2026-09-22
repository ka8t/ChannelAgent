"""Mutation check of #109 (2026-09-21): applies each mutation, runs the targeted tests, restores the file.
Run from the repository root: .venv/bin/python scripts/dev/mutations/issue_109_2026-09-21.py
"""
import subprocess, re
T=["tests/test_api_jobs.py","tests/test_api_config.py","tests/test_admin_client.py","tests/test_api_scopes.py","tests/test_api_completeness.py"]
MUT=[
 ("actor label ignored","app/api/actor.py","    return value if value and _CLI.fullmatch(value) else API_ACTOR","    return API_ACTOR"),
 ("job cancel does nothing","app/admin/jobs.py","            job.task.cancel()","            pass"),
 ("ENCRYPTION_KEY settable through the API","app/settings_rules.py","        if not allow_initial_key:","        if False:"),
 ("secret value returned by GET /config","app/api/config_routes.py",'            value=None if e["secret"] else (e["value"] or None),','            value=e["value"] or None,'),
 ("config write echoes nothing but ignores the .env check","app/api/config_routes.py","    if not os.path.isfile(env) or not os.path.isfile(example):","    if False:"),
 ("contract: help text no longer required","app/admin/manifest.py",'        if not op["description"]:','        if False:'),
 ("contract: duplicate command names not flagged","app/admin/manifest.py",'        if op["command"] in seen:','        if False:'),
 ("client does not wait for a job","app/admin/client.py","    if response.status_code == 202 and wait and","    if False and"),
 ("failed job does not fail the command","app/admin/client.py",'        op["returns_job"]\n        and isinstance(body, dict)','        False\n        and isinstance(body, dict)'),
 ("describe drops the audit commands","app/admin/manifest.py","        method = sorted(route.methods - {\"HEAD\", \"OPTIONS\"})[0]","        if route.tags and route.tags[0] == \"audit\":\n            continue\n        method = sorted(route.methods - {\"HEAD\", \"OPTIONS\"})[0]"),
 ("engine launched with the full environment","start.sh",'nohup env -i PATH="$PATH" HOME="$HOME" TMPDIR="${TMPDIR:-/tmp}" LANG="${LANG:-C}" \\\n      "${LLAMA_SERVER_BIN}" \\','nohup \\\n      "${LLAMA_SERVER_BIN}" \\'),
]
for name,path,old,new in MUT:
    src=open(path).read(); assert old in src,(name,old[:45])
    open(path,"w").write(src.replace(old,new,1))
    try:
        r=subprocess.run([".venv/bin/python","-m","pytest",*T,"-q","--no-header","-p","no:cacheprovider","-x" if False else "-q"],capture_output=True,text=True,timeout=300)
        failed=re.findall(r"^FAILED tests/(\S+)",r.stdout,re.M)
        print(f"{name}: {len(failed)} failed -> {', '.join(sorted({f.split('::')[1].split('[')[0] for f in failed}))[:110]}")
    except subprocess.TimeoutExpired: print(f"{name}: TIMEOUT")
    finally: open(path,"w").write(src)
