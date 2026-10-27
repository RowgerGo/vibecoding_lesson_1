"""数据库初始化及事务；每次业务操作使用独立连接。"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin','company','seeker')),
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
    name TEXT NOT NULL, normalized_name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
    csrf TEXT NOT NULL, expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY, name TEXT NOT NULL,
    normalized_name TEXT NOT NULL UNIQUE,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1))
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY, company_id INTEGER NOT NULL REFERENCES companies(id),
    position_id INTEGER NOT NULL REFERENCES positions(id),
    description TEXT NOT NULL, email TEXT NOT NULL,
    is_open INTEGER NOT NULL DEFAULT 1 CHECK(is_open IN (0,1)),
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES jobs(id),
    seeker_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL DEFAULT '',
    original_filename TEXT NOT NULL, stored_filename TEXT NOT NULL UNIQUE,
    created_at REAL NOT NULL, viewed_at REAL,
    UNIQUE(job_id,seeker_id)
);
CREATE TABLE IF NOT EXISTS invitations (
    id INTEGER PRIMARY KEY, application_id INTEGER NOT NULL REFERENCES applications(id),
    token TEXT NOT NULL UNIQUE, created_at REAL NOT NULL, expires_at REAL NOT NULL,
    revoked_at REAL, used_at REAL
);
CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY, invitation_id INTEGER NOT NULL UNIQUE REFERENCES invitations(id),
    name TEXT NOT NULL, phone TEXT NOT NULL, scheduled_at REAL NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS jobs_company ON jobs(company_id);
CREATE INDEX IF NOT EXISTS applications_job ON applications(job_id);
CREATE INDEX IF NOT EXISTS applications_seeker ON applications(seeker_id);
CREATE INDEX IF NOT EXISTS invitations_application ON invitations(application_id,id);
"""


@contextmanager
def connect(path: Path):
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        # 写入先取得锁，确保关闭招聘、投递、邀请重发及预约的检查和写入原子化。
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize(data_dir: Path):
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "uploads").mkdir(exist_ok=True)
    path = data_dir / "platform.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SCHEMA)
    return path
