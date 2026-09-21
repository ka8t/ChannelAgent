import subprocess
R="app/settings_rules.py"; S="start.sh"; D="app/api/deps.py"
muts=[
("M1 no port upper bound",R,"not 1 <= int(value) <= 65535","not 1 <= int(value) <= 10**9"),
("M2 port 0 accepted",R,"not 1 <= int(value) <= 65535","not 0 <= int(value) <= 65535"),
("M3 posint accepts 0",R,'not _UINT.fullmatch(value) or int(value) < 1','not _UINT.fullmatch(value)'),
("M4 host with underscore",R,'r"(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?"','r"(?=.{1,253}$)[A-Za-z0-9_]([A-Za-z0-9_-]{0,61}[A-Za-z0-9_])?"'),
("M5 bind address as a host",R,'"API_BIND_ADDRESS": "ip"','"API_BIND_ADDRESS": "host"'),
("M6 url accepts ftp",R,'parsed.scheme in ("http", "https")','parsed.scheme in ("http", "https", "ftp")'),
("M7 any database url",R,'if not value.startswith("sqlite+aiosqlite://"):','if False:'),
("M8 api key unchecked",R,'"API_SERVER_KEY": "api_key"','"API_SERVER_KEY": "free"'),
("M9 loose Fernet length",R,'_FERNET = re.compile(r"[A-Za-z0-9_-]{43}=")','_FERNET = re.compile(r"[A-Za-z0-9_-]{30,60}=?")'),
("M10 nothing required",R,"REQUIRED = frozenset(","REQUIRED = frozenset() and frozenset("),
("M11 shell characters allowed",R,'SHELL_UNSAFE = frozenset(" \\t&;|<>()$`\'\\"\\\\")','SHELL_UNSAFE = frozenset()'),
("M12 control characters allowed",R,"if any(ord(c) < 32 or ord(c) == 127 for c in value):","if False:"),
("M13 message echoes the value",R,'    reason = validate(key, sys.stdin.read())\n    if reason:\n        print(f"{key} was NOT changed: the value {reason}", file=sys.stderr)','    val = sys.stdin.read()\n    reason = validate(key, val)\n    if reason:\n        print(f"{key} was NOT changed: the value {reason} (got {val})", file=sys.stderr)'),
("M14 tag may be non-ASCII",R,"value.strip() and value.isascii() and '\"' not in value","value.strip() and '\"' not in value"),
("M15 folder may hold wildcards",R,"not any(c in value for c in '\"\\\\*%')","not any(c in value for c in '\"\\\\')"),
("M16 start.sh skips the rules",S,'if check.returncode != 0:','if False:'),
("M17 start.sh runs a different module",S,'"app/settings_rules.py", key]','"app/nonexistent_rules.py", key]'),
("M18 token needs no digits",R,'_TELEGRAM_TOKEN = re.compile(r"[0-9]{5,}:[A-Za-z0-9_-]{20,}")','_TELEGRAM_TOKEN = re.compile(r".+")'),
("M19 uint accepts a minus sign",R,'_UINT = re.compile(r"[0-9]{1,9}")','_UINT = re.compile(r"-?[0-9]{1,9}")'),
("M20 API keeps its own copy of the rule",D,"from app.settings_rules import MIN_API_KEY_LENGTH, api_key_is_acceptable  # noqa: F401","from app.settings_rules import MIN_API_KEY_LENGTH  # noqa: F401\n\n\ndef api_key_is_acceptable(key):\n    return bool(key) and len(key) >= 16"),
("M21 unknown kind silently accepted",R,'raise ValueError(f"unknown rule kind {kind!r}")','return None'),
]
for name,f,a,b in muts:
    orig=open(f).read()
    assert a in orig,name
    new=orig.replace(a,b,1); assert new!=orig,name
    open(f,"w").write(new)
    try:
        r=subprocess.run([".venv/bin/python","-m","pytest","tests/test_settings_rules.py","tests/test_api_auth_hardening.py","-q","--no-header","-p","no:cacheprovider"],capture_output=True,text=True)
        print(name,"->",r.stdout.strip().splitlines()[-1])
    finally:
        open(f,"w").write(orig)
