"""Private SQLite storage with versioned, backed-up migrations."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
from typing import Iterator


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PRIVATE_DIR = PROJECT_ROOT / "data" / "private"
DB_PATH = PRIVATE_DIR / "activities.sqlite3"
MIGRATION = Path(__file__).resolve().parent / "migrations" / "0001_initial.sql"
LATEST_VERSION = 2


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def secure_dir(path: Path) -> None:
    if path.is_symlink():
        raise RuntimeError("private path is a symlink")
    if path.exists():
        if not path.is_dir() or path.stat().st_mode & 0o077:
            raise RuntimeError("existing private directory has unsafe permissions")
        return
    path.mkdir(mode=0o700, parents=True)
    if path.stat().st_mode & 0o077:
        raise RuntimeError("could not create owner-only private directory")


def secure_file(path: Path) -> None:
    if path.is_symlink():
        raise RuntimeError("private file is a symlink")
    if path.exists():
        if not path.is_file() or path.stat().st_mode & 0o077:
            raise RuntimeError("existing private file has unsafe permissions")
        return
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    os.close(fd)


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute("PRAGMA journal_mode=DELETE")
    return connection


def backup_database(connection: sqlite3.Connection, private_dir: Path = PRIVATE_DIR) -> Path:
    backup_dir = private_dir / "backups"
    secure_dir(backup_dir)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = backup_dir / f"activities_{stamp}.sqlite3"
    secure_file(path)
    destination = _connect(path)
    try:
        connection.backup(destination)
    finally:
        destination.close()
    return path


@contextmanager
def open_database(private_dir: Path = PRIVATE_DIR, *, database_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    secure_dir(private_dir.parent)
    secure_dir(private_dir)
    path = database_path or private_dir / "activities.sqlite3"
    if path.parent.resolve() != private_dir.resolve():
        raise RuntimeError("database must be directly inside the project private directory")
    if database_path is not None and not path.is_file():
        raise RuntimeError("alternate database must be an existing restored copy")
    existed = path.exists() or path.is_symlink()
    secure_file(path)
    previous_umask = os.umask(0o077)
    try:
        connection = _connect(path)
    except BaseException:
        os.umask(previous_umask)
        raise
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version < LATEST_VERSION:
            if existed and path.stat().st_size > 0:
                backup_database(connection, private_dir)
            for next_version in range(version + 1, LATEST_VERSION + 1):
                migration = next(MIGRATION.parent.glob(f"{next_version:04d}_*.sql"))
                sql = migration.read_text(encoding="utf-8")
                connection.executescript(
                    "BEGIN IMMEDIATE;\n" + sql + "\n"
                    "INSERT INTO schema_migration(version, applied_at_utc) "
                    f"VALUES ({next_version}, datetime('now'));\n"
                    f"PRAGMA user_version={next_version};\nCOMMIT;"
                )
        if version > LATEST_VERSION:
            raise RuntimeError("database schema is newer than this program")
        yield connection
    finally:
        connection.close()
        os.umask(previous_umask)


def restore_to_new_file(backup: Path, private_dir: Path = PRIVATE_DIR) -> Path:
    secure_dir(private_dir.parent)
    secure_dir(private_dir)
    backup_dir = private_dir / "backups"
    if backup.is_symlink() or backup.parent.resolve() != backup_dir.resolve():
        raise RuntimeError("backup must be a local private backup file")
    if not backup.is_file() or backup.stat().st_mode & 0o077:
        raise RuntimeError("backup file is missing or permissions are unsafe")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    target = private_dir / f"activities_restored_{stamp}.sqlite3"
    secure_file(target)
    source_conn = sqlite3.connect(f"file:{backup}?mode=ro", uri=True)
    dest_conn = _connect(target)
    try:
        source_conn.backup(dest_conn)
        if dest_conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("restored database failed integrity check")
    finally:
        source_conn.close()
        dest_conn.close()
    return target
