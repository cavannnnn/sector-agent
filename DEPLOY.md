# 部署指南 - 板块轮动 AI 智能体

## 目标
把仪表盘部署到 Render.com 免费版，实现：
- 7×24 永久在线
- 每周一自动刷新数据
- 朋友可以点"刷新"按钮触发数据更新

---

## 你需要做的（共 4 步，约 10 分钟）

### 第 1 步：注册 GitHub 账号（2 分钟）

1. 打开 https://github.com/signup
2. 用邮箱注册（免费）
3. 验证邮箱

### 第 2 步：把代码推到 GitHub（3 分钟）

1. 在 GitHub 首页点 **New repository**
2. 名字填 `sector-rotation-agent`，选 **Private**，点 **Create repository**
3. 在你的 Mac 上打开终端，复制粘贴以下命令：

```bash
cd /Users/cavanliu/WorkBuddy/A1/sector_agent

# 把你的 GitHub 邮箱和用户名替换进去
git config user.email "你的邮箱@gmail.com"
git config user.name "你的GitHub用户名"

# 关联远程仓库（把 你的用户名 替换成你的 GitHub 用户名）
git remote add origin https://github.com/你的用户名/sector-rotation-agent.git

# 提交代码
git add -A
git commit -m "Sector Rotation AI Agent - production ready"

# 推送（会要求输入 GitHub 用户名和密码/Token）
git push -u origin main
```

> **关于密码**：GitHub 已不支持用账号密码推送，需要用 Personal Access Token：
> 1. 打开 https://github.com/settings/tokens
> 2. 点 **Generate new token (classic)**
> 3. 勾选 `repo` 权限，生成后复制 Token
> 4. 推送时密码栏粘贴这个 Token

### 第 3 步：注册 Render 账号并部署（3 分钟）

1. 打开 https://render.com/register
2. 点 **Sign up with GitHub**（用 GitHub 账号直接登录）
3. 授权 Render 访问你的 GitHub
4. 点 **New +** → **Blueprint**
5. 选择你的 `sector-rotation-agent` 仓库
6. Render 会自动识别 `render.yaml` 配置文件
7. 点 **Apply** — Render 开始自动构建

### 第 4 步：等待部署完成（2 分钟）

- Render 会自动安装依赖、启动服务
- 部署完成后你会看到一个 URL，类似：
  `https://sector-rotation-agent-xxxx.onrender.com`
- **这就是你和朋友访问的永久网址！**

---

## 部署后你会拥有什么

| 功能 | 说明 |
|------|------|
| 永久在线 | 7×24 任何人都能访问 |
| 固定网址 | 不会变，直接分享链接 |
| 每周自动刷新 | 每周一早上 9 点自动抓最新数据 |
| 手动刷新 | 任何人点"刷新"按钮，2-3 分钟后数据更新 |
| 全部功能 | 仪表盘、历史记录、参数设置、预警、报告 |
| 持久存储 | SQLite 数据库在云端持久磁盘，不会丢失 |

---

## 关于免费版限制

| 限制 | 影响 | 解决方案 |
|------|------|---------|
| 15 分钟无访问会休眠 | 下次访问需等 ~30 秒唤醒 | 升级付费版 ($7/月) 或接受冷启动 |
| 512MB 内存 | 足够运行本项目 | 无需处理 |
| 750 小时/月 | 1 个 Web 服务 + 1 个 Cron 刚好够用 | 无需处理 |

---

## 常见问题

**Q: 推送代码时报错 "Authentication failed"**
A: 确保你用的是 Personal Access Token 而不是 GitHub 密码。

**Q: Render 部署失败**
A: 检查 Build Logs，确认 requirements.txt 和 start.sh 都在仓库根目录。

**Q: 首次访问很慢**
A: 首次部署需要初始化数据库（跑一次数据管道），可能需要 3-5 分钟。

**Q: 朋友点刷新后页面没反应**
A: 刷新需要 2-3 分钟，按钮会变成"刷新中..."，完成后自动重载页面。

---

## 本地开发

```bash
# 启动本地服务器
cd /Users/cavanliu/WorkBuddy/A1/sector_agent
python3 app.py

# 手动刷新数据
python3 scheduler.py

# 生成静态快照（用于 CloudStudio 部署）
python3 generate_static.py
```
