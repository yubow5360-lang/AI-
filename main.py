from pathlib import Path
from datetime import datetime, date, timedelta
import json
import os
import uuid
from typing import Optional

from fastapi import FastAPI, Request, UploadFile, File, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text, text
from sqlalchemy.orm import declarative_base, sessionmaker
from openai import OpenAI
from passlib.context import CryptContext
from jose import JWTError, jwt

SECRET_KEY = os.getenv("APP_SECRET_KEY", "dev-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

BASE_DIR = Path(__file__).resolve().parent
UPLOADS_DIR = BASE_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

app = FastAPI()

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY", ""),
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com"),
)

DB_PATH = BASE_DIR / "tasks.db"
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)
Session = sessionmaker(bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    title = Column(String)
    completed = Column(Boolean, default=False)
    due_date = Column(DateTime, nullable=True)
    goal_id = Column(Integer, nullable=True)
    user_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Goal(Base):
    __tablename__ = "goals"
    id = Column(Integer, primary_key=True)
    title = Column(String)
    user_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True)
    summary = Column(Text, nullable=True)
    efficiency = Column(Text, nullable=True)
    tomorrow_plan = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    user_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Assignment(Base):
    __tablename__ = "assignments"
    id = Column(Integer, primary_key=True)
    filename = Column(String)
    original_name = Column(String)
    user_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class StudyGroup(Base):
    __tablename__ = "study_groups"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    owner_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class GroupMember(Base):
    __tablename__ = "group_members"
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, nullable=False)
    user_id = Column(Integer, nullable=False)
    role = Column(String, default="member")
    created_at = Column(DateTime, default=datetime.utcnow)


class TeamTask(Base):
    __tablename__ = "team_tasks"
    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    completed = Column(Boolean, default=False)
    assignee_id = Column(Integer, nullable=True)
    due_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(engine)


pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def run_migrations():
    """为已有数据库添加新列（若不存在）"""
    with engine.connect() as conn:
        for table, cols in [
            (
                "tasks",
                [
                    ("completed", "INTEGER DEFAULT 0"),
                    ("due_date", "DATETIME"),
                    ("goal_id", "INTEGER"),
                    ("created_at", "DATETIME"),
                    ("user_id", "INTEGER"),
                ],
            ),
            (
                "reviews",
                [
                    ("summary", "TEXT"),
                    ("efficiency", "TEXT"),
                    ("tomorrow_plan", "TEXT"),
                    ("created_at", "DATETIME"),
                    ("user_id", "INTEGER"),
                ],
            ),
            ("assignments", [("user_id", "INTEGER")]),
            ("goals", [("user_id", "INTEGER")]),
            ("team_tasks", [("completed", "INTEGER DEFAULT 0"), ("assignee_id", "INTEGER"), ("due_date", "DATETIME"), ("created_at", "DATETIME")]),
        ]:
            try:
                r = conn.execute(text(f"PRAGMA table_info({table})"))
                existing = [row[1] for row in r]
                for col_name, col_type in cols:
                    if col_name not in existing:
                        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"))
                        conn.commit()
            except Exception:
                pass


run_migrations()

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(request: Request) -> User:
    auth_header: Optional[str] = request.headers.get("Authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")
    token = auth_header.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效 token")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效 token")
    db = Session()
    user = db.query(User).filter(User.id == int(user_id)).first()
    db.close()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    return user


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/service-worker.js")
async def service_worker():
    return FileResponse(
        str(BASE_DIR / "static" / "service-worker.js"),
        media_type="application/javascript",
    )


# ---------- Auth ----------
@app.post("/auth/register")
async def register(data: dict):
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        raise HTTPException(status_code=400, detail="用户名和密码不能为空")
    db = Session()
    if db.query(User).filter(User.username == username).first():
        db.close()
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = User(username=username, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token({"sub": str(user.id)})
    db.close()
    return {"access_token": token, "token_type": "bearer", "username": username}


@app.post("/auth/login")
async def login(data: dict):
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    db = Session()
    user = db.query(User).filter(User.username == username).first()
    db.close()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=400, detail="用户名或密码错误")
    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer", "username": username}


