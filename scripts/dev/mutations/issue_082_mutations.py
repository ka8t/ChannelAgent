import subprocess
L="app/logging_setup.py"; M="app/main.py"
muts=[
("M1 records not scrubbed at all",L,"    logging.setLogRecordFactory(factory)\n    _install_excepthooks()","    _install_excepthooks()"),
("M2 httpx left at INFO",L,'    for noisy in ("httpx", "httpcore"):\n        logging.getLogger(noisy).setLevel(logging.WARNING)\n',''),
("M3 token shape too narrow",L,"[A-Za-z0-9_-]{20,}","[A-Za-z0-9_-]{50,}"),
("M4 literal secrets not replaced",L,"    for secret in _secrets:\n        text = text.replace(secret, REDACTED)\n",""),
("M5 arguments not scrubbed",L,"    message = record.getMessage()  # may raise","    message = str(record.msg)  # may raise"),
("M6 traceback not scrubbed",L,"        record.exc_text = scrub(logging.Formatter().formatException(record.exc_info))","        pass"),
("M7 stack not scrubbed",L,"        record.stack_info = scrub(record.stack_info)","        pass"),
("M8 excepthook not installed",L,"    if not getattr(sys.excepthook, \"_redacting\", False):","    if False:"),
("M9 thread hook not installed",L,"    if not getattr(threading.excepthook, \"_redacting\", False):","    if False:"),
("M10 short secrets redacted",L,"MIN_SECRET_LENGTH = 8","MIN_SECRET_LENGTH = 1"),
("M11 bot token not among the secrets",L,"        settings.telegram_bot_token,\n",""),
("M12 old key not among the secrets",L,'        os.environ.get("OLD_ENCRYPTION_KEY"),\n',""),
("M13 main does not configure logging",M,"configure_logging()\nlogger","logger"),
("M14 configure_logging skips the scrubbing",L,"        logging.getLogger(noisy).setLevel(logging.WARNING)\n    install_redaction()","        logging.getLogger(noisy).setLevel(logging.WARNING)"),
]
for name,f,a,b in muts:
    orig=open(f).read()
    assert a in orig,name
    new=orig.replace(a,b,1); assert new!=orig,name
    open(f,"w").write(new)
    try:
        r=subprocess.run([".venv/bin/python","-m","pytest","tests/test_log_redaction.py","-q","--no-header","-p","no:cacheprovider"],capture_output=True,text=True)
        print(name,"->",r.stdout.strip().splitlines()[-1])
    finally:
        open(f,"w").write(orig)
