"""Mutation check of #137 (2026-09-21): applies each mutation, runs the targeted tests, restores the file.
Run from the repository root: .venv/bin/python scripts/dev/mutations/issue_137_2026-09-21.py
"""
import subprocess, re
M="app/admin/models.py"; R="app/api/models_routes.py"
MUT=[
 ("spec syntax not checked",M,"    if HUB_SPEC.fullmatch(spec):","    if True:"),
 ("ambiguous quant takes the first",M,"    if len(ggufs) > 1:","    if False:"),
 ("shards pulled",M,"    if SHARD.search(ggufs[0]):","    if False:"),
 ("projector files listed",M,' and "mmproj" not in f.lower()]',']'),
 ("no .gguf match not refused",M,"    if not ggufs:","    if False:"),
 ("hash never compared",M,"    if expected and digest != expected:","    if False:"),
 ("bad file kept after a mismatch",M,"        part.unlink(missing_ok=True)\n        raise JobError(\"The SHA256","        raise JobError(\"The SHA256"),
 ("administrator hash ignored",M,"    expected = _expected_hash(plan.get(\"sha256\"), seen.get(\"x-linked-etag\"))","    expected = _expected_hash(seen.get(\"x-linked-etag\"))"),
 ("hub hash ignored",M,"    expected = _expected_hash(plan.get(\"sha256\"), seen.get(\"x-linked-etag\"))","    expected = _expected_hash(plan.get(\"sha256\"))"),
 ("resume does not ask for a range",M,'        if start:\n            headers["Range"]','        if False:\n            headers["Range"]'),
 ("range answer not verified",M,"            if not match or int(match.group(1)) != offset:","            if False:"),
 ("declared size limit removed",M,"        if total and total > settings.model_pull_max_bytes:","        if False:"),
 ("streamed size limit removed",M,"                    if received > settings.model_pull_max_bytes:","                    if False:"),
 ("time limit removed",M,"        async with asyncio.timeout(settings.model_pull_timeout_seconds):","        async with asyncio.timeout(None):"),
 ("free space not checked",M,"        if total and free_bytes(directory) < total - offset + FREE_SPACE_MARGIN:","        if False:"),
 ("incomplete download accepted",M,"    if total and received != total:","    if False:"),
 ("name not claimed",M,"                claim(name)\n","                pass\n"),
 ("existing name overwritten",M,"                if (dest.exists() or dest.is_symlink()) and not plan[\"force\"]:","                if False:"),
 ("URL not guarded up front",M,"            await asyncio.to_thread(build_guard().prepare, plan[\"url\"])","            pass"),
 ("hop not guarded",M,"            target = await asyncio.to_thread(guard.prepare, url)","            target = await asyncio.to_thread(guard.prepare, url) if not url.startswith('https://10.') and _ < 1 else __import__('app.security.outbound',fromlist=['Target']).Target(url=url, host_header=urlsplit(url).netloc, sni=None)"),
 ("token sent to every host",M,"        if token and host == hub_host:","        if token:"),
 ("pinned address not used",M,'        request = client.build_request("GET", target.url,','        request = client.build_request("GET", url,'),
 ("Host header not restored",M,'        headers = {"Host": target.host_header, "User-Agent": "channelagent-model-pull"}','        headers = {"User-Agent": "channelagent-model-pull"}'),
 ("pull not audited",R,'                action="model.pull",','                action="model.pull-x",'),
 ("verified flag always true",M,'        "verified": expected is not None,','        "verified": True,'),
]
T=["tests/test_models_pull.py"]
for name,path,old,new in MUT:
    src=open(path).read()
    if old not in src: print(name,": PATTERN NOT FOUND"); continue
    open(path,"w").write(src.replace(old,new,1))
    try:
        r=subprocess.run([".venv/bin/python","-m","pytest",*T,"-q","--no-header","-p","no:cacheprovider"],capture_output=True,text=True,timeout=200)
        failed=sorted({f.split('[')[0] for f in re.findall(r"^FAILED tests/\S+::(\S+)",r.stdout,re.M)})
        print(f"{name}: {len(failed)} failed -> {', '.join(failed)[:80]}")
    except subprocess.TimeoutExpired: print(name,"TIMEOUT (detected)")
    finally: open(path,"w").write(src)