@app.get("/auth/me")
async def me(current: User = Depends(get_current_user)):
    return {"id": current.id, "username": current.username}


def calc_efficiency_metrics(tasks):
    total = len(tasks)
    completed = sum(1 for t in tasks if getattr(t, "completed", False))
    completion_rate = (completed / total * 100) if total else 0.0

    due_tasks = [t for t in tasks if getattr(t, "due_date", None)]
    overdue_open = []
    now = datetime.utcnow()
    for t in due_tasks:
        due = t.due_date
        if due and due.tzinfo:
            due = due.replace(tzinfo=None)
        if due and due < now and not getattr(t, "completed", False):
            overdue_open.append(t)
    procrastination_index = (len(overdue_open) / len(due_tasks) * 100) if due_tasks else 0.0

    recent_days = 14
    day_map = {}
    for t in tasks:
        c = getattr(t, "created_at", None)
        if not c:
            continue
        c = c.replace(tzinfo=None)
        if (now - c).days >= recent_days:
            continue
        key = c.date().isoformat()
        day_map.setdefault(key, {"total": 0, "done": 0})
        day_map[key]["total"] += 1
        if getattr(t, "completed", False):
            day_map[key]["done"] += 1
    active_days = len(day_map)
    avg_daily_done_rate = 0.0
    if active_days:
        avg_daily_done_rate = sum(v["done"] / v["total"] for v in day_map.values() if v["total"]) / active_days * 100
    consistency = (active_days / recent_days) * 100
    focus_score = (avg_daily_done_rate * 0.7) + (consistency * 0.3)

    return {
        "total_tasks": total,
        "completed_tasks": completed,
        "completion_rate": round(completion_rate, 1),
        "focus_score": round(min(max(focus_score, 0), 100), 1),
        "procrastination_index": round(min(max(procrastination_index, 0), 100), 1),
        "overdue_count": len(overdue_open),
    }


def summarize_period(tasks, start_dt: datetime, end_dt: datetime, title: str):
    scoped = []
    for t in tasks:
        created = getattr(t, "created_at", None)
        if not created:
            continue
        created = created.replace(tzinfo=None)
        if start_dt <= created < end_dt:
            scoped.append(t)
    metrics = calc_efficiency_metrics(scoped)
    top_open = [t.title for t in scoped if not getattr(t, "completed", False)][:5]
    return {
        "title": title,
        "period_start": start_dt.date().isoformat(),
        "period_end": (end_dt - timedelta(days=1)).date().isoformat(),
        "metrics": metrics,
        "suggestions": [
            "先完成截止时间最早的任务，再处理长期任务",
            "每天固定一个 25 分钟专注时段，减少任务切换",
            "把未完成任务拆分到可在 30 分钟内完成的小步骤",
        ],
        "open_tasks": top_open,
    }


# ---------- 1. AI 学习计划 ----------
@app.post("/ai_plan")
async def ai_plan(data: dict, current: User = Depends(get_current_user)):
    goal = data.get("goal", "").strip()
    if not goal:
        return {"plan": "", "error": "目标不能为空"}
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "把目标拆成学习任务，每行一个，不要编号不要多余符号"},
            {"role": "user", "content": goal},
        ],
    )
    plan = response.choices[0].message.content or ""
    db = Session()
    today = datetime.utcnow().date()
    for i, line in enumerate(plan.split("\n")):
        t = line.strip()
        if t:
            due = datetime.combine(today, datetime.min.time()) if i < 5 else None
            db.add(Task(title=t, due_date=due, user_id=current.id))
    db.commit()
    db.close()
    return {"plan": plan}


