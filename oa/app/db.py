"""SQLite 连接及幂等初始化；写操作在独立事务中串行校验业务约束。"""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "oa.sqlite3"


def database_path():
    return Path(os.getenv("OA_DB_PATH", str(DEFAULT_DB))).expanduser().resolve()


@contextmanager
def connection(path, *, write=False):
    db = sqlite3.connect(str(path), timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        if write:
            db.execute("BEGIN IMMEDIATE")
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connection(path) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE CHECK(length(trim(name)) BETWEEN 1 AND 80),
            enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
            head_user_id INTEGER UNIQUE REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            department_id INTEGER REFERENCES departments(id),
            is_admin INTEGER NOT NULL DEFAULT 0 CHECK(is_admin IN (0,1)),
            enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
            CHECK(is_admin = 1 OR department_id IS NOT NULL)
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            csrf_token TEXT NOT NULL,
            expires_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY,
            applicant_id INTEGER NOT NULL REFERENCES users(id),
            approval_department_id INTEGER NOT NULL REFERENCES departments(id),
            event_date TEXT NOT NULL,
            title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 200),
            content TEXT NOT NULL CHECK(length(trim(content)) BETWEEN 1 AND 10000),
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
            submitted_at TEXT NOT NULL,
            reviewer_id INTEGER REFERENCES users(id),
            reviewed_at TEXT,
            rejection_reason TEXT,
            CHECK(
                (status = 'pending' AND reviewer_id IS NULL AND reviewed_at IS NULL AND rejection_reason IS NULL)
                OR (status = 'approved' AND reviewer_id IS NOT NULL AND reviewed_at IS NOT NULL AND rejection_reason IS NULL)
                OR (status = 'rejected' AND reviewer_id IS NOT NULL AND reviewed_at IS NOT NULL AND rejection_reason IS NOT NULL AND length(trim(rejection_reason)) > 0)
            )
        );
        CREATE INDEX IF NOT EXISTS idx_applicant ON applications(applicant_id, id DESC);
        CREATE INDEX IF NOT EXISTS idx_approval ON applications(approval_department_id, status, id DESC);
        CREATE INDEX IF NOT EXISTS idx_session_user ON sessions(user_id);
        CREATE TRIGGER IF NOT EXISTS immutable_user_identity
        BEFORE UPDATE OF username, department_id, is_admin ON users
        WHEN NEW.username IS NOT OLD.username OR NEW.department_id IS NOT OLD.department_id OR NEW.is_admin IS NOT OLD.is_admin
        BEGIN SELECT RAISE(ABORT, '用户身份和部门不可变更'); END;
        CREATE TRIGGER IF NOT EXISTS immutable_department_head
        BEFORE UPDATE OF head_user_id ON departments
        WHEN OLD.head_user_id IS NOT NULL AND NEW.head_user_id IS NOT OLD.head_user_id
        BEGIN SELECT RAISE(ABORT, '不支持更换负责人'); END;
        CREATE TRIGGER IF NOT EXISTS valid_department_head
        BEFORE UPDATE OF head_user_id ON departments
        WHEN NEW.head_user_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM users WHERE id=NEW.head_user_id AND department_id=NEW.id AND enabled=1 AND is_admin=0
        )
        BEGIN SELECT RAISE(ABORT, '负责人必须是本部门启用的普通用户'); END;
        CREATE TRIGGER IF NOT EXISTS active_department_head
        BEFORE UPDATE OF enabled ON users
        WHEN NEW.enabled=0 AND EXISTS(SELECT 1 FROM departments WHERE head_user_id=NEW.id)
        BEGIN SELECT RAISE(ABORT, '现任负责人不能停用'); END;
        CREATE TRIGGER IF NOT EXISTS immutable_completed_application
        BEFORE UPDATE ON applications WHEN OLD.status != 'pending'
        BEGIN SELECT RAISE(ABORT, '已完成的审批不可修改'); END;
        """)
