import subprocess
R="app/settings_rules.py"; S="start.sh"
muts=[
("M1 never quotes",R,"    return value if _SAFE_UNQUOTED.fullmatch(value) else f\"'{value}'\"","    return value"),
("M2 quotes everything",R,"    return value if _SAFE_UNQUOTED.fullmatch(value) else f\"'{value}'\"","    return f\"'{value}'\" if value else value"),
("M3 space counted safe",R,'_SAFE_UNQUOTED = re.compile(r"[A-Za-z0-9_./:@+,=%^\\[\\]-]*")','_SAFE_UNQUOTED = re.compile(r"[A-Za-z0-9_./:@+,=%^\\[\\] -]*")'),
("M4 ampersand counted safe",R,'_SAFE_UNQUOTED = re.compile(r"[A-Za-z0-9_./:@+,=%^\\[\\]-]*")','_SAFE_UNQUOTED = re.compile(r"[A-Za-z0-9_./:@+,=%^\\[\\]&-]*")'),
("M5 tilde counted safe",R,'_SAFE_UNQUOTED = re.compile(r"[A-Za-z0-9_./:@+,=%^\\[\\]-]*")','_SAFE_UNQUOTED = re.compile(r"[A-Za-z0-9_./:@+,=%^\\[\\]~-]*")'),
("M6 single quote allowed",R,'    if "\'" in value or "\\\\" in value:','    if "\\\\" in value:'),
("M7 backslash allowed",R,'    if "\'" in value or "\\\\" in value:','    if "\'" in value:'),
("M8 ${ allowed",R,'    if "${" in value:','    if False:'),
("M9 control characters allowed",R,"    if any(ord(c) < 32 or ord(c) == 127 for c in value):\n        return \"must be one line","    if False:\n        return \"must be one line"),
("M10 start.sh writes the raw value",S,'lines[i] = f"{key}={written}\\n"','lines[i] = f"{key}={value}\\n"'),
("M11 start.sh appends the raw value",S,'lines.append(f"{key}={written}\\n")','lines.append(f"{key}={value}\\n")'),
("M12 show-config keeps the quotes",S,'if len(value) >= 2 and value[0] == value[-1] and value[0] in "\'\\"":','if False:'),
("M13 key guard does not unquote",S,'if current.strip("\'\\"") != "":','if current != "":'),
("M14 double quotes used",R,"    return value if _SAFE_UNQUOTED.fullmatch(value) else f\"'{value}'\"","    return value if _SAFE_UNQUOTED.fullmatch(value) else f'\"{value}\"'"),
("M15 rules not loaded (silent)",S,"except ImportError as exc:","except ZeroDivisionError as exc:"),
]
for name,f,a,b in muts:
    orig=open(f).read()
    assert a in orig,name
    new=orig.replace(a,b,1); assert new!=orig,name
    open(f,"w").write(new)
    try:
        r=subprocess.run([".venv/bin/python","-m","pytest","tests/test_env_quoting.py","tests/test_settings_rules.py","tests/test_start_set_safety.py","-q","--no-header","-p","no:cacheprovider"],capture_output=True,text=True)
        print(name,"->",r.stdout.strip().splitlines()[-1])
    finally:
        open(f,"w").write(orig)
