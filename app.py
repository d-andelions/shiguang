"""拾光校园 —— 校园闲置资源共享平台（单校区轻量化网页 MVP）

对应课程汇报的最小功能闭环：发布 → 分类搜索 → 详情查看 → 更新状态。
包含：用户注册/登录（Session）、物品与图片持久化（SQLite + uploads/）、
服务端权限校验（本人可编辑、他人不可改，双账号验证点）。
建设边界：不做在线支付、物流配送、复杂站内聊天、信用评分与自动仲裁。

运行：python3 app.py   （默认 0.0.0.0:5000，便于手机等跨设备访问验证）
"""

import os
import uuid
from datetime import datetime
from functools import wraps

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   send_from_directory, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import db as dbm

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")

# ---- 常量：下拉框取值与上传约束 ----
CATEGORIES = ["教材", "数码配件", "生活用品", "其他"]
CAMPUSES = ["江湾校区", "邯郸校区", "枫林校区", "张江校区"]
CONDITIONS = ["全新", "九成新", "八成新", "有明显使用痕迹"]
MODES = ["出售", "免费赠送", "交换"]
STATUSES = ["在售", "已转出", "已下架"]
ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5MB

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "shiguang-mvp-dev-key")
os.makedirs(UPLOAD_DIR, exist_ok=True)
dbm.init_db()

SORT_OPTIONS = {
    "latest": "i.created_at DESC, i.id DESC",
    "price_asc": "i.price ASC, i.created_at DESC",
    "price_desc": "i.price DESC, i.created_at DESC",
}


# ---------------------------------------------------------------- 数据库连接
@app.teardown_appcontext
def close_db(exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def get_db():
    if "db" not in g:
        g.db = dbm.connect()
    return g.db


@app.context_processor
def inject_globals():
    """模板全局变量：当前用户与各下拉框选项。"""
    user = None
    if session.get("user_id"):
        user = get_db().execute(
            "SELECT id, username, nickname, contact FROM users WHERE id = ?",
            (session["user_id"],)).fetchone()
    return {"current_user": user, "CATEGORIES": CATEGORIES, "CAMPUSES": CAMPUSES,
            "CONDITIONS": CONDITIONS, "MODES": MODES, "STATUSES": STATUSES,
            "SORT_OPTIONS": [("latest", "最新发布"), ("price_asc", "价格从低到高"),
                             ("price_desc", "价格从高到低")]}


# ---------------------------------------------------------------- 鉴权
def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("请先登录后再操作", "error")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def get_owned_item_or_403(item_id):
    """取物品并校验归属：不存在返回 404，非本人返回 403（他人不可改）。"""
    item = get_db().execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if item is None:
        abort(404)
    if item["user_id"] != session.get("user_id"):
        abort(403)
    return item


# ---------------------------------------------------------------- 图片上传
def save_image(file_storage):
    """校验并保存上传图片，返回 (文件名, 错误信息)。"""
    filename = file_storage.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_IMAGE_EXT:
        return None, "图片格式仅支持 png / jpg / jpeg / gif / webp"
    data = file_storage.read()
    if len(data) > MAX_IMAGE_BYTES:
        return None, "图片大小不能超过 5MB"
    if not data:
        return None, "图片文件为空"
    name = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(UPLOAD_DIR, name), "wb") as f:
        f.write(data)
    return name, None


def remove_image(filename):
    if filename:
        path = os.path.join(UPLOAD_DIR, filename)
        if os.path.exists(path):
            os.remove(path)


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


