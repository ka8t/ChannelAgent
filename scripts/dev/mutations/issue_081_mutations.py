import subprocess
F="app/db/backup.py"
muts=[
("M1 ordered by the whole name (the bug)","    dated.sort()\n","    dated.sort(key=lambda t: t[1])\n"),
("M2 before-restore copies pruned",'_NEVER_PRUNED = ("-prerekey-", "-before-restore-")','_NEVER_PRUNED = ("-prerekey-",)'),
("M3 prerekey copies pruned",'_NEVER_PRUNED = ("-prerekey-", "-before-restore-")','_NEVER_PRUNED = ("-before-restore-",)'),
("M4 files without a stamp pruned","        if match:\n            dated.append((match.group(1), path.name, path))","        dated.append((match.group(1) if match else '', path.name, path))"),
("M5 one backup too many deleted","dated[:-keep] if keep > 0 else []","dated[:-(keep - 1)] if keep > 1 else dated"),
("M6 oldest first kept (reverse order)","    dated.sort()\n","    dated.sort(reverse=True)\n"),
]
orig=open(F).read()
for name,a,b in muts:
    assert a in orig,name
    new=orig.replace(a,b,1); assert new!=orig,name
    open(F,"w").write(new)
    try:
        r=subprocess.run([".venv/bin/python","-m","pytest","tests/test_backup_prune.py","-q","--no-header","-p","no:cacheprovider"],capture_output=True,text=True)
        print(name,"->",r.stdout.strip().splitlines()[-1])
    finally:
        open(F,"w").write(orig)
