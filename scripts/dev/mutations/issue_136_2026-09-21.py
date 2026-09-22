"""Mutation check of #136 (2026-09-21): applies each mutation, runs the targeted tests, restores the file.
Run from the repository root: .venv/bin/python scripts/dev/mutations/issue_136_2026-09-21.py
"""
import subprocess, re
M="app/admin/models.py"; R="app/api/models_routes.py"
MUT=[
 ("GGUF check removed",M,"        if f.read(4) != GGUF_MAGIC:","        if False:"),
 ("directory accepted as source",M,"    if not src.is_file():","    if False:"),
 ("name required check removed",M,"    if name is None and not NAME_RE.fullmatch(chosen):","    if False:"),
 ("existing name overwritten silently",M,"    if (dest.exists() or dest.is_symlink()) and not force:","    if False:"),
 ("free space not checked",M,"    if free_bytes(directory) < size + FREE_SPACE_MARGIN:","    if False:"),
 ("partial file kept on failure",M,"        if not done:\n            part.unlink(missing_ok=True)","        if False:\n            part.unlink(missing_ok=True)"),
 ("copy not renamed atomically (direct write)",M,"        os.replace(part, dest)","        os.replace(part, dest)\n        part = dest"),
 ("hash file not written",M,"    write_sha256(dest, digest.hexdigest())","    pass"),
 ("wrong hash reported",M,'    return {"name": plan["name"], "size_bytes": copied, "sha256": digest.hexdigest()}','    return {"name": plan["name"], "size_bytes": copied, "sha256": "0" * 64}'),
 ("progress never reported",M,"                job.update(copied / size if size else 1.0)","                pass"),
 ("size mismatch not detected",M,"        if copied != size:","        if False:"),
 ("name never released",R,"    job.task.add_done_callback(lambda _task, name=plan[\"name\"]: models.release(name))","    pass"),
 ("name never claimed",R,"    models.claim(plan[\"name\"])\n    actor","    actor"),
 ("import not audited",R,'                action="model.import",','                action="model.import-x",'),
]
for name,path,old,new in MUT:
    src=open(path).read(); assert old in src,(name,old[:45])
    open(path,"w").write(src.replace(old,new,1))
    try:
        r=subprocess.run([".venv/bin/python","-m","pytest","tests/test_models_import.py","-q","--no-header","-p","no:cacheprovider"],capture_output=True,text=True,timeout=120)
        failed=sorted({f.split('[')[0] for f in re.findall(r"^FAILED tests/\S+::(\S+)",r.stdout,re.M)})
        print(f"{name}: {len(failed)} failed -> {', '.join(failed)[:85]}")
    except subprocess.TimeoutExpired: print(name,"TIMEOUT")
    finally: open(path,"w").write(src)
