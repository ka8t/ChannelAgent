"""Run the targeted test files of each issue and print the last pytest line.

Usage: .venv/bin/python scripts/dev/tools/run_test_groups.py [OUT.json]
"""
import json
import subprocess
import sys
groups={
 "36":["test_admin_api","test_admin_service"],
 "37":["test_admin_api","test_agent"],
 "39":["test_log_search"],
 "40":["test_storage_overview"],
 "41":["test_admin_console","test_admin_cli"],
 "45":["test_logging"],
 "46":["test_admin_api","test_bootstrap","test_telegram_adapter","test_start_script"],
 "49":["test_persistence"],
 "50":["test_integrity"],
 "51":["test_failed_turn","test_email_adapter"],
 "52":["test_api_exposure"],
 "53":["test_admin_notifications"],
 "54":["test_agent_selection"],
 "55":["test_undecryptable"],
 "66":["test_migration_backup"],
 "68":["test_file_permissions"],
 "3":["test_persistence","test_agent","test_conversation_reset","test_failed_turn"],
}
out={}
for n,files in groups.items():
    r=subprocess.run([".venv/bin/python","-m","pytest",*[f"tests/{f}.py" for f in files],"-q","-p","no:cacheprovider","--no-header"],capture_output=True,text=True)
    out[n]=r.stdout.strip().splitlines()[-1]
    print(f"#{n}: {out[n]}")
if len(sys.argv) > 1:
    json.dump(out, open(sys.argv[1], "w"))
