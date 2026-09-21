"""Spec for scripts/dev/mutation_check.py: #85 (resolved requests, IntegrityError)."""

TESTS = [
    "tests/test_request_reopen.py",
    "tests/test_admin_notifications.py",
    "tests/test_admin_service.py",
]
S = "app/admin/service.py"
MUTATIONS = {
    "M2 denied is reopened with a notification": (
        S,
        "        return existing, False\n    req = AccessRequest",
        "        existing.status = RequestStatus.PENDING\n        return existing, True\n    req = AccessRequest",
    ),
    "M3 approved is not reopened": (S, "        if existing.status == RequestStatus.APPROVED:", "        if False:"),
    "M4 reopen keeps resolved_at": (S, "            existing.resolved_at = None\n            existing.resolved_by = None\n", ""),
    "M5 reopen keeps the old first message": (S, "            existing.first_message_text = message_text\n", ""),
    "M6 reopened without notification": (
        S,
        "            return existing, True\n        return existing, False",
        "            return existing, False\n        return existing, False",
    ),
}
