"""Tests for #34: ./start.sh --show-config and --set. Every run is in a
temporary directory holding a *copy* of start.sh, because the script resolves
its own directory from its path: running the real one from elsewhere would
still modify the real .env (this happened once).
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def sandbox(tmp_path):
    shutil.copy(REPO / "start.sh", tmp_path / "start.sh")
    shutil.copy(REPO / ".env.example", tmp_path / ".env.example")
    return tmp_path


def _run(sandbox: Path, *args: str):
    return subprocess.run(
        ["bash", "start.sh", *args], cwd=sandbox, capture_output=True, text=True, timeout=60
    )


def _example_keys() -> list[str]:
    keys = []
    for line in (REPO / ".env.example").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            keys.append(line.partition("=")[0])
    return keys


def _env(sandbox: Path) -> dict[str, str]:
    values = {}
    for line in (sandbox / ".env").read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key] = value
    return values


def test_show_config_creates_env_from_the_example_and_lists_every_variable(sandbox):
    result = _run(sandbox, "--show-config")
    assert result.returncode == 0, result.stderr
    assert (sandbox / ".env").exists()
    shown = [line.split()[0] for line in result.stdout.splitlines() if line.startswith("  ")]
    assert shown == _example_keys()
    assert len(shown) >= 25


@pytest.mark.parametrize(
    "key",
    [
        "ENCRYPTION_KEY",
        "API_SERVER_KEY",
        "TELEGRAM_BOT_TOKEN",
        "EMAIL_PASSWORD",
        "MATRIX_BOT_ACCESS_TOKEN",
    ],
)
def test_show_config_never_prints_a_secret_in_full(sandbox, key):
    secret = "SECRETVALUE-0123456789-abcdef"
    (sandbox / ".env").write_text((sandbox / ".env.example").read_text())
    assert _run(sandbox, "--set", f"{key}={secret}").returncode == 0
    out = _run(sandbox, "--show-config").stdout
    assert secret not in out, f"{key} is printed in clear"
    assert "SECR...(hidden)" in [
        w for line in out.splitlines() if key in line for w in line.split()
    ]


def test_show_config_shows_ordinary_values_and_marks_missing_ones(sandbox):
    _run(sandbox, "--set", "LLAMA_PORT=9999")
    out = _run(sandbox, "--show-config").stdout
    port_line = next(line for line in out.splitlines() if "LLAMA_PORT" in line)
    assert port_line.split() == ["LLAMA_PORT", "9999"]
    assert "(not set)" in next(line for line in out.splitlines() if "MODEL_FILE" in line)


def test_set_updates_an_existing_key_and_keeps_everything_else(sandbox):
    _run(sandbox, "--show-config")
    before = (sandbox / ".env").read_text().splitlines()
    result = _run(sandbox, "--set", "LLAMA_PORT=8123")
    assert result.returncode == 0
    after = (sandbox / ".env").read_text().splitlines()
    assert len(after) == len(before)
    changed = [(a, b) for a, b in zip(before, after, strict=True) if a != b]
    assert changed == [(next(a for a in before if a.startswith("LLAMA_PORT=")), "LLAMA_PORT=8123")]


def test_set_keeps_brackets_equals_signs_and_spaces_in_the_value(sandbox):
    assert _run(sandbox, "--set", "EMAIL_TRIGGER_TAG=[agent] a=b c").returncode == 0
    assert _env(sandbox)["EMAIL_TRIGGER_TAG"] == "[agent] a=b c"


def test_set_creates_env_when_it_is_missing(sandbox):
    assert not (sandbox / ".env").exists()
    assert _run(sandbox, "--set", "LLAMA_PORT=8123").returncode == 0
    assert _env(sandbox)["LLAMA_PORT"] == "8123"


def test_set_works_on_a_file_without_a_trailing_newline(sandbox):
    (sandbox / ".env").write_text("A=1")
    assert _run(sandbox, "--set", "LLAMA_PORT=7").returncode == 0
    assert (sandbox / ".env").read_text() == "A=1\nLLAMA_PORT=7\n"


@pytest.mark.parametrize("argument", ["", "NOEQUALSIGN"])
def test_set_without_key_equals_value_prints_usage_and_changes_nothing(sandbox, argument):
    _run(sandbox, "--show-config")
    before = (sandbox / ".env").read_text()
    result = _run(sandbox, "--set", argument) if argument else _run(sandbox, "--set")
    assert result.returncode == 1 and "Usage" in result.stderr
    assert (sandbox / ".env").read_text() == before


@pytest.mark.parametrize("argument", ["=value", "lower_case=1", "BAD KEY=1", "LLAMA-PORT=1"])
def test_set_refuses_an_invalid_variable_name_and_changes_nothing(sandbox, argument):
    _run(sandbox, "--show-config")
    before = (sandbox / ".env").read_text()
    result = _run(sandbox, "--set", argument)
    assert result.returncode == 1 and "not a valid variable name" in result.stderr
    assert (sandbox / ".env").read_text() == before


def test_set_refuses_a_key_the_application_does_not_know(sandbox):
    _run(sandbox, "--show-config")
    before = (sandbox / ".env").read_text()
    result = _run(sandbox, "--set", "LLAMA_PROT=9999")  # a typo of LLAMA_PORT
    assert result.returncode == 1 and "unknown variable" in result.stderr
    assert "LLAMA_PORT" in result.stderr, "it suggests the known names"
    assert (sandbox / ".env").read_text() == before
