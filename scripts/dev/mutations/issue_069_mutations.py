import subprocess
muts=[
("M1 one runtime pin loosened","requirements.txt","aiofiles==25.1.0","aiofiles>=25.1.0"),
("M2 direct dependency missing from the lock","requirements.in","httpx","httpx\nnot-a-locked-package"),
("M3 requirements.in pinned","requirements.in","fastapi\n","fastapi==0.1\n"),
("M4 dev lock differs from runtime lock","requirements-dev.txt","aiofiles==25.1.0","aiofiles==25.0.0"),
("M5 image installs the loose list","Dockerfile","pip install --no-cache-dir -r requirements.txt","pip install --no-cache-dir -r requirements.in"),
("M6 CI installs the runtime lock only","./.github/workflows/ci.yml","run: pip install -r requirements-dev.txt","run: pip install -r requirements.txt"),
("M7 start.sh installs the loose list","start.sh","pip install --quiet -r requirements.txt","pip install --quiet -r requirements.in"),
("M8 script resolves with another Python","scripts/update_requirements.sh","python:3.12-slim","python:3.13-slim"),
("M9 Dependabot daily","./.github/dependabot.yml","interval: weekly","interval: daily"),
("M10 CI without the audit","./.github/workflows/ci.yml","run: pip-audit -r requirements.txt --no-deps --disable-pip","run: echo skipped"),
("M11 CI audit silently ignores a vulnerability","./.github/workflows/ci.yml","run: pip-audit -r requirements.txt --no-deps --disable-pip","run: pip-audit -r requirements.txt --ignore-vuln PYSEC-1 --no-deps"),
("M12 README without the update procedure","README.md","scripts/update_requirements.sh","scripts/x.sh"),
]
for name,f,a,b in muts:
    f=f.removeprefix("./")
    orig=open(f).read()
    assert a in orig,name
    new=orig.replace(a,b) if name.startswith(("M8","M12")) else orig.replace(a,b,1)
    assert new!=orig,name
    open(f,"w").write(new)
    try:
        r=subprocess.run([".venv/bin/python","-m","pytest","tests/test_requirements_lock.py","-q","--no-header","-p","no:cacheprovider"],capture_output=True,text=True)
        print(name,"->",r.stdout.strip().splitlines()[-1])
    finally:
        open(f,"w").write(orig)
