import subprocess, pathlib
files = {"h": pathlib.Path("app/health.py"), "m": pathlib.Path("app/main.py")}
orig = {k: v.read_text() for k, v in files.items()}
muts = {
 "M1 beats after all ended": ("h","    while not components or any(not task.done() for task in components):","    while True:"),
 "M2 age ignored": ("h","    if age > max_age:","    if False:"),
 "M3 heartbeat not started": ("m","    beating = asyncio.create_task(heartbeat(tasks))","    beating = asyncio.create_task(asyncio.sleep(0))"),
 "M4 needs all components": ("h","any(not task.done() for task in components)","all(not task.done() for task in components)"),
 "M5 idle app unhealthy": ("h","while not components or any","while any"),
 "M6 missing file healthy": ("h",'        return False, f"no heartbeat file at {target}"','        return True, "x"'),
 "M7 exit code always 0": ("h","    return 0 if healthy else 1","    return 0"),
 "M8 wrong file": ("h","    (path or HEARTBEAT_PATH).touch()","    (path or HEARTBEAT_PATH.with_name('other')).touch()"),
}
try:
    for name,(f,a,b) in muts.items():
        assert a in orig[f], name
        files[f].write_text(orig[f].replace(a,b,1))
        r = subprocess.run([".venv/bin/python","-m","pytest","tests/test_health.py","-q","-x","-p","no:cacheprovider"],capture_output=True,text=True)
        print(name, "->", r.stdout.strip().splitlines()[-1])
        files[f].write_text(orig[f])
finally:
    for k,v in files.items(): v.write_text(orig[k])
