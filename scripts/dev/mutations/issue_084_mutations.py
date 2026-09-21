import subprocess
L="app/logging_setup.py"
muts=[
("A always flatten (the regression)",L,"    if scrubbed != message:  # nothing to hide: the record is left exactly as it was\n        _replace_message(record, scrubbed)","    record.msg = scrubbed\n    record.args = None"),
("B structured path never checked",L,"        if formatted is not None and scrub(formatted) == formatted:\n            return","        if formatted is not None:\n            return"),
("C string arguments not scrubbed",L,"        record.args = tuple(scrub(a) if isinstance(a, str) else a for a in old_args)","        record.args = old_args"),
("D format string not scrubbed",L,"        record.msg = scrub(old_msg)\n        record.args","        record.args"),
("E flatten never done",L,"    record.msg = scrubbed\n    record.args = None\n\n\ndef _scrub_record","    return\n\n\ndef _scrub_record"),
]
for name,f,a,b in muts:
    orig=open(f).read()
    assert a in orig,name
    new=orig.replace(a,b,1); assert new!=orig,name
    open(f,"w").write(new)
    try:
        r=subprocess.run([".venv/bin/python","-m","pytest","tests/test_log_redaction.py","-q","--no-header","-p","no:cacheprovider","--deselect","tests/test_log_redaction.py::test_the_real_application_never_prints_a_token_shaped_secret"],capture_output=True,text=True)
        print(name,"->",r.stdout.strip().splitlines()[-1])
    finally:
        open(f,"w").write(orig)