# ---------------------------------------------------------------- 首页：分类搜索
@app.route("/")
def index():
    f = {
        "q": request.args.get("q", "").strip(),
        "category": request.args.get("category", ""),
        "campus": request.args.get("campus", ""),
        "mode": request.args.get("mode", ""),
        "status": request.args.get("status", "在售"),  # 默认只看在售，避免"已转出仍在列表"
        "sort": request.args.get("sort", "latest"),
    }
    where, params = ["1=1"], []
    if f["q"]:
        where.append("AND (i.title LIKE ? OR i.description LIKE ?)")
        params += [f"%{f['q']}%"] * 2
    for field, column in (("category", "i.category"), ("campus", "i.campus"),
                          ("mode", "i.mode")):
        if f[field]:
            where.append(f"AND {column} = ?")
            params.append(f[field])
    if f["status"]:
        where.append("AND i.status = ?")
        params.append(f["status"])

    order = SORT_OPTIONS.get(f["sort"], SORT_OPTIONS["latest"])
    rows = get_db().execute(
        f"""SELECT i.*, u.nickname FROM items i
            JOIN users u ON u.id = i.user_id
            WHERE {' '.join(where)} ORDER BY {order} LIMIT 100""",
        params).fetchall()
    return render_template("index.html", items=rows, filters=f)


# ---------------------------------------------------------------- 用户
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        nickname = request.form.get("nickname", "").strip() or username
        contact = request.form.get("contact", "").strip()
        password = request.form.get("password", "")
        error = None
        if not (3 <= len(username) <= 20) or not username.replace("_", "").isalnum():
            error = "用户名需为 3-20 位字母、数字或下划线"
        elif len(password) < 6:
            error = "密码至少 6 位"
        elif not contact:
            error = "请填写联系方式（如微信号/QQ，仅登录用户可见）"
        else:
            try:
                with get_db() as conn:
                    conn.execute(
                        "INSERT INTO users (username, password_hash, nickname, contact, created_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (username, generate_password_hash(password), nickname, contact,
                         datetime.now().strftime("%Y-%m-%d %H:%M")))
            except Exception:
                error = "该用户名已被注册"
        if error:
            flash(error, "error")
            return render_template("register.html", form=request.form), 400
        flash("注册成功，请登录", "success")
        return redirect(url_for("login"))
    return render_template("register.html", form={})


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM users WHERE username = ?",
                                (username,)).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("用户名或密码错误", "error")
            return render_template("login.html", form=request.form), 401
        session.clear()
        session["user_id"] = user["id"]
        session["nickname"] = user["nickname"]
        flash(f"欢迎回来，{user['nickname']}！", "success")
        next_url = request.args.get("next") or url_for("index")
        if not next_url.startswith("/"):  # 防开放跳转
            next_url = url_for("index")
        return redirect(next_url)
    return render_template("login.html", form={})


@app.route("/logout")
def logout():
    session.clear()
    flash("已退出登录", "success")
    return redirect(url_for("index"))


# ---------------------------------------------------------------- 物品
@app.route("/publish", methods=["GET", "POST"])
@login_required
def publish():
    if request.method == "POST":
        data, error = parse_item_form()
        if error:
            flash(error, "error")
            return render_template("publish.html", form=request.form), 400
        image_name, img_error = maybe_save_upload()
        if img_error:
            flash(img_error, "error")
            return render_template("publish.html", form=request.form), 400
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        with get_db() as conn:
            cur = conn.execute(
                "INSERT INTO items (user_id, title, category, mode, price, condition, "
                "campus, description, image, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (session["user_id"], data["title"], data["category"], data["mode"],
                 data["price"], data["condition"], data["campus"], data["description"],
                 image_name, "在售", now, now))
            item_id = cur.lastrowid
        flash("发布成功！", "success")
        return redirect(url_for("item_detail", item_id=item_id))
    return render_template("publish.html", form={})


@app.route("/item/<int:item_id>")
def item_detail(item_id):
    item = get_db().execute(
        "SELECT i.*, u.nickname, u.contact FROM items i "
        "JOIN users u ON u.id = i.user_id WHERE i.id = ?", (item_id,)).fetchone()
    if item is None:
        abort(404)
    is_owner = session.get("user_id") == item["user_id"]
    return render_template("detail.html", item=item, is_owner=is_owner)