# ---------- 2. 任务管理 ----------
@app.get("/tasks")
def get_tasks(current: User = Depends(get_current_user)):
    db = Session()
    tasks = db.query(Task).filter(Task.user_id == current.id).order_by(Task.id.desc()).all()
    out = [
        {
            "id": t.id,
            "title": t.title,
            "completed": getattr(t, "completed", False) or False,
            "due_date": t.due_date.isoformat() if getattr(t, "due_date", None) else None,
            "created_at": getattr(t, "created_at", None).isoformat() if getattr(t, "created_at", None) else None,
        }
        for t in tasks
    ]
    db.close()
    return out


@app.post("/task")
async def add_task(data: dict, current: User = Depends(get_current_user)):
    db = Session()
    title = data.get("title", "").strip()
    due = data.get("due_date")
    if due:
        due_dt = datetime.fromisoformat(due.replace("Z", "+00:00"))
    else:
        due_dt = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    task = Task(title=title, due_date=due_dt, user_id=current.id)
    db.add(task)
    db.commit()
    tid = task.id
    db.close()
    return {"status": "ok", "id": tid}


@app.patch("/task/{task_id}")
async def update_task(task_id: int, data: dict, current: User = Depends(get_current_user)):
    db = Session()
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == current.id).first()
    if not task:
        db.close()
        return {"status": "error", "message": "任务不存在"}
    if "completed" in data:
        task.completed = bool(data["completed"])
    if "due_date" in data:
        task.due_date = datetime.fromisoformat(data["due_date"].replace("Z", "+00:00")) if data["due_date"] else None
    db.commit()
    db.close()
    return {"status": "ok"}


@app.delete("/task/{task_id}")
def delete_task(task_id: int, current: User = Depends(get_current_user)):
    db = Session()
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == current.id).first()
    if task:
        db.delete(task)
        db.commit()
    db.close()
    return {"status": "ok"}


# ---------- 日历事件（FullCalendar 用）----------
@app.get("/events")
def get_events(start: str = None, end: str = None, current: User = Depends(get_current_user)):
    db = Session()
    tasks = db.query(Task).filter(Task.user_id == current.id, Task.due_date.isnot(None)).all()
    events = []
    for t in tasks:
        if getattr(t, "due_date", None):
            d = t.due_date
            if d.tzinfo:
                d = d.replace(tzinfo=None)
            events.append({
                "id": str(t.id),
                "title": t.title,
                "start": d.date().isoformat() if hasattr(d, "date") else d[:10],
                "allDay": True,
                "extendedProps": {"completed": getattr(t, "completed", False)},
            })
    db.close()
    return events


# ---------- 4. 学习效率统计 ----------
@app.get("/stats")
def get_stats(current: User = Depends(get_current_user)):
    db = Session()
    tasks = db.query(Task).filter(Task.user_id == current.id).all()
    total = len(tasks)
    completed = sum(1 for t in tasks if getattr(t, "completed", False))
    rate = (completed / total * 100) if total else 0
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    today_end = today_start + timedelta(days=1)
    today_tasks = [t for t in tasks if getattr(t, "created_at", None) and today_start <= t.created_at.replace(tzinfo=None) < today_end]
    today_total = len(today_tasks)
    today_done = sum(1 for t in today_tasks if getattr(t, "completed", False))
    today_rate = (today_done / today_total * 100) if today_total else 0
    db.close()
    return {
        "total_tasks": total,
        "completed_tasks": completed,
        "completion_rate": round(rate, 1),
        "today_total": today_total,
        "today_completed": today_done,
        "today_rate": round(today_rate, 1),
    }


@app.get("/analytics/efficiency")
def get_efficiency(current: User = Depends(get_current_user)):
    db = Session()
    tasks = db.query(Task).filter(Task.user_id == current.id).all()
    db.close()
    return calc_efficiency_metrics(tasks)


