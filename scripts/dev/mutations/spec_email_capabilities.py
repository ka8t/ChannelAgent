"""Spec for scripts/dev/mutation_check.py: IMAP capabilities under Python 3.12 (found live 2026-09-21)."""

TESTS = ["tests/test_email_adapter.py"]
E = "app/channels/email.py"
MUTATIONS = {
    "M1 client list trusted as before": (E, "    caps = _capabilities(imap)\n", "    caps = getattr(imap, \"capabilities\", ())\n"),
    "M2 server never asked": (E, "    if not {\"MOVE\", \"UIDPLUS\"} & set(caps):\n        try:", "    if not caps:\n        try:"),
    "M3 capabilities not upper-cased": (E, "data[0].decode().upper().split()", "data[0].decode().split()"),
}
