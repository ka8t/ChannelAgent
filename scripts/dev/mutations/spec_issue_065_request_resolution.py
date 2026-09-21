"""Spec for scripts/dev/mutation_check.py: #65 (requests resolved, automated mail)."""

TESTS = [
    "tests/test_request_resolution.py",
    "tests/test_email_adapter.py",
    "tests/test_admin_api.py",
]
S, E = "app/admin/service.py", "app/channels/email.py"
_SEL = (
    "                    AccessRequest.external_id == external_id,\n"
    "                    AccessRequest.status == RequestStatus.PENDING,\n"
    "                )\n            )\n        )\n        .scalars()\n        .all()\n    )\n"
    "    for request in pending:"
)
MUTATIONS = {
    "M1 not resolved on identity creation": (
        S,
        "    await resolve_requests_for_identity(session, channel, external_id, actor=actor)\n"
        "    return identity",
        "    return identity",
    ),
    "M2 not resolved on grant": (
        S,
        "    await resolve_requests_for_identity(\n"
        "        session, identity.channel, identity.external_id, actor=actor\n    )\n"
        "    return permission",
        "    return permission",
    ),
    "M3 every pending request of the channel": (
        S,
        _SEL,
        _SEL.replace("                    AccessRequest.external_id == external_id,\n", ""),
    ),
    "M5 denied requests also approved": (
        S,
        _SEL,
        _SEL.replace("                    AccessRequest.status == RequestStatus.PENDING,\n", ""),
    ),
    "M6 resolved_by not set": (S, "        request.resolved_by = actor\n        await record_admin_event(", "        await record_admin_event("),
    "M7 Precedence ignored": (
        E,
        '    return str(msg.get("Precedence", "")).strip().lower() in ("bulk", "list", "junk")',
        "    return False",
    ),
    "M8 Auto-Submitted: no counts as automated": (E, '    if auto and auto != "no":', "    if auto:"),
    "M9 automated mail not filtered": (E, "                if _is_automated(msg):", "                if False:"),
    "M11 replies not marked": (E, '    msg["Auto-Submitted"] = "auto-replied"\n', ""),
    "M12 Auto-Submitted parameters not stripped": (
        E,
        'str(msg.get("Auto-Submitted", "")).split(";")[0].strip().lower()',
        'str(msg.get("Auto-Submitted", "")).strip().lower()',
    ),
}
