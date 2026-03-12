# AI Study System

（Vibe coding纯娱乐瞎玩）
一个基于 FastAPI + SQLite + 原生前端的 AI 学习系统，支持任务管理、学习分析、AI 辅助和团队协作。

## 功能特性

- 用户系统：注册、登录、JWT 鉴权
- 任务管理：新增/完成/删除任务，日历视图
- AI 功能：
  - AI 拆解学习计划
  - AI 每日复盘
  - AI 学习教练
  - AI Agent（自动规划、自动提醒、自动总结、自动调整计划）
- 数据分析：
  - 学习效率分析（完成率、专注度、拖延指数）
  - 学习周报 / 学习月报
- 团队协作：学习小组、成员管理、团队任务
- 跨设备：PWA（支持“安装到手机”）

## 技术栈

- 后端：FastAPI, SQLAlchemy, SQLite
- 鉴权：python-jose, passlib
- 前端：HTML/CSS/Vanilla JS + FullCalendar + Chart.js
- 部署：Uvicorn / Docker / Caddy(HTTPS)

## 本地运行

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

复制并编辑：

```bash
cp .env.example .env
```

最少需要配置：

- `APP_SECRET_KEY`
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`（默认是 `https://api.deepseek.com`）

### 3. 启动项目

```bash
python main.py
```

默认访问地址：

- `http://127.0.0.1:8000`

## 推送到 GitHub

```bash
git init
git add .
git commit -m "init"
git branch -M main
git remote add origin https://github.com/<your-name>/<repo>.git
git push -u origin main
```

## 部署方式

### 方式 A：Render（推荐，无服务器）

1. 把代码推送到 GitHub
2. Render 新建 Web Service，连接仓库
3. 配置：

- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

4. 在 Render 环境变量里配置：

- `APP_SECRET_KEY`
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`

### 方式 B：Docker + Caddy（有服务器）

项目已提供：

- `Dockerfile`
- `docker-compose.yml`
- `deploy/Caddyfile`
- `DEPLOY.md`

启动：

```bash
docker compose up -d --build
```

## 目录结构

```text
.
├── main.py
├── requirements.txt
├── templates/
│   └── index.html
├── static/
│   ├── app.js
│   ├── styles.css
│   ├── manifest.webmanifest
│   └── service-worker.js
├── deploy/
│   └── Caddyfile
├── Dockerfile
├── docker-compose.yml
└── DEPLOY.md
```

## 常见问题

### 1. `ModuleNotFoundError`

先确认当前 Python 环境，再执行：

```bash
python -m pip install -r requirements.txt
```

### 2. 登录/注册报错

- 检查 `APP_SECRET_KEY` 是否设置
- 检查数据库文件权限（`tasks.db`）
- 强制刷新浏览器缓存（`Cmd+Shift+R`）

### 3. AI 接口报错

- 检查 `OPENAI_API_KEY`
- 检查 `OPENAI_BASE_URL`
