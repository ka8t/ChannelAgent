import subprocess
muts=[
("M1 set_agent_active records nothing","app/admin/service.py",'action="agent.set_active",','action="agent.set_active_X",'),
("M2 actor ignored","app/admin/service.py","        actor=actor,\n        action=action,\n        target_type=target_type,\n        target_id=target_id,\n        details=json","        actor=\"x\",\n        action=action,\n        target_type=target_type,\n        target_id=target_id,\n        details=json"),
("M3 API rename without actor","app/api/routes.py","service.rename_agent(session, agent_id, body.name, actor=API_ACTOR)","service.rename_agent(session, agent_id, body.name)"),
("M4 API logs read not committed","app/api/routes.py","    await session.commit()  # a read of decrypted logs is itself recorded (#59)\n","    pass\n"),
("M5 console logs read not committed","app/admin/cli.py","        await session.commit()  # a read of decrypted logs is itself recorded (#59)\n","        pass\n"),
("M6 details stored in clear","app/db/models.py","details: Mapped[str | None] = mapped_column(EncryptedString, default=None)","details: Mapped[str | None] = mapped_column(String(2000), default=None)"),
("M7 address written to the event","app/admin/service.py",'details={"channel": channel.value, "identity_id": identity.id},','details={"channel": channel.value, "identity_id": identity.id, "identifier": identifier},'),
("M8 rekey forgets admin_events","app/admin/rekey.py",'    ("admin_events", "id", "details"),\n',''),
("M9 event of a refused delete still written","app/admin/service.py","    if logs and not purge:\n        raise UserHasHistoryError(user_id, agents, logs)","    if logs and not purge:\n        await record_admin_event(session, actor=actor, action='user.delete', target_type='user', target_id=user_id)\n        raise UserHasHistoryError(user_id, agents, logs)"),
("M10 two events for create_user","app/admin/service.py",'        action="user.create",','        action="user.create",\n        # dup\n'),
("M11 blank actor accepted","app/admin/service.py",'    if not actor or len(actor) > MAX_ACTOR_LENGTH:','    if len(actor) > MAX_ACTOR_LENGTH:'),
("M12 search keyword not recorded","app/admin/service.py",'for k, v in filters.items()\n                if v is not None\n            },\n            "results": len(found),\n        },\n    )\n    return found\n\n\nasync def _search_action_logs','for k, v in filters.items()\n                if v is not None and k != "keyword"\n            },\n            "results": len(found),\n        },\n    )\n    return found\n\n\nasync def _search_action_logs'),
]
import shutil
for name,f,a,b in muts:
    orig=open(f).read()
    assert a in orig,name
    new=orig.replace(a,b,1)
    if name.startswith("M10"):
        # real duplicate: call record twice
        new=orig.replace('    await record_admin_event(\n        session,\n        actor=actor,\n        action="user.create",','    await record_admin_event(session, actor=actor, action="user.create", target_type="user")\n    await record_admin_event(\n        session,\n        actor=actor,\n        action="user.create",',1)
        assert new!=orig
    assert new!=orig,name
    open(f,"w").write(new)
    try:
        r=subprocess.run([".venv/bin/python","-m","pytest","tests/test_admin_events.py","tests/test_admin_api.py","tests/test_rekey.py","-q","-x","--no-header","-p","no:cacheprovider"],capture_output=True,text=True)
        print(name,"->",r.stdout.strip().splitlines()[-1])
    finally:
        open(f,"w").write(orig)
