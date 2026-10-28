"""数据库模块：SQLite 连接与建表。

数据持久化是课程验收点之一（"刷新页面或换设备后，物品记录、已转出状态
与图片地址必须保持一致"），因此所有数据都落在 instance/shiguang.db。
"""

import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "instance" / "shiguang.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    nickname      TEXT NOT NULL,          -- 对外展示的昵称
    contact       TEXT NOT NULL DEFAULT '',-- 联系方式，仅登录用户可见
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    category    TEXT NOT NULL,            -- 教材 / 数码配件 / 生活用品 / 其他
    mode        TEXT NOT NULL,            -- 出售 / 免费赠送 / 交换
    price       REAL NOT NULL DEFAULT 0,  -- 出售时的价格（元）；免费/交换记 0
    condition   TEXT NOT NULL,            -- 成色
    campus      TEXT NOT NULL,            -- 所在校区
    description TEXT NOT NULL DEFAULT '',
    image       TEXT,                     -- uploads/ 下的文件名，可为空
    status      TEXT NOT NULL DEFAULT '在售',  -- 在售 / 已转出 / 已下架
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);
CREATE INDEX IF NOT EXISTS idx_items_status   ON items(status);
CREATE INDEX IF NOT EXISTS idx_items_campus   ON items(campus);
"""


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)
