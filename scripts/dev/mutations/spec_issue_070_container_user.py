"""Spec for scripts/dev/mutation_check.py: #70 (container runs as uid 10001)."""

TESTS = ["tests/test_container_user.py"]
D, S, C = "Dockerfile", "app/db/session.py", ".github/workflows/ci.yml"
MUTATIONS = {
    "M1 USER removed": (D, "USER 10001:10001\n", ""),
    "M2 USER root": (D, "USER 10001:10001\n", "USER root\n"),
    "M3 USER after CMD": (D, "USER 10001:10001\n\n# Healthy", "\n# Healthy"),
    "M4 data dir not chowned": (
        D,
        "RUN mkdir -p /app/data && chown 10001:10001 /app/data",
        "RUN mkdir -p /app/data",
    ),
    "M5 uid drift in useradd": (D, "--uid 10001 --gid 10001", "--uid 10002 --gid 10001"),
    "M6 code chowned to app user": (D, "COPY app/ ./app/", "COPY --chown=10001:10001 app/ ./app/"),
    "M7 no writable check": (S, "        if not os.access(path.parent, os.W_OK | os.X_OK):", "        if False:"),
    "M8 message lacks the fix": (S, "chown -R 10001:10001 <host data directory>", "fix the permissions"),
    "M10 start.sh no longer creates data/": ("start.sh", "  mkdir -p data\n", ""),
    "M9 CI step removed": (C, '          test "$uid" != 0\n', ""),
}
