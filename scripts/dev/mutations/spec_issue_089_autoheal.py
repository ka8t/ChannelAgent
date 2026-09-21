"""Spec for scripts/dev/mutation_check.py: #89 (autoheal overlay)."""

TESTS = ["tests/test_autoheal_overlay.py"]
O = "docker-compose.autoheal.yml"
MUTATIONS = {
    "M1 application not labelled": (O, '      autoheal: "true"', '      other: "true"'),
    "M2 watcher acts on every container": (O, "AUTOHEAL_CONTAINER_LABEL: autoheal", "AUTOHEAL_CONTAINER_LABEL: all"),
    "M3 extra host mount": (O, "      - /var/run/docker.sock:/var/run/docker.sock", "      - /var/run/docker.sock:/var/run/docker.sock\n      - /:/host"),
    "M4 watcher not restarted": (O, "    restart: unless-stopped", "    restart: \"no\""),
    "M5 slow check interval": (O, 'AUTOHEAL_INTERVAL: "10"', 'AUTOHEAL_INTERVAL: "600"'),
    "M6 published port": (O, "    restart: unless-stopped\n    environment:", "    restart: unless-stopped\n    ports:\n      - \"80:80\"\n    environment:"),
}