@app.get("/reports/weekly")
def weekly_report(current: User = Depends(get_current_user)):
    db = Session()
    tasks = db.query(Task).filter(Task.user_id == current.id).all()
    db.close()
    now = datetime.utcnow().replace(tzinfo=None)
    week_start = datetime.combine((now - timedelta(days=now.weekday())).date(), datetime.min.time())
    week_end = week_start + timedelta(days=7)
    return summarize_period(tasks, week_start, week_end, "学习周报")


@app.get("/reports/monthly")
def monthly_report(current: User = Depends(get_current_user)):
    db = Session()
    tasks = db.query(Task).filter(Task.user_id == current.id).all()
    db.close()
    now = datetime.utcnow().replace(tzinfo=None)
    month_start = datetime(now.year, now.month, 1)
    if now.month == 12:
        month_end = datetime(now.year + 1, 1, 1)
    else:
        month_end = datetime(now.year, now.month + 1, 1)
    return summarize_period(tasks, month_start, month_end, "学习月报")


# ---------- 5. 长期目标 ----------
@app.get("/goals")
def get_goals(current: User = Depends(get_current_user)):
    db = Session()
    goals = db.query(Goal).filter(Goal.user_id == current.id).order_by(Goal.id.desc()).all()
    out = [{"id": g.id, "title": g.title, "created_at": g.created_at.isoformat() if g.created_at else None} for g in goals]
    db.close()
    return out


@app.post("/goal")
async def add_goal(data: dict, current: User = Depends(get_current_user)):
    title = data.get("title", "").strip()
    if not title:
        return {"status": "error", "message": "目标不能为空"}
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "将长期目标拆解为多个阶段任务，每行一个阶段，格式：阶段名或简短描述，不要编号"},
            {"role": "user", "content": title},
        ],
    )
    plan = response.choices[0].message.content or ""
    db = Session()
    goal = Goal(title=title, user_id=current.id)
    db.add(goal)
    db.flush()
    goal_id = goal.id
    base_date = datetime.utcnow()
    for i, line in enumerate(plan.split("\n")):
        t = line.strip()
        if t:
            due = base_date + timedelta(days=7 * (i + 1))
            db.add(Task(title=t, goal_id=goal_id, due_date=due, user_id=current.id))
    db.commit()
    db.close()
    return {"status": "ok", "goal_id": goal_id, "phases": [x.strip() for x in plan.split("\n") if x.strip()]}


# ---------- 6. AI 每日复盘 ----------
@app.post("/review")
async def ai_review(current: User = Depends(get_current_user)):
    db = Session()
    tasks = db.query(Task).filter(Task.user_id == current.id).all()
    completed_list = [t.title for t in tasks if getattr(t, "completed", False)]
    all_titles = [t.title for t in tasks]
    text_completed = "\n".join(completed_list) if completed_list else "无"
    text_all = "\n".join(all_titles) if all_titles else "无"
    db.close()

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {
                "role": "system",
                "content": "你是一个学习复盘助手。根据用户提供的今日任务列表和完成情况，用JSON格式回复，包含三个字段（均为字符串）：\n"
                '"summary": "今日复盘总结（一段话）",\n'
                '"efficiency": "效率分析（简短）",\n'
                '"tomorrow_plan": "明日计划建议（简短）"\n'
                "只返回JSON，不要其他文字。",
            },
            {"role": "user", "content": f"今日全部任务：\n{text_all}\n\n今日已完成：\n{text_completed}"},
        ],
    )
    raw = response.choices[0].message.content or "{}"
    try:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
    except Exception:
        data = {"summary": raw, "efficiency": "", "tomorrow_plan": ""}

    summary = data.get("summary", "")
    efficiency = data.get("efficiency", "")
    tomorrow_plan = data.get("tomorrow_plan", "")

    db = Session()
    db.add(Review(summary=summary, efficiency=efficiency, tomorrow_plan=tomorrow_plan, content=raw, user_id=current.id))
    db.commit()
    db.close()
    return {"summary": summary, "efficiency": efficiency, "tomorrow_plan": tomorrow_plan}


