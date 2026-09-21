import subprocess, pathlib
F={"d":pathlib.Path("app/channels/dispatch.py"),"e":pathlib.Path("app/channels/email.py"),"s":pathlib.Path("app/admin/service.py")}
orig={k:v.read_text() for k,v in F.items()}
muts={
 "M1 retry always reruns the turn":("d","    if retry:\n        pending = await find_undelivered_answer(","    if False:\n        pending = await find_undelivered_answer("),
 "M2 redelivery not marked ok":("d","    pending.status = ActionStatus.OK\n","    pass\n"),
 "M3 delivery failure reported as FAILED":("d","        outbound.status = ActionStatus.FAILED\n        await session.commit()\n        return DispatchOutcome.UNDELIVERED","        outbound.status = ActionStatus.FAILED\n        await session.commit()\n        return DispatchOutcome.FAILED"),
 "M4 redelivery failure reported OK":("d","            \"Delivering the kept reply to %s/%s failed again\", event.channel.value, event.user_id\n        )\n        return DispatchOutcome.UNDELIVERED","            \"Delivering the kept reply to %s/%s failed again\", event.channel.value, event.user_id\n        )\n        return DispatchOutcome.OK"),
 "M5 apology may be redelivered":("d","not_answers=(APOLOGY_MESSAGE, NO_REPLY_NOTE),","not_answers=(),"),
 "M6 lookup ignores status":("s","        or answer.status != ActionStatus.FAILED\n",""),
 "M7 lookup ignores the user":("s","                ActionLog.user_id == user_id,\n                ActionLog.agent_id == agent_id,\n                ActionLog.channel == channel,\n                ActionLog.direction == Direction.INBOUND,","                ActionLog.agent_id == agent_id,\n                ActionLog.channel == channel,\n                ActionLog.direction == Direction.INBOUND,"),
 "M8 email does not count UNDELIVERED":("e","outcome in (DispatchOutcome.FAILED, DispatchOutcome.UNDELIVERED)","outcome is DispatchOutcome.FAILED"),
 "M9 first outbound after inbound ignored (any outbound)":("s","                ActionLog.id > entry.id,\n","")
}
def run():
    r=subprocess.run([".venv/bin/python","-m","pytest","tests/test_undelivered_retry.py","tests/test_failed_turn.py","tests/test_email_adapter.py","-q","-p","no:cacheprovider"],capture_output=True,text=True)
    return r.stdout.strip().splitlines()[-1]
try:
    for n,(f,a,b) in muts.items():
        assert a in orig[f],n
        F[f].write_text(orig[f].replace(a,b,1)); print(n,"->",run()); F[f].write_text(orig[f])
finally:
    for k,v in F.items(): v.write_text(orig[k])
