"""重置数据库并写入演示数据（含 SVG 占位图）。

用法：python3 seed.py
注意：会删除 instance/shiguang.db 与 uploads/ 下的所有旧文件。

演示账号：demo1 / shiguang123，demo2 / shiguang123
（两个账号用于课程验收的"双账号验证：本人可编辑、他人不可改"）
"""

import shutil
from datetime import datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

from werkzeug.security import generate_password_hash

import db as dbm

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"

PALETTES = [("#fbbf24", "#b45309"),   # 暖黄
            ("#5eead4", "#0f766e"),   # 青绿
            ("#c7d2fe", "#4338ca"),   # 靛蓝
            ("#fbcfe8", "#9d174d")]   # 玫粉

# (发布者, 标题, 分类, 方式, 价格, 成色, 校区, 描述, 状态, 几天前发布)
DEMO_ITEMS = [
    (0, "高等数学（第七版·上册）", "教材", "出售", 12, "九成新", "江湾校区",
     "教材课程用书，无笔记无划线，附送课后习题答案打印版。可来教学楼自提。", "在售", 6),
    (0, "线性代数 + 概率论与数理统计（打包）", "教材", "免费赠送", 0, "八成新", "江湾校区",
     "毕业清宿舍，两本一起送，先到先得。有少量铅笔笔记，不影响阅读。", "已转出", 12),
    (1, "数据结构（C++ 语言版）", "教材", "出售", 15, "八成新", "江湾校区",
     "计算机系必修课教材，书脊轻微磨损，内页完好。", "在售", 4),
    (1, "罗技 K380 蓝牙键盘（粉色）", "数码配件", "出售", 80, "九成新", "江湾校区",
     "使用一学期，按键无油光，电池仓干净。配对稳定，iPad/手机/电脑均可连。", "在售", 3),
    (0, "USB-C 八合一扩展坞", "数码配件", "出售", 95, "全新", "江湾校区",
     "双十一凑单多买的，未拆封。含 HDMI/网口/SD 卡槽/3 个 USB 口。", "在售", 2),
    (1, "小米台灯（可调光）", "生活用品", "交换", 0, "有明显使用痕迹", "江湾校区",
     "想换一个桌面收纳盒或等价生活用品，灯罩有一处小磕碰，功能正常。", "在售", 5),
    (0, "宿舍收纳箱三件套", "生活用品", "出售", 20, "八成新", "江湾校区",
     "搬宿舍用不上了，洗过晾干。可叠放，装被子衣物都很能装。", "在售", 8),
    (1, "长柄晴雨伞", "生活用品", "免费赠送", 0, "有明显使用痕迹", "江湾校区",
     "伞骨完好，伞面略褪色。放宿舍楼下宿管处，需要的同学自取。", "在售", 1),
    (0, "机械键盘键帽套装（108 键）", "数码配件", "出售", 45, "全新", "江湾校区",
     "买键盘时多买的一套 PBT 键帽，未拆封，白灰配色。", "已下架", 10),
    (1, "计算机网络：自顶向下方法（第8版）", "教材", "出售", 18, "九成新", "江湾校区",
     "英文影印版，只看了前三章，像新书。江湾食堂门口可交接。", "在售", 0),
]

DEMO_USERS = [
    # (用户名, 昵称, 联系方式)
    ("demo1", "拾光学姐", "微信：shiguang-demo1"),
    ("demo2", "江湾学长", "QQ：123456789"),
]


def make_placeholder(dest: Path, title: str, category: str, idx: int):
    """生成渐变色 SVG 占位图（标题文字由浏览器渲染，无需本地字体）。"""
    light, dark = PALETTES[idx % len(PALETTES)]
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480" viewBox="0 0 640 480">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{light}"/>
      <stop offset="1" stop-color="{dark}"/>
    </linearGradient>
  </defs>
  <rect width="640" height="480" fill="url(#g)"/>
  <circle cx="545" cy="80" r="130" fill="#ffffff" opacity="0.14"/>
  <circle cx="70" cy="430" r="170" fill="#ffffff" opacity="0.10"/>
  <text x="44" y="92" font-size="26" fill="#ffffff" opacity="0.85" font-family="sans-serif">{escape(category)}</text>
  <text x="44" y="404" font-size="34" font-weight="bold" fill="#ffffff" font-family="sans-serif">{escape(title)}</text>
  <text x="44" y="444" font-size="18" fill="#ffffff" opacity="0.75" font-family="sans-serif">拾光校园 · 演示图片</text>
</svg>
"""
    dest.write_text(svg, encoding="utf-8")


def main():
    # 1) 清空旧数据
    if dbm.DB_PATH.exists():
        dbm.DB_PATH.unlink()
    if UPLOAD_DIR.exists():
        shutil.rmtree(UPLOAD_DIR)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    dbm.init_db()
    now_base = datetime.now()

    conn = dbm.connect()
    with conn:
        # 2) 演示用户
        user_ids = []
        for username, nickname, contact in DEMO_USERS:
            cur = conn.execute(
                "INSERT INTO users (username, password_hash, nickname, contact, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (username, generate_password_hash("shiguang123"), nickname, contact,
                 (now_base - timedelta(days=15)).strftime("%Y-%m-%d %H:%M")))
            user_ids.append(cur.lastrowid)

        # 3) 演示物品 + 占位图
        for i, (owner, title, category, mode, price, condition, campus,
                desc, status, days_ago) in enumerate(DEMO_ITEMS):
            image_name = f"seed-{i:02d}.svg"
            make_placeholder(UPLOAD_DIR / image_name, title, category, i)
            created = (now_base - timedelta(days=days_ago, hours=(i * 3) % 20)).strftime("%Y-%m-%d %H:%M")
            conn.execute(
                "INSERT INTO items (user_id, title, category, mode, price, condition, campus, "
                "description, image, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (user_ids[owner], title, category, mode, price, condition, campus,
                 desc, image_name, status, created, created))
    conn.close()

    print(f"✅ 已重置并写入演示数据：{len(DEMO_USERS)} 个用户、{len(DEMO_ITEMS)} 件物品")
    print("   演示账号：demo1 / shiguang123、demo2 / shiguang123")


if __name__ == "__main__":
    main()
