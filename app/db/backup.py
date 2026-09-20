"""Backup before migrating (#66).

`init_db()` runs `alembic upgrade head` at every startup, so starting the
application or the console can change the schema of the real database. A
migration that fails half-way, or that turns out to be wrong, would leave the
only copy modified. Before applying any migration to an existing SQLite file
that is behind head, this module copies it with SQLite's online backup API
(consistent even if something is writing), checks the copy, and keeps the
last few. If the copy cannot be made or does not check out, the migration does
not run.

Restore: stop the application, then copy the wanted file from
`<data dir>/backups/` over the database file.
"""

import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger("channelagent")

BACKUP_DIR_NAME = "backups"


class BackupError(RuntimeError):
    """The backup could not be made or verified: the migration must not run."""


def _current_revision(path: Path) -> str | None:
    """The Alembic revision stored in the file, or None when there is no
    version table (a fresh file, or a database from before Alembic).
    """
    con = sqlite3.connect(path)
    try:
        try:
            row = con.execute("select version_num from alembic_version").fetchone()
        except sqlite3.OperationalError:
            return None
        return row[0] if row else None
    finally:
        con.close()


def _has_tables(path: Path) -> bool:
    con = sqlite3.connect(path)
    try:
        count = con.execute("select count(*) from sqlite_master where type = 'table'")
        return count.fetchone()[0] > 0
    finally:
        con.close()


def _verify(source: Path, target: Path) -> None:
    """The copy opens, passes the integrity check and holds the same number of
    rows as the source in every table.
    """
    src, dst = sqlite3.connect(source), sqlite3.connect(target)
    try:
        if dst.execute("pragma integrity_check").fetchall() != [("ok",)]:
            raise BackupError(f"the backup {target.name} fails the integrity check")
        tables = [r[0] for r in src.execute("select name from sqlite_master where type = 'table'")]
        for table in tables:
            a = src.execute(f'select count(*) from "{table}"').fetchone()[0]
            b = dst.execute(f'select count(*) from "{table}"').fetchone()[0]
            if a != b:
                raise BackupError(f"the backup has {b} rows in {table}, the source has {a}")
    finally:
        src.close()
        dst.close()


def _prune(directory: Path, stem: str, keep: int) -> None:
    """Only migration backups are rotated: a "prerekey" copy is the way back
    from a key rotation and is never deleted automatically.
    """
    candidates = [p for p in directory.glob(f"{stem}-*.db") if "-prerekey-" not in p.name]
    for old in sorted(candidates)[:-keep]:
        old.unlink()
        logger.info("Removed the old migration backup %s", old.name)


def make_backup(path: Path, label: str) -> Path:
    """Copy `path` into `backups/` next to it with SQLite's online backup API,
    verify the copy, and return it. Raises BackupError (and leaves no bad copy)
    if it cannot be made or does not check out.
    """
    directory = path.parent / BACKUP_DIR_NAME
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    target = directory / f"{path.stem}-{label}-{stamp}.db"
    src = sqlite3.connect(path)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    except sqlite3.Error as exc:
        target.unlink(missing_ok=True)
        raise BackupError(f"could not back up {path.name}: {exc}") from exc
    finally:
        dst.close()
        src.close()
    try:
        _verify(path, target)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target


def backup_before_migration(database_url: str, head_revision: str, keep: int) -> Path | None:
    """Back up the database when a migration is about to change it.

    Returns the backup path, or None when nothing had to be done: not a SQLite
    file, no file yet, an empty file, already at head, or `keep` is 0.
    """
    from app.db.session import sqlite_file_path

    path = sqlite_file_path(database_url)
    if keep <= 0 or path is None or not path.exists() or path.stat().st_size == 0:
        return None
    current = _current_revision(path)
    if current == head_revision or (current is None and not _has_tables(path)):
        return None

    target = make_backup(path, current or "none")
    logger.info(
        "Backed up %s to %s before migrating from %s to %s",
        path.name,
        target,
        current or "no revision",
        head_revision,
    )
    _prune(target.parent, path.stem, keep)
    return target
