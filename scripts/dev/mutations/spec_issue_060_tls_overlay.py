"""Spec for scripts/dev/mutation_check.py: #60 (TLS proxy overlay)."""

TESTS = ["tests/test_tls_overlay.py"]
O, C = "docker-compose.tls.yml", "docker/Caddyfile"
MUTATIONS = {
    "M1 published on all interfaces": (O, "${TLS_BIND_ADDRESS:-127.0.0.1}:", "${TLS_BIND_ADDRESS:-0.0.0.0}:"),
    "M2 plain http port also published": (
        O,
        '      - "${TLS_BIND_ADDRESS:-127.0.0.1}:${TLS_PORT:-8443}:8443"',
        '      - "${TLS_BIND_ADDRESS:-127.0.0.1}:${TLS_PORT:-8443}:8443"\n      - "80:80"',
    ),
    "M3 no tls (comment mentions it too: tests must read directives)": (C, "\ttls internal\n", ""),
    "M4 wrong upstream": (C, "reverse_proxy channelagent:", "reverse_proxy localhost:"),
    "M5 caddyfile writable": (O, "/etc/caddy/Caddyfile:ro", "/etc/caddy/Caddyfile"),
    "M6 no persistent data": (O, "      - tls_proxy_data:/data\n", ""),
}
