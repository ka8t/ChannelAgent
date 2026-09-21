import subprocess
F="start.sh"
muts=[
("M1 existing key overwritten","    if current:\n        print(","    if False:\n        print("),
("M2 refuse only a different key","    if current:\n        print(","    if current and current != value:\n        print("),
("M3 no Fernet validation","    if not re.fullmatch(r\"[A-Za-z0-9_-]{43}=\", value):","    if False:"),
("M4 standard alphabet accepted",'r"[A-Za-z0-9_-]{43}="','r"[A-Za-z0-9_+/-]{43}="'),
("M6 no backup","    os.write(fd, previous)\n","    pass\n"),
("M7 backup world readable","os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)\ntry:\n    os.fchmod(fd, 0o600)","os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)\ntry:\n    os.fchmod(fd, 0o644)"),
("M8 backup appended, not one generation","os.O_WRONLY | os.O_CREAT | os.O_TRUNC","os.O_WRONLY | os.O_CREAT | os.O_APPEND"),
("M9 refusal prints the current key","            \"'Encryption key: backup, loss and rotation').\",\n            file=sys.stderr,","            \"'Encryption key: backup, loss and rotation').\" + current,\n            file=sys.stderr,"),
("M10 backup written before the guard","with open(path) as f:\n    lines = f.readlines()\n","with open(path) as f:\n    lines = f.readlines()\nopen(path + '.bak', 'w').write('x')\n"),
]
orig=open(F).read()
for name,a,b in muts:
    assert a in orig,name
    new=orig.replace(a,b,1); assert new!=orig,name
    open(F,"w").write(new)
    try:
        r=subprocess.run([".venv/bin/python","-m","pytest","tests/test_start_set_safety.py","-q","--no-header","-p","no:cacheprovider"],capture_output=True,text=True)
        print(name,"->",r.stdout.strip().splitlines()[-1])
    finally:
        open(F,"w").write(orig)