# ---------- 7. 提醒（仅前端浏览器通知，无后端）----------

# ---------- 8. 作业管理 ----------
@app.post("/assignment")
async def upload_assignment(file: UploadFile = File(...), current: User = Depends(get_current_user)):
    ext = Path(file.filename or "").suffix or ".bin"
    safe_name = f"{uuid.uuid4().hex}{ext}"
    path = UPLOADS_DIR / safe_name
    content = await file.read()
    path.write_bytes(content)
    db = Session()
    a = Assignment(filename=safe_name, original_name=file.filename or "未命名", user_id=current.id)
    db.add(a)
    db.commit()
    aid = a.id
    db.close()
    return {"status": "ok", "id": aid, "filename": file.filename, "stored": safe_name}


@app.get("/assignments")
def get_assignments(current: User = Depends(get_current_user)):
    db = Session()
    items = db.query(Assignment).filter(Assignment.user_id == current.id).order_by(Assignment.id.desc()).all()
    out = [{"id": a.id, "original_name": a.original_name, "filename": a.filename, "created_at": a.created_at.isoformat() if a.created_at else None} for a in items]
    db.close()
    return out


# ---------- 9. 番茄钟（仅前端）----------

# ---------- 10. AI 学习教练 ----------
@app.post("/coach")
async def ai_coach(current: User = Depends(get_current_user)):
    db = Session()
    tasks = db.query(Task).filter(Task.user_id == current.id).all()
    total = len(tasks)
    completed = sum(1 for t in tasks if getattr(t, "completed", False))
    recent = [t for t in tasks[-20:]]
    text = "\n".join([f"{'✓' if getattr(t, 'completed', False) else '○'} {t.title}" for t in recent])
    db.close()

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "你是学习教练。根据用户的任务完成情况，给出一段简短、具体、可执行的学习建议（2–4句话）。"},
            {"role": "user", "content": f"总任务数：{total}，已完成：{completed}。最近任务：\n{text}"},
        ],
    )
    advice = response.choices[0].message.content or "暂无建议"
    return {"advice": advice}


@app.post("/agent/auto_plan")
async def agent_auto_plan(data: dict, current: User = Depends(get_current_user)):
    goal = (data.get("goal") or "").strip()
    days = int(data.get("days") or 7)
    if not goal:
        raise HTTPException(status_code=400, detail="目标不能为空")
    days = min(max(days, 1), 30)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "把学习目标拆成按天执行的任务清单。每行一个任务，最多10行，不要编号。"},
            {"role": "user", "content": f"目标：{goal}\n计划天数：{days}"},
        ],
    )
    plan = response.choices[0].message.content or ""
    db = Session()
    base_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    added = []
    for i, line in enumerate(plan.split("\n")):
        text_line = line.strip()
        if not text_line:
            continue
        due = base_date + timedelta(days=min(i, days - 1))
        task = Task(title=text_line, due_date=due, user_id=current.id)
        db.add(task)
        added.append(text_line)
    db.commit()
    db.close()
    return {"status": "ok", "count": len(added), "tasks": added}


@app.post("/agent/auto_adjust")
async def agent_auto_adjust(current: User = Depends(get_current_user)):
    db = Session()
    tasks = db.query(Task).filter(Task.user_id == current.id).all()
    metrics = calc_efficiency_metrics(tasks)
    now = datetime.utcnow()
    adjusted = 0
    # 如果拖延指数偏高，自动把逾期任务平滑到未来 3 天
    if metrics["procrastination_index"] >= 40:
        overdue = []
        for t in tasks:
            if not t.due_date or getattr(t, "completed", False):
                continue
            d = t.due_date.replace(tzinfo=None) if t.due_date.tzinfo else t.due_date
            if d < now:
                overdue.append(t)
        for idx, t in enumerate(overdue):
            t.due_date = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=(idx % 3) + 1)
            adjusted += 1
        db.commit()
    db.close()
    return {"status": "ok", "adjusted_tasks": adjusted, "metrics": metrics}


