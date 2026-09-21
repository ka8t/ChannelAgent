import subprocess
M="app/main.py"; R="app/admin/restore.py"
muts=[
("S1 failures not caught",M,"    except (Exception, SystemExit):","    except ZeroDivisionError:"),
("S2 SystemExit not caught (uvicorn bind failure)",M,"    except (Exception, SystemExit):","    except Exception:"),
("S3 shutdown swallowed as a failure",M,"    except (Exception, SystemExit):","    except (Exception, SystemExit, asyncio.CancelledError):"),
("S4 no fix hint in the message",M,'            "%s stopped and will stay stopped; the other components keep running. %s",\n            name,\n            hint,','            "%s stopped and will stay stopped; the other components keep running.",\n            name,'),
("S5 traceback dropped",M,"            exc_info=True,\n",""),
("S6 exit code 0 when all stopped",M,"            return 1\n    finally:","            return 0\n    finally:"),
("S7 no message when all stopped",M,'            logger.error("Every component has stopped (see the errors above): exiting.")\n',''),
("S8 API not supervised",M,'                    "Admin API",\n                    "Check API_SERVER_PORT (already in use?) and API_SERVER_HOST.",\n                    uvicorn.Server(config).serve(),','                    "Admin API",\n                    "Check API_SERVER_PORT (already in use?) and API_SERVER_HOST.",\n                    _raise(uvicorn.Server(config).serve()),'),
("R1 docker check removed",R,'    if shutil.which("docker"):','    if False:'),
("R2 llama container blocks the restore",R,'app_containers = [n for n in out if "llama" not in n]','app_containers = list(out)'),
]
for name,f,a,b in muts:
    orig=open(f).read()
    assert a in orig,name
    new=orig.replace(a,b,1); assert new!=orig,name
    if name.startswith("S8"):
        new=new.replace("async def main() -> int:","async def _raise(coro):\n    return await coro\n\n\nasync def main() -> int:",1)
    open(f,"w").write(new)
    try:
        t=["tests/test_supervision.py"] if name[0]=="S" else ["tests/test_restore.py"]
        r=subprocess.run([".venv/bin/python","-m","pytest",*t,"-q","-x","--no-header","-p","no:cacheprovider","--deselect","tests/test_supervision.py::test_the_real_process_keeps_the_api_up_when_telegram_rejects_its_token","--deselect","tests/test_supervision.py::test_the_real_process_exits_non_zero_when_its_only_component_fails"],capture_output=True,text=True)
        print(name,"->",r.stdout.strip().splitlines()[-1])
    finally:
        open(f,"w").write(orig)
