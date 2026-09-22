"""Mutation check of #135 (2026-09-21): applies each mutation, runs the targeted tests, restores the file.
Run from the repository root: .venv/bin/python scripts/dev/mutations/issue_135_2026-09-21.py
"""
import subprocess, re
T=["tests/test_models_admin.py"]
M="app/admin/models.py"; R="app/api/models_routes.py"
MUT=[
 ("name allow-list removed",M,'    if not NAME_RE.fullmatch(name or "") or ".." in name or len(name) > 200:','    if False:'),
 ("dot-dot allowed",M,' or ".." in name or len(name) > 200:',' or len(name) > 200:'),
 ("length cap removed",M,' or ".." in name or len(name) > 200:',' or ".." in name:'),
 ("path containment removed",M,"    if path.parent != directory:","    if False:"),
 ("loaded model deletable",M,"    if loaded == name:","    if False:"),
 ("configured model deletable",M,"    if get_settings().model_file == name:","    if False:"),
 ("hash file left behind",M,"    sidecar(path).unlink(missing_ok=True)","    pass"),
 ("unknown model not 404",M,"    if not path.is_file():","    if False:"),
 ("no directory not 409",M,"    if not directory.is_dir():","    if False:"),
 ("partial downloads listed",M,'    for path in sorted(models_dir().glob("*.gguf")):','    for path in sorted(models_dir().glob("*.gguf*")):'),
 ("recorded hash not read",M,"    return text if re.fullmatch(r\"[0-9a-f]{64}\", text) else None","    return None"),
 ("deletion not audited",R,'        action="model.delete",','        action="model.delete-x",'),
 ("loaded flag always false",R,'ModelOut(**m, loaded=m["name"] == loaded,','ModelOut(**m, loaded=False,'),
 ("configured flag always false",R,'configured=m["name"] == configured)','configured=False)'),
]
for name,path,old,new in MUT:
    src=open(path).read(); assert old in src,(name,old[:45])
    open(path,"w").write(src.replace(old,new,1))
    try:
        r=subprocess.run([".venv/bin/python","-m","pytest",*T,"-q","--no-header","-p","no:cacheprovider"],capture_output=True,text=True,timeout=120)
        failed=sorted({f.split('[')[0] for f in re.findall(r"^FAILED tests/\S+::(\S+)",r.stdout,re.M)})
        print(f"{name}: {len(failed)} failed -> {', '.join(failed)[:90]}")
    finally: open(path,"w").write(src)
