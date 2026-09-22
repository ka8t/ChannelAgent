"""Mutation check of #110 (2026-09-21): applies each mutation, runs the targeted tests, restores the file.
Run from the repository root: .venv/bin/python scripts/dev/mutations/issue_110_2026-09-21.py
"""
import subprocess, re
S="app/admin/service.py"; G="app/graph.py"; R="app/api/routes.py"; SC="app/api/schemas.py"; M="app/db/models.py"; K="app/admin/rekey.py"
MUT=[
 ("memory mode not validated (service)",S,'    if value not in MEMORY_MODES:','    if False:'),
 ("memory mode any string (schema)",SC,'MemoryMode = Literal["off", "ondemand", "always", "search"]','MemoryMode = str'),
 ("tool names not validated",S,"        if not isinstance(item, str) or not _TOOL_NAME.fullmatch(item):","        if False:"),
 ("tools not de-duplicated",S,"        if item not in seen:","        if True:"),
 ("tools count not limited",S,"    if not isinstance(value, list) or len(value) > MAX_TOOLS:","    if not isinstance(value, list):"),
 ("model name not validated",S,"    if not isinstance(value, str) or not _MODEL_NAME.fullmatch(value.strip()):","    if False:"),
 ("prompt length not limited",S,"    if len(value) > MAX_SYSTEM_PROMPT_LENGTH:","    if False:"),
 ("unknown settings ignored",S,"    if unknown:","    if False:"),
 ("empty prompt kept as empty text",S,"    return value or None\n","    return value\n"),
 ("prompt not sent to the engine",G,"        if prefix:\n            sent = [SystemMessage(content=prefix), *window]","        if False:\n            sent = [SystemMessage(content=prefix), *window]"),
 ("model not sent to the engine",G,'    extra = {"model": model} if model else {}','    extra = {}'),
 ("prompt not counted in the budget",G,"        room = budget - _prefix_cost(counter, _prefix(system_prompt, summary))\n        window = window_messages(messages, max(room, 1), counter)\n        dropped","        room = budget - _prefix_cost(counter, _prefix(None, summary))\n        window = window_messages(messages, max(room, 1), counter)\n        dropped"),
 ("prompt and summary in two messages",G,'    return "\\n\\n".join(parts)','    return parts[-1] if parts else ""'),
 ("settings read once and cached",G,"    _agent_settings.set(","    _agent_settings.set(_agent_settings.get() or "),
 ("prompt returned to everyone",R,"        system_prompt=agent.system_prompt if principal.scope >= Scope.ADMIN else None,","        system_prompt=agent.system_prompt,"),
 ("partial update sets every field",R,"    settings = body.model_dump(include=body.model_fields_set & set(service.CONFIG_FIELDS))","    settings = body.model_dump(include=set(service.CONFIG_FIELDS))"),
 ("prompt stored in clear",M,"    system_prompt: Mapped[str | None] = mapped_column(EncryptedString, default=None)","    system_prompt: Mapped[str | None] = mapped_column(String, default=None)"),
 ("prompt not in the rekey list",K,'    ("agents", "id", "system_prompt"),\n',""),
 ("prompt in the audit event",S,'    details: dict = {"fields": sorted(cleaned)}','    details: dict = {"fields": sorted(cleaned), "system_prompt": cleaned.get("system_prompt")}'),
]
T=["tests/test_agent_config.py","tests/test_admin_events.py"]
for name,path,old,new in MUT:
    src=open(path).read()
    if old not in src: print(name,": PATTERN NOT FOUND"); continue
    open(path,"w").write(src.replace(old,new,1))
    try:
        r=subprocess.run([".venv/bin/python","-m","pytest",*T,"-q","--no-header","-p","no:cacheprovider"],capture_output=True,text=True,timeout=300)
        failed=sorted({f.split('[')[0] for f in re.findall(r"^FAILED tests/\S+::(\S+)",r.stdout,re.M)})
        print(f"{name}: {len(failed)} failed -> {', '.join(failed)[:85]}")
    except subprocess.TimeoutExpired: print(name,"TIMEOUT")
    finally: open(path,"w").write(src)
