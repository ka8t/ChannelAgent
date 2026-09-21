import subprocess, pathlib
p = pathlib.Path("app/graph.py"); orig = p.read_text()
muts = {
 "M1 no trimming": ('    return kept or messages[-1:]', '    return messages'),
 "M2 no fallback": ('    return kept or messages[-1:]', '    return kept'),
 "M3 start_on removed": ('        start_on="human",\n', ''),
 "M4 keeps the oldest": ('strategy="last"', 'strategy="first"'),
 "M5 share 1.0": ('HISTORY_CONTEXT_SHARE = 0.75', 'HISTORY_CONTEXT_SHARE = 1.0'),
 "M6 window not used": ('convert_to_openai_messages(window)', 'convert_to_openai_messages(state["messages"])'),
 "M7 max_tokens x10": ('max_tokens=budget', 'max_tokens=budget * 10'),
}
try:
    for name,(a,b) in muts.items():
        assert a in orig, name
        p.write_text(orig.replace(a,b,1))
        r = subprocess.run([".venv/bin/python","-m","pytest","tests/test_history_window.py","-q","-x","-p","no:cacheprovider"],capture_output=True,text=True)
        print(name, "->", r.stdout.strip().splitlines()[-1])
finally:
    p.write_text(orig)
