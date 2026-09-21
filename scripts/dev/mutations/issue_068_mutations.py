import subprocess
muts=[
("M1 umask not set","app/security/permissions.py","    os.umask(0o077)\n","    pass\n"),
("M2 wrong mode mask","app/security/permissions.py","_GROUP_AND_OTHER = 0o077","_GROUP_AND_OTHER = 0o007"),
("M3 nothing logged","app/security/permissions.py","    if loose:\n        listing","    if False:\n        listing"),
("M4 warning tightens the file","app/security/permissions.py","    return len(loose)\n\n\ndef warn_about_loose_application_files","    for p, _ in loose:\n        p.chmod(0o600)\n    return len(loose)\n\n\ndef warn_about_loose_application_files"),
("M5 backup file 644","app/db/backup.py","os.O_EXCL, 0o600))","os.O_EXCL, 0o644))"),
("M6 backup dir 755","app/db/backup.py","        directory.mkdir(parents=True, mode=0o700)  # a copy of everything: owner only (#68)\n        os.chmod(directory, 0o700)  # mkdir's mode is filtered by the umask; be exact\n","        directory.mkdir(parents=True, mode=0o755)\n        os.chmod(directory, 0o755)\n"),
("M7 app.main not hardened","app/main.py","async def main() -> None:\n    harden_process()\n","async def main() -> None:\n"),
("M8 console not hardened","app/admin/cli.py","async def main() -> None:\n    harden_process()\n","async def main() -> None:\n"),
("M9 rekey not hardened","app/admin/rekey.py","    args = parser.parse_args(argv)\n    harden_process()\n","    args = parser.parse_args(argv)\n"),
("M10 start.sh copies with the caller's umask","start.sh","  (umask 077; cp .env.example .env)","  (cp .env.example .env)"),
("M11 start.sh never warns","start.sh",'  if [ $(( 8#$mode & 8#077 )) -ne 0 ]; then','  if false; then'),
("M12 start.sh fixes the mode itself","start.sh",'Restrict it: chmod 600 .env" >&2\n  fi','Restrict it: chmod 600 .env" >&2\n    chmod 600 .env\n  fi'),
("M13 db file not checked","app/security/permissions.py","        paths.append(database)\n","        pass\n"),
("M14 checkpoint file not checked","app/security/permissions.py","    paths.append(checkpoint_db_path())\n",""),
]
for name,f,a,b in muts:
    orig=open(f).read()
    assert a in orig,name
    new=orig.replace(a,b,1)
    assert new!=orig,name
    open(f,"w").write(new)
    try:
        r=subprocess.run([".venv/bin/python","-m","pytest","tests/test_file_permissions.py","-q","--no-header","-p","no:cacheprovider"],capture_output=True,text=True)
        print(name,"->",r.stdout.strip().splitlines()[-1])
    finally:
        open(f,"w").write(orig)
