import subprocess, pathlib
F={"g":pathlib.Path("app/admin/rekey_guided.py"),"s":pathlib.Path("start.sh")}
orig={k:v.read_text() for k,v in F.items()}
muts={
"M1 no check that the app is stopped":("g","    if reasons:\n","    if False:\n"),
"M2 dry run skipped for unreadable":("g","    if report.unreadable and not args.allow_unreadable:\n        print(\n            \"Refused: some values","    if False:\n        print(\n            \"Refused: some values"),
"M3 confirmation ignored":("g","        if answer != CONFIRMATION_WORD:","        if False:"),
"M4 safety net not written":("g","    _write_private(SAFETY_NET, previous_env)\n",""),
"M5 existing safety net overwritten":("g","    if SAFETY_NET.exists() and not args.dry_run:","    if False:"),
"M6 new key not written to .env":("g","    _replace_key(ENV_FILE, new_key)\n",""),
"M7 rollback does not restore .env":("g","        _write_private(ENV_FILE, previous_env)\n        SAFETY_NET.unlink(missing_ok=True)","        SAFETY_NET.unlink(missing_ok=True)"),
"M8 rollback even when data moved":("g","    if rewritten == 0:","    if True:"),
"M9 dry-run flag writes anyway":("g","    if args.dry_run:\n        print(\"Dry run only","    if False:\n        print(\"Dry run only"),
"M10 the old key is printed":("g","    print(f\"{report.to_rewrite} value(s) to re-encrypt, {report.unreadable} unreadable.\")","    print(f\"{report.to_rewrite} value(s) to re-encrypt, {report.unreadable} unreadable. {old_key}\")"),
"M11 the new key is printed":("g","    print(\"==> 6/6 Done. What to do now\")","    print(\"==> 6/6 Done. What to do now\"); print(new_key)"),
"M12 files not private":("g","    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)\n    try:\n        os.fchmod(fd, 0o600)","    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)\n    try:\n        os.fchmod(fd, 0o644)"),
"M13 read-back skipped":("g","        unreadable = _read_back_unreadable()","        unreadable = 0"),
"M14 backups disabled":("g","            db_path, checkpoints, old_key, new_key, allow_unreadable=args.allow_unreadable\n        )","            db_path, checkpoints, old_key, new_key, allow_unreadable=args.allow_unreadable,\n            backup=False,\n        )"),
"M15 start.sh keeps the exported key":("s","exec env -u ENCRYPTION_KEY -u OLD_ENCRYPTION_KEY python3 -m app.admin.rekey_guided","exec python3 -m app.admin.rekey_guided"),
}
def run():
    r=subprocess.run([".venv/bin/python","-m","pytest","tests/test_rekey_guided.py","-q","-x","-p","no:cacheprovider"],capture_output=True,text=True)
    return r.stdout.strip().splitlines()[-1]
try:
    for n,(f,a,b) in muts.items():
        assert a in orig[f],n
        F[f].write_text(orig[f].replace(a,b,1)); print(n,"->",run()); F[f].write_text(orig[f])
finally:
    for k,v in F.items(): v.write_text(orig[k])
