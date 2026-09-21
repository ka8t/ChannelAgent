import subprocess, pathlib
p=pathlib.Path("start.sh"); o=p.read_text()
muts={
"M1 pid file trusted without checking the command":('  pid_alive "$pid" || return 1\n  ps -p "$pid" -o command= 2>/dev/null | grep -q -- "$pattern"','  pid_alive "$pid" || return 1\n  return 0'),
"M2 stop kills whatever the pid file names":('  if pid_is "$file" "$pattern"; then\n    pid="$(cat "$file")"','  if [ -f "$file" ]; then\n    pid="$(cat "$file")"'),
"M3 --stop always stops llama-server":('  if [ "$also_llama" = "1" ]; then','  if true; then'),
"M4 --stop --all does not stop llama-server":('  if [ "$also_llama" = "1" ]; then\n    stop_pid_file "llama-server"','  if [ "$also_llama" = "1" ]; then\n    true "llama-server"'),
"M5 container not stopped":('    docker compose stop channelagent || status=1','    true'),
"M6 stops every container":('    docker compose stop channelagent || status=1','    docker compose stop || status=1'),
"M7 401 counted as down":('      200|401|429) echo','      200|429) echo'),
"M8 zombie counted alive":('  [ -n "$state" ] && [ "${state:0:1}" != "Z" ]','  [ -n "$state" ]'),
"M9 stale pid file kept":('      rm -f "$file"\n      echo "==> ${label}: stale','      echo "==> ${label}: stale'),
"M10 no notice after --set":('  echo "==> Applies at the next start','  true "Applies at the next start'),
"M11 native pid file not written":('echo $$ > .app.pid\n',''),
"M12 status ignores the pid for llama":('    if pid_is .llama-server.pid "llama-server"; then\n      echo "  llama-server     : up on port ${llama_port} (pid','    if true; then\n      echo "  llama-server     : up on port ${llama_port} (pid'),
"M13 unknown --stop argument accepted":('    *) echo "Usage: ./start.sh --stop [--all]" >&2; exit 1 ;;','    *) ;;'),
}
def run():
    r=subprocess.run([".venv/bin/python","-m","pytest","tests/test_start_status_stop.py","-q","-x","-p","no:cacheprovider"],capture_output=True,text=True)
    return r.stdout.strip().splitlines()[-1]
try:
    for n,(a,b) in muts.items():
        assert a in o,n
        p.write_text(o.replace(a,b,1)); print(n,"->",run()); p.write_text(o)
finally: p.write_text(o)