@app.post("/agent/auto_summary")
async def agent_auto_summary(current: User = Depends(get_current_user)):
    db = Session()
    tasks = db.query(Task).filter(Task.user_id == current.id).order_by(Task.created_at.desc()).limit(20).all()
    db.close()
    recent_lines = [f"{'✓' if t.completed else '○'} {t.title}" for t in tasks]
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "你是AI学习助手。根据任务记录输出一个简短学习总结（80-120字）和一个下一步建议。输出JSON：summary,next_step"},
            {"role": "user", "content": "\n".join(recent_lines) if recent_lines else "暂无任务"},
        ],
    )
    raw = response.choices[0].message.content or "{}"
    try:
        data = json.loads(raw)
    except Exception:
        data = {"summary": raw, "next_step": "保持每日复盘"}
    return {"summary": data.get("summary", ""), "next_step": data.get("next_step", "")}


@app.get("/agent/reminders")
async def agent_reminders(current: User = Depends(get_current_user)):
    db = Session()
    now = datetime.utcnow().replace(tzinfo=None)
    soon = now + timedelta(days=1)
    tasks = db.query(Task).filter(Task.user_id == current.id, Task.completed == False, Task.due_date.isnot(None)).all()
    db.close()
    reminders = []
    for t in tasks:
        due = t.due_date.replace(tzinfo=None) if t.due_date and t.due_date.tzinfo else t.due_date
        if not due:
            continue
        if due < now:
            reminders.append(f"任务已逾期：{t.title}")
        elif due <= soon:
            reminders.append(f"任务即将截止：{t.title}（{due.date().isoformat()}）")
    return {"items": reminders[:10]}


# ---------- 团队协作 ----------
@app.post("/groups")
def create_group(data: dict, current: User = Depends(get_current_user)):
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="小组名称不能为空")
    db = Session()
    g = StudyGroup(name=name, owner_id=current.id)
    db.add(g)
    db.flush()
    db.add(GroupMember(group_id=g.id, user_id=current.id, role="owner"))
    db.commit()
    db.refresh(g)
    db.close()
    return {"id": g.id, "name": g.name}


@app.get("/groups")
def list_groups(current: User = Depends(get_current_user)):
    db = Session()
    memberships = db.query(GroupMember).filter(GroupMember.user_id == current.id).all()
    group_ids = [m.group_id for m in memberships]
    groups = db.query(StudyGroup).filter(StudyGroup.id.in_(group_ids)).order_by(StudyGroup.id.desc()).all() if group_ids else []
    out = [{"id": g.id, "name": g.name, "owner_id": g.owner_id} for g in groups]
    db.close()
    return out


@app.post("/groups/{group_id}/members")
def add_group_member(group_id: int, data: dict, current: User = Depends(get_current_user)):
    username = (data.get("username") or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="用户名不能为空")
    db = Session()
    owner = db.query(GroupMember).filter(
        GroupMember.group_id == group_id,
        GroupMember.user_id == current.id,
        GroupMember.role == "owner",
    ).first()
    if not owner:
        db.close()
        raise HTTPException(status_code=403, detail="只有组长可以添加成员")
    user = db.query(User).filter(User.username == username).first()
    if not user:
        db.close()
        raise HTTPException(status_code=404, detail="用户不存在")
    exists = db.query(GroupMember).filter(GroupMember.group_id == group_id, GroupMember.user_id == user.id).first()
    if exists:
        db.close()
        return {"status": "ok", "message": "成员已存在"}
    db.add(GroupMember(group_id=group_id, user_id=user.id, role="member"))
    db.commit()
    db.close()
    return {"status": "ok"}


