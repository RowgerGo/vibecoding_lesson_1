"""本地管理命令：python -m app.cli create-admin --username admin。"""

import argparse
import getpass
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .common import password_hash
from .db import connect, initialize


def main():
    parser = argparse.ArgumentParser(description="伯乐直聘本地管理")
    parser.add_argument("command", choices=["create-admin"])
    parser.add_argument("--username", required=True)
    args = parser.parse_args()
    username = args.username.strip()
    if not username or len(username) > 40:
        parser.error("用户名不能为空且最多 40 个字符")
    password = getpass.getpass("管理员密码（8～128 个字符）：")
    if not 8 <= len(password) <= 128:
        parser.error("密码长度需为 8～128 个字符")
    if password != getpass.getpass("再次输入密码："):
        parser.error("两次密码不一致")
    data_dir = Path(os.environ.get("BL_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
    database = initialize(data_dir)
    try:
        with connect(database) as conn:
            conn.execute("INSERT INTO users(username,password_hash,role,created_at) VALUES(?,?,'admin',?)",
                         (username, password_hash(password), datetime.now(timezone.utc).timestamp()))
    except sqlite3.IntegrityError:
        parser.error("用户名已存在，未覆盖已有账号")
    print(f"管理员 {username} 创建成功")


if __name__ == "__main__":
    main()
