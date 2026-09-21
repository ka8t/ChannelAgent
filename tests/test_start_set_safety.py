"""Tests for #74: `start.sh --set` can never silently destroy access to the
data. A non-empty ENCRYPTION_KEY is never overwritten (only the rotation tool
changes it), an empty one only accepts a valid Fernet key, and every
successful `--set` first keeps the previous .env as .env.bak (mode 600).
"""

import base64
import hashlib
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

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


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _key() -> str:
    return Fernet.generate_key().decode()


def _with_key(sandbox: Path, key: str) -> None:
    lines = (sandbox / ".env.example").read_text().splitlines()
    out = [f"ENCRYPTION_KEY={key}" if ln.startswith("ENCRYPTION_KEY=") else ln for ln in lines]
    (sandbox / ".env").write_text("\n".join(out) + "\n")
    (sandbox / ".env").chmod(0o600)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


# --- a key already in place is never overwritten ---


def test_set_refuses_to_replace_an_existing_encryption_key(sandbox):
    current, other = _key(), _key()
    _with_key(sandbox, current)
    before = _sha(sandbox / ".env")
    result = _run(sandbox, "--set", f"ENCRYPTION_KEY={other}")
    assert result.returncode != 0
    assert _sha(sandbox / ".env") == before
    assert not (sandbox / ".env.bak").exists(), "a refused command changes nothing at all"
    assert "rotation" in result.stderr.lower()
    assert "rekey" in result.stderr
    for secret in (current, other):
        assert secret not in result.stdout + result.stderr


def test_set_refuses_even_to_write_the_same_key_again(sandbox):
    current = _key()
    _with_key(sandbox, current)
    before = _sha(sandbox / ".env")
    result = _run(sandbox, "--set", f"ENCRYPTION_KEY={current}")
    assert result.returncode != 0 and _sha(sandbox / ".env") == before


def test_set_refuses_to_blank_an_existing_encryption_key(sandbox):
    _with_key(sandbox, _key())
    before = _sha(sandbox / ".env")
    result = _run(sandbox, "--set", "ENCRYPTION_KEY=")
    assert result.returncode != 0 and _sha(sandbox / ".env") == before


# --- an empty key only accepts a valid Fernet key ---


def test_set_accepts_a_valid_key_when_none_is_set(sandbox):
    (sandbox / ".env").write_text((sandbox / ".env.example").read_text())
    (sandbox / ".env").chmod(0o600)
    key = _key()
    result = _run(sandbox, "--set", f"ENCRYPTION_KEY={key}")
    assert result.returncode == 0, result.stderr
    assert f"ENCRYPTION_KEY={key}\n" in (sandbox / ".env").read_text()
    assert key not in result.stdout + result.stderr, "the key is never echoed"


def _invalid_keys() -> dict[str, str]:
    good = _key()
    raw = base64.urlsafe_b64decode(good)
    return {
        "not base64 at all": "notafernetkey",
        "31 bytes": base64.urlsafe_b64encode(raw[:31]).decode(),
        "33 bytes": base64.urlsafe_b64encode(raw + b"x").decode(),
        "hex digest": hashlib.sha256(b"x").hexdigest(),
        "standard alphabet": base64.b64encode(b"\xfb" * 32).decode(),
        "with a space": good[:10] + " " + good[11:],
        "quoted": f'"{good}"',
    }


@pytest.mark.parametrize("label", list(_invalid_keys()))
def test_set_refuses_an_invalid_key_when_none_is_set(sandbox, label):
    (sandbox / ".env").write_text((sandbox / ".env.example").read_text())
    (sandbox / ".env").chmod(0o600)
    before = _sha(sandbox / ".env")
    result = _run(sandbox, "--set", f"ENCRYPTION_KEY={_invalid_keys()[label]}")
    assert result.returncode != 0, label
    assert _sha(sandbox / ".env") == before
    assert not (sandbox / ".env.bak").exists()


def test_set_creates_env_and_accepts_a_key_when_there_is_no_env_yet(sandbox):
    key = _key()
    result = _run(sandbox, "--set", f"ENCRYPTION_KEY={key}")
    assert result.returncode == 0, result.stderr
    assert f"ENCRYPTION_KEY={key}\n" in (sandbox / ".env").read_text()


# --- every successful --set keeps the previous .env ---


def test_a_successful_set_keeps_the_previous_env_as_a_private_backup(sandbox):
    _with_key(sandbox, _key())
    previous = (sandbox / ".env").read_text()
    before = os.umask(0o022)
    try:
        result = _run(sandbox, "--set", "LLAMA_PORT=9191")
    finally:
        os.umask(before)
    assert result.returncode == 0, result.stderr
    assert (sandbox / ".env.bak").read_text() == previous
    assert _mode(sandbox / ".env.bak") == 0o600
    assert ".env.bak" in result.stdout
    assert "LLAMA_PORT=9191" in (sandbox / ".env").read_text()


def test_the_backup_is_one_generation_the_state_before_the_last_set(sandbox):
    _with_key(sandbox, _key())
    _run(sandbox, "--set", "LLAMA_PORT=9191")
    after_first = (sandbox / ".env").read_text()
    _run(sandbox, "--set", "LLAMA_PORT=9292")
    assert (sandbox / ".env.bak").read_text() == after_first


def test_the_backup_can_undo_a_bad_edit(sandbox):
    _with_key(sandbox, _key())
    original = (sandbox / ".env").read_text()
    _run(sandbox, "--set", "LLAMA_PORT=9191")
    shutil.copy(sandbox / ".env.bak", sandbox / ".env")
    assert (sandbox / ".env").read_text() == original


def test_an_unknown_variable_leaves_no_backup(sandbox):
    _with_key(sandbox, _key())
    before = _sha(sandbox / ".env")
    result = _run(sandbox, "--set", "NOT_A_SETTING=1")
    assert result.returncode != 0
    assert _sha(sandbox / ".env") == before
    assert not (sandbox / ".env.bak").exists()


def test_the_backup_is_git_ignored():
    ignored = (REPO / ".gitignore").read_text().splitlines()
    assert ".env.bak" in ignored or ".env.*" in ignored or ".env*" in ignored
    result = subprocess.run(
        ["git", "check-ignore", "-q", ".env.bak"], cwd=REPO, capture_output=True
    )
    assert result.returncode == 0


def test_show_config_still_masks_the_key(sandbox):
    key = _key()
    _with_key(sandbox, key)
    result = _run(sandbox, "--show-config")
    assert result.returncode == 0
    assert key not in result.stdout + result.stderr