@app.get("/groups/{group_id}/members")
def list_group_members(group_id: int, current: User = Depends(get_current_user)):
    db = Session()
    joined = db.query(GroupMember).filter(GroupMember.group_id == group_id, GroupMember.user_id == current.id).first()
    if not joined:
        db.close()
        raise HTTPException(status_code=403, detail="无权访问该小组")
    members = db.query(GroupMember).filter(GroupMember.group_id == group_id).all()
    user_ids = [m.user_id for m in members]
    users = db.query(User).filter(User.id.in_(user_ids)).all() if user_ids else []
    name_map = {u.id: u.username for u in users}
    out = [{"user_id": m.user_id, "username": name_map.get(m.user_id, "unknown"), "role": m.role} for m in members]
    db.close()
    return out


@app.post("/groups/{group_id}/tasks")
def create_team_task(group_id: int, data: dict, current: User = Depends(get_current_user)):
    title = (data.get("title") or "").strip()
    assignee_username = (data.get("assignee_username") or "").strip()
    due_text = data.get("due_date")
    if not title:
        raise HTTPException(status_code=400, detail="任务标题不能为空")
    db = Session()
    joined = db.query(GroupMember).filter(GroupMember.group_id == group_id, GroupMember.user_id == current.id).first()
    if not joined:
        db.close()
        raise HTTPException(status_code=403, detail="无权访问该小组")
    assignee_id = None
    if assignee_username:
        user = db.query(User).filter(User.username == assignee_username).first()
        if not user:
            db.close()
            raise HTTPException(status_code=404, detail="指派用户不存在")
        member = db.query(GroupMember).filter(GroupMember.group_id == group_id, GroupMember.user_id == user.id).first()
        if not member:
            db.close()
            raise HTTPException(status_code=400, detail="指派用户不在小组内")
        assignee_id = user.id
    due = datetime.fromisoformat(due_text.replace("Z", "+00:00")) if due_text else None
    task = TeamTask(group_id=group_id, title=title, assignee_id=assignee_id, due_date=due)
    db.add(task)
    db.commit()
    db.refresh(task)
    db.close()
    return {"id": task.id, "title": task.title}


@app.get("/groups/{group_id}/tasks")
def list_team_tasks(group_id: int, current: User = Depends(get_current_user)):
    db = Session()
    joined = db.query(GroupMember).filter(GroupMember.group_id == group_id, GroupMember.user_id == current.id).first()
    if not joined:
        db.close()
        raise HTTPException(status_code=403, detail="无权访问该小组")
    tasks = db.query(TeamTask).filter(TeamTask.group_id == group_id).order_by(TeamTask.id.desc()).all()
    user_ids = [t.assignee_id for t in tasks if t.assignee_id]
    users = db.query(User).filter(User.id.in_(user_ids)).all() if user_ids else []
    name_map = {u.id: u.username for u in users}
    out = []
    for t in tasks:
        out.append({
            "id": t.id,
            "title": t.title,
            "completed": t.completed,
            "assignee_username": name_map.get(t.assignee_id, ""),
            "due_date": t.due_date.isoformat() if t.due_date else None,
        })
    db.close()
    return out


@app.patch("/groups/{group_id}/tasks/{task_id}")
def update_team_task(group_id: int, task_id: int, data: dict, current: User = Depends(get_current_user)):
    db = Session()
    joined = db.query(GroupMember).filter(GroupMember.group_id == group_id, GroupMember.user_id == current.id).first()
    if not joined:
        db.close()
        raise HTTPException(status_code=403, detail="无权访问该小组")
    task = db.query(TeamTask).filter(TeamTask.group_id == group_id, TeamTask.id == task_id).first()
    if not task:
        db.close()
        raise HTTPException(status_code=404, detail="任务不存在")
    if "completed" in data:
        task.completed = bool(data["completed"])
    db.commit()
    db.close()
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("APP_HOST", "0.0.0.0")
    port = int(os.getenv("APP_PORT", "8000"))
    uvicorn.run(
        app,
        host=host,
        port=port,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
