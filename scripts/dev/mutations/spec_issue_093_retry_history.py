"""Spec for scripts/dev/mutation_check.py: #93 (a retried failed turn stores its user message once)."""

TESTS = ["tests/test_undelivered_retry.py", "tests/test_failed_turn.py", "tests/test_persistence.py"]
G, D = "app/graph.py", "app/channels/dispatch.py"
MUTATIONS = {
    "M1 retry flag not passed": (D, "event.channel, event.user_id, agent_id, event.text, retry=retry", "event.channel, event.user_id, agent_id, event.text"),
    "M2 guard disabled": (G, "    if retry:\n        state = await graph.aget_state(config)", "    if False:\n        state = await graph.aget_state(config)"),
    "M3 any last message skipped, not only identical": (G, "and stored[-1].content == text:", "and True:"),
    "M4 skipped without checking it is a user message": (G, "isinstance(stored[-1], HumanMessage) and ", ""),
}
