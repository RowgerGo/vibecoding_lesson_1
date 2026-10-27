"""使用 python -m app.cli init / create-admin 初始化。"""

import argparse
import getpass
import sqlite3

from pydantic import ValidationError

from .db import connection, database_path, initialize
from .schemas import UserCreate
from .security import hash_password


def create_admin(path, username, name, password):
    user = UserCreate(username=username, name=name, password=password, is_admin=True)
    initialize(path)
    with connection(path, write=True) as db:
        db.execute(
            "INSERT INTO users(username,name,password_hash,is_admin) VALUES(?,?,?,1)",
            (user.username, user.name, hash_password(user.password)),
        )


def main():
    parser = argparse.ArgumentParser(description="OA 初始化工具")
    parser.add_argument("command", choices=["init", "create-admin"])
    args = parser.parse_args()
    path = database_path()
    if args.command == "init":
        initialize(path)
        print(f"数据库已初始化：{path}")
        return
    username = input("管理员用户名：").strip()
    name = input("姓名：").strip()
    password = getpass.getpass("密码（8—128 位）：")
    if password != getpass.getpass("再次输入密码："):
        parser.exit(1, "两次密码不一致，未创建账号。\n")
    try:
        create_admin(path, username, name, password)
    except sqlite3.IntegrityError:
        parser.exit(1, "用户名已存在，未覆盖原账号。\n")
    except ValidationError:
        parser.exit(1, "资料无效：用户名需为 1—40 位字母、数字、下划线、点或短横线，姓名 1—80 位，密码 8—128 位。\n")
    print("管理员创建成功。")


if __name__ == "__main__":
    main()
