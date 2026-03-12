# 公网部署（Docker + Caddy + HTTPS）

## 1. 服务器准备
- 一台 Linux 服务器（推荐 Ubuntu 22.04）
- 已安装 Docker 与 Docker Compose
- 域名 `A` 记录已指向服务器公网 IP

## 2. 配置环境变量
在项目根目录执行：

```bash
cp .env.example .env
```

编辑 `.env`，至少填写：
- `DOMAIN`
- `TLS_EMAIL`
- `APP_SECRET_KEY`
- `OPENAI_API_KEY`

## 3. 启动服务

```bash
docker compose up -d --build
```

启动后访问：
- `https://你的域名`

## 4. 常用运维命令
查看日志：

```bash
docker compose logs -f app
docker compose logs -f caddy
```

重启：

```bash
docker compose restart
```

停止：

```bash
docker compose down
```

## 5. 安全建议
- 不要把 `.env` 提交到仓库
- 定期更换 `APP_SECRET_KEY`
- 服务器防火墙仅开放 `80/443`
- 若只有少量用户，建议增加注册邀请码机制
