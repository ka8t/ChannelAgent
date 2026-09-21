import subprocess
muts=[
("M1 agent filter ignored","app/admin/service.py","        agent_query = agent_query.where(Agent.id == agent_id)\n","        pass\n"),
("M2 agent ownership not checked","app/admin/service.py","        if agent is None or agent.user_id != user_id:\n            raise AgentNotFoundError(f\"No agent {agent_id} for user {user_id}\")\n    from app.graph import delete_threads, threads_with_history","        pass\n    from app.graph import delete_threads, threads_with_history"),
("M3 no event","app/admin/service.py",'action="conversation.reset",','action="conversation.reset_X",'),
("M4 nothing deleted","app/admin/service.py","    await delete_threads(thread_ids)\n    await record_admin_event(","    await record_admin_event("),
("M5 count = all slots","app/admin/service.py","    threads = await threads_with_history(thread_ids)\n","    threads = len(thread_ids)\n"),
("M6 hint on every failure","app/channels/dispatch.py",'if isinstance(exc, ValueError) and "decrypt" in str(exc).lower():','if True:'),
("M7 hint text without the console remedy","app/channels/dispatch.py","console, Users > reset-conversation, or ","the console, or "),
("M8 console ignores the agent id","app/admin/cli.py","session, user_id, agent_id, actor=CONSOLE_ACTOR\n            )\n            await session.commit()\n            print(f\"Reset","session, user_id, None, actor=CONSOLE_ACTOR\n            )\n            await session.commit()\n            print(f\"Reset"),
("M9 API ignores the agent id","app/api/routes.py","service.reset_conversation(session, user_id, agent_id, actor=API_ACTOR)","service.reset_conversation(session, user_id, None, actor=API_ACTOR)"),
("M10 API without actor","app/api/routes.py","service.reset_conversation(session, user_id, agent_id, actor=API_ACTOR)","service.reset_conversation(session, user_id, agent_id)"),
("M11 unreadable checkpoint not counted","app/graph.py","        except Exception:\n            found += 1\n    return found","        except Exception:\n            pass\n    return found"),
]
for name,f,a,b in muts:
    orig=open(f).read()
    assert a in orig,name
    new=orig.replace(a,b,1)
    assert new!=orig,name
    open(f,"w").write(new)
    try:
        r=subprocess.run([".venv/bin/python","-m","pytest","tests/test_conversation_reset.py","-q","--no-header","-p","no:cacheprovider"],capture_output=True,text=True)
        print(name,"->",r.stdout.strip().splitlines()[-1])
    finally:
        open(f,"w").write(orig)
