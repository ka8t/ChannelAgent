"""Mutation check for #105 (model routing): one deliberate defect per new control,
tests/test_model_routing.py judged on whether it notices. Restores every file in
a finally. Run: .venv/bin/python scripts/dev/mutations/issue_105_mutations.py
"""

import subprocess

ROUTING = "app/admin/routing.py"
GRAPH = "app/graph.py"

muts = [
    (
        "A min_length lower bound removed",
        ROUTING,
        "if isinstance(value, bool) or not isinstance(value, int) or value < 1:",
        "if isinstance(value, bool) or not isinstance(value, int):",
    ),
    (
        "B match_type allow-list skipped",
        ROUTING,
        "if match_type not in MATCH_TYPES:",
        "if False:",
    ),
    (
        "C a rule may have no model",
        ROUTING,
        "    model = _clean_model(rule.get(\"model\"))\n    if model is None:\n        raise "
        'InvalidInputError("A rule needs a model")',
        '    model = _clean_model(rule.get("model")) or "unspecified"',
    ),
    (
        "D rule count cap removed",
        ROUTING,
        "if not isinstance(rules, list) or len(rules) > MAX_RULES:",
        "if not isinstance(rules, list):",
    ),
    (
        "E model_ctx_sizes lower bound removed",
        ROUTING,
        "if model is None or isinstance(size, bool) or not isinstance(size, int) or size < 1:",
        "if model is None or isinstance(size, bool) or not isinstance(size, int):",
    ),
    (
        "F fallback attempted even when the default itself failed",
        GRAPH,
        "if exc.response.status_code == 400 and model and default_model and model != default_model:",
        "if exc.response.status_code == 400 and model and default_model:",
    ),
    (
        "G per-model ctx size no longer capped by LLAMA_CTX_SIZE",
        GRAPH,
        "ctx_size = min(agent.get(\"ctx_size\") or settings.llama_ctx_size, settings.llama_ctx_size)",
        'ctx_size = agent.get("ctx_size") or settings.llama_ctx_size',
    ),
    (
        "H rules never consulted, only the agent's own model",
        GRAPH,
        "model = agent.model or routing_service.select_model(\n            text=text, rules=routing[\"rules\"], "
        'default_model=routing["default_model"]\n        )',
        "model = agent.model",
    ),
    (
        "I explicit agent model loses to a matching rule",
        GRAPH,
        'model = agent.model or routing_service.select_model(\n            text=text, rules=routing["rules"], '
        'default_model=routing["default_model"]\n        )',
        'model = routing_service.select_model(\n            text=text, rules=routing["rules"], '
        'default_model=routing["default_model"]\n        ) or agent.model',
    ),
]

for name, f, a, b in muts:
    orig = open(f).read()
    assert a in orig, f"{name}: pattern not found in {f}"
    new = orig.replace(a, b, 1)
    assert new != orig, name
    open(f, "w").write(new)
    try:
        r = subprocess.run(
            [".venv/bin/python", "-m", "pytest", "tests/test_model_routing.py", "-q",
             "--no-header", "-p", "no:cacheprovider"],
            capture_output=True, text=True,
        )
        print(name, "->", r.stdout.strip().splitlines()[-1])
    finally:
        open(f, "w").write(orig)
