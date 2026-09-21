import subprocess
R="app/admin/restore.py"; S="start.sh"
muts=[
("M1 running check skipped",R,"    reasons = running_reasons(db_path, api_host, api_port)\n    if reasons:","    reasons = []\n    if reasons:"),
("M2 lock check skipped",R,'            if "lock" in str(exc).lower() or "busy" in str(exc).lower():','            if False:'),
("M3 API probe skipped",R,"        with socket.create_connection((probe_host, port), timeout=1):","        with socket.create_connection((probe_host, 1), timeout=1):"),
("M4 backup checks skipped",R,"    revision, needs_migration = check_backup(backup)","    revision, needs_migration = _current_revision(backup), False"),
("M5 unknown revision accepted",R,"    if revision not in known:","    if False:"),
("M6 unreadable values ignored",R,"        if not allow_unreadable:\n            raise RestoreError(\n                \"refused:","        if False:\n            raise RestoreError(\n                \"refused:"),
("M7 confirmation ignored",R,"    if not yes:\n        answer","    if False:\n        answer"),
("M8 no copy of the current database",R,"    if have_current:\n        report.before_restore_copy = make_backup(db_path, \"before-restore\")","    if False:\n        report.before_restore_copy = make_backup(db_path, \"before-restore\")"),
("M9 stale wal kept",R,'        for suffix in ("-wal", "-shm", "-journal"):','        for suffix in ():'),
("M10 staged copy world readable",R,"os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)","os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o644)"),
("M11 final mode not set",R,"    os.chmod(db_path, 0o600)\n",""),
("M12 checkpoints backups listed",R,'directory.glob(f"{db_path.stem}-*.db")','directory.glob("*.db")'),
("M13 prerekey not recognised",R,'    if label == "prerekey":','    if label == "prerekey-x":'),
("M14 checkpoint note missing",R,'"Checkpoints : the conversation history (checkpoints.db) is a separate file and was NOT "','"Checkpoints : the conversation history (checkpoints.db) is a separate file and was "'),
("M15 live file may be restored onto itself",R,"    if backup == db_path.resolve():","    if False:"),
("M16 needs_migration never set",R,"    report.needs_migration = needs_migration","    report.needs_migration = False"),
("M17 cli ignores --yes",R,"            yes=args.yes,","            yes=False,"),
("M18 cli ignores --allow-unreadable",R,"            allow_unreadable=args.allow_unreadable,","            allow_unreadable=False,"),
("M19 start.sh does not route --restore",S,'  --restore) MODE="restore" ;;\n',""),
("M20 integrity check skipped",R,"    if integrity != [(\"ok\",)]:","    if False:"),
("M22 both permission safeguards removed",R,"os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o600)","os.O_CREAT | os.O_WRONLY | os.O_EXCL, 0o644)"),
("M21 swap leaves the staging file",R,"    finally:\n        staging.unlink(missing_ok=True)\n    os.chmod","    finally:\n        pass\n    os.chmod"),
]
for name,f,a,b in muts:
    orig=open(f).read()
    assert a in orig,name
    new=orig.replace(a,b,1); assert new!=orig,name
    if name.startswith('M22'): new=new.replace('    os.chmod(db_path, 0o600)\n','',1)
    open(f,"w").write(new)
    try:
        r=subprocess.run([".venv/bin/python","-m","pytest","tests/test_restore.py","-q","--no-header","-p","no:cacheprovider"],capture_output=True,text=True)
        print(name,"->",r.stdout.strip().splitlines()[-1])
    finally:
        open(f,"w").write(orig)