@app.route("/item/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def edit_item(item_id):
    item = get_owned_item_or_403(item_id)  # 他人访问直接 403
    if request.method == "POST":
        data, error = parse_item_form()
        if error:
            flash(error, "error")
            return render_template("edit.html", item=item, form=request.form), 400
        new_status = request.form.get("status", item["status"])
        if new_status not in STATUSES:
            new_status = item["status"]
        image_name = item["image"]
        upload = request.files.get("image")
        if upload and upload.filename:
            name, img_error = save_image(upload)
            if img_error:
                flash(img_error, "error")
                return render_template("edit.html", item=item, form=request.form), 400
            remove_image(image_name)  # 换图后清理旧文件
            image_name = name
        with get_db() as conn:
            conn.execute(
                "UPDATE items SET title=?, category=?, mode=?, price=?, condition=?, "
                "campus=?, description=?, image=?, status=?, updated_at=? WHERE id=?",
                (data["title"], data["category"], data["mode"], data["price"],
                 data["condition"], data["campus"], data["description"], image_name,
                 new_status, datetime.now().strftime("%Y-%m-%d %H:%M"), item_id))
        flash("物品信息已更新", "success")
        return redirect(url_for("item_detail", item_id=item_id))
    return render_template("edit.html", item=item, form=None)


@app.route("/item/<int:item_id>/status", methods=["POST"])
@login_required
def update_status(item_id):
    item = get_owned_item_or_403(item_id)
    new_status = request.form.get("status", "")
    if new_status not in STATUSES:
        flash("无效的状态值", "error")
        return redirect(url_for("item_detail", item_id=item_id))
    with get_db() as conn:
        conn.execute("UPDATE items SET status=?, updated_at=? WHERE id=?",
                     (new_status, datetime.now().strftime("%Y-%m-%d %H:%M"), item_id))
    flash(f"状态已更新为「{new_status}」", "success")
    return redirect(request.referrer or url_for("item_detail", item_id=item_id))


@app.route("/item/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_item(item_id):
    item = get_owned_item_or_403(item_id)
    with get_db() as conn:
        conn.execute("DELETE FROM items WHERE id=?", (item_id,))
    remove_image(item["image"])
    flash("物品已删除", "success")
    return redirect(url_for("my_items"))


@app.route("/my/items")
@login_required
def my_items():
    items = get_db().execute(
        "SELECT * FROM items WHERE user_id=? ORDER BY created_at DESC, id DESC",
        (session["user_id"],)).fetchall()
    return render_template("my_items.html", items=items)


# ---------------------------------------------------------------- 表单校验
def parse_item_form():
    """校验发布/编辑表单，返回 (data, error)。"""
    form = request.form
    title = form.get("title", "").strip()
    category = form.get("category", "")
    mode = form.get("mode", "")
    condition = form.get("condition", "")
    campus = form.get("campus", "")
    description = form.get("description", "").strip()
    if not (1 <= len(title) <= 50):
        return None, "标题长度需为 1-50 个字符"
    if category not in CATEGORIES:
        return None, "请选择物品分类"
    if mode not in MODES:
        return None, "请选择交易方式"
    if condition not in CONDITIONS:
        return None, "请选择物品成色"
    if campus not in CAMPUSES:
        return None, "请选择所在校区"
    price = 0.0
    if mode == "出售":
        try:
            price = round(float(form.get("price", "")), 2)
            if price < 0 or price > 999999:
                raise ValueError
        except ValueError:
            return None, "出售时请填写 0-999999 之间的有效价格"
    return {"title": title, "category": category, "mode": mode, "price": price,
            "condition": condition, "campus": campus,
            "description": description[:1000]}, None


def maybe_save_upload():
    upload = request.files.get("image")
    if upload is None or not upload.filename:
        return None, None  # 图片为可选
    return save_image(upload)


# ---------------------------------------------------------------- 错误页
@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403,
                           message="没有权限：只有发布者本人可以修改该物品（他人不可改）"), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="页面或物品不存在"), 404


if __name__ == "__main__":
    # host=0.0.0.0：同一校园网内可用手机等设备访问，验证"跨设备数据一致"
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 18000)))
