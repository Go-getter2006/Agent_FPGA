# 部署与试点准备（阶段 6）

## 1. 组成

`docker-compose.yml` 一条命令启动四个容器：

| 容器 | 内容 | 说明 |
|---|---|---|
| db | PostgreSQL 16 | 数据存在 `pgdata` 数据卷；不对外开放端口 |
| api | 后端接口（uvicorn） | 启动时先执行数据库迁移（`alembic upgrade head`），再同步题目 |
| worker | 判题进程池 | 默认 2 个进程（`JUDGE_WORKERS`）；与 api 共用一个镜像 |
| web | nginx | 提供前端页面，`/api/` 转发给 api；关闭缓冲，助教对话的流式输出能逐字到达 |

后端镜像基于 Ubuntu 24.04，iverilog 12 / yosys 0.33 / verilator 5.020 与开发环境版本相同，判题结果一致。
api 和 worker 在容器里以普通用户（uid 10001）运行，不是 root。

## 2. 第一次部署

需要一台装了 Docker（含 compose 插件）的 Linux 服务器，建议 4 核 8 GB 以上。

```bash
git clone <仓库地址> agent_fpga && cd agent_fpga
cp .env.example .env
# 编辑 .env，至少填写：
#   POSTGRES_PASSWORD   数据库密码（随便一串长随机字符）
#   ANON_SALT           匿名 ID 的盐，例如 `openssl rand -hex 16` 的输出；定了以后不要再改，否则匿名 ID 全部变化
#   DEEPSEEK_API_KEY    不填也能用，只是提示全部走规则提示、助教对话不可用
docker compose up -d --build
docker compose ps                     # 四个容器都是 running / healthy
curl http://localhost:8080/api/health # {"ok": true, ...}
```

创建教师账号和班级（教师密码随机生成，只显示一次）：

```bash
docker compose exec api python -m backend.scripts.create_class \
  --teacher T001 --name 王老师 --class "数字电路实验 1 班" --term "2026 秋"
```

之后教师登录网站，在“班级管理”里粘贴学生名单（学号,姓名[,分组]），系统生成每个学生的初始密码。

说明：
- 网站默认在 `8080` 端口（`.env` 里的 `WEB_PORT`）。学校要求 HTTPS 时，在前面再放一层学校统一的反向代理或在 nginx 里配证书，配好后把 `COOKIE_SECURE=true`；只用 http 访问时必须保持 `false`，否则登录 Cookie 发不出去。
- 服务器在国内、访问 Docker Hub / PyPI / npm 慢时，给 Docker 配镜像加速，或在构建前给 pip、npm 配国内源。
- 更新代码：`git pull && docker compose up -d --build`（迁移在 api 启动时自动执行）。

## 3. 备份与恢复

```bash
deploy/backup.sh                                  # 备份到 backups/db-时间.dump，自动删 30 天前的
deploy/restore.sh backups/db-20261109-023000.dump # 恢复（会覆盖当前数据，先询问）
```

- 备份用 `pg_dump -Fc`（压缩格式），备份完会用 `pg_restore --list` 自检一次，通过后才保存成正式文件名。
- 恢复时自动暂停 api 和 worker，在一个事务里恢复（失败则什么都不改），完成后再启动。
- 建议每天定时备份，并把 `backups/` 同步到另一台机器或网盘：
  `30 2 * * *  /opt/agent_fpga/deploy/backup.sh >> /var/log/agent_backup.log 2>&1`
- 只备份数据库。判题日志（`/data/logs`）和研究导出（`/data/exports`）都能从数据库重新生成。
- 试点开始前至少演练一次“备份 → 删数据 → 恢复 → 核对”（阶段 6 的演练记录见第 6 节）。

## 4. 知情同意书

正文和版本号都在 `backend/app/data/consent.md`：

```markdown
---
version: v1
---
# 参与研究的知情同意
……
```

- 定稿：改正文，同时改文件头里的 `version`。也可以不改仓库里的文件，把定稿文件放到服务器上，用环境变量 `CONSENT_FILE` 指向它（容器里需要挂载进去）。
- 版本号一变，**所有学生**（包括之前选了“同意”或“暂不参与”的）下次进入学生端都会先看到新版本，重新选择后才能继续做题；页面会提示“知情同意书有更新”。
- 每次选择都写事件日志（`consent.accept` / `consent.decline`，带版本号）；班级管理页显示每个学生同意的版本。
- 研究导出只包含当前状态为“同意”的学生。
- 当前文件是草案（`v1-draft`），其中【】里的内容（数据保存年限、研究负责人联系方式）要在伦理审查定稿时填写。

## 5. 学生代码的资源限制

学生代码由 iverilog / vvp / yosys / verilator 执行。除了原有的 10 秒墙钟超时，判题时在 Linux 上用 `prlimit` 给每个工具进程加上限：

| 限制 | 默认 | 环境变量 | 超出时 |
|---|---|---|---|
| CPU 时间 | 超时秒数 + 5 秒 | — | 按超时处理 |
| 内存（地址空间） | 2048 MB | `JUDGE_MEMORY_MB` | 工具报错退出 |
| 写文件 / 输出大小 | 32 MB | `JUDGE_OUTPUT_MB` | 按超时处理 |

工具的输出先写到临时文件，所以输出上限同样限制了 `$display` 死循环这类“刷屏”代码：到 32 MB 就被终止，不用等满 10 秒，也不会撑满判题进程的内存。
`JUDGE_RLIMITS=0` 关闭这些限制（没有 prlimit 的系统如 macOS 自动不加）。容器以非 root 用户运行，学生代码无法修改系统文件。
这不是完整的沙箱（没有禁网、没有独立文件系统）；仿真器本身不提供执行任意系统命令的能力，对课程实验够用。

## 6. 阶段 6 的检查记录（2026-11-09，开发云环境）

- **PostgreSQL 16**（compose 里的 db 容器）：`alembic upgrade head` 成功，`alembic check` 无差异。
- **后端测试改用 PostgreSQL 跑**：`TEST_DATABASE_URL=postgresql+psycopg://… pytest backend/tests` → 173 通过、13 跳过。
  跳过的是教师端“与 SQL 直接统计一致”的核对：核对用的 SQL 按 SQLite 方言写（`json_each` 等），这些页面的接口在 PostgreSQL 上另外逐个请求过，都正常返回。
- **整套流程**：后端接口和判题进程连 PostgreSQL，前端用 `deploy/nginx.conf` 的 nginx 容器提供。经 nginx 走通：
  学生登录 → 知情同意 → 锁定预测 → 提交 → worker 判题（3.6 秒）→ 结果；助教对话的流式输出逐段到达（不是最后一次性到）；
  教师端总览、热力图、误区、分组、作业、ICAP、班级管理、题目分析都返回 200，研究导出任务正常创建。
- **备份恢复演练**：`deploy/backup.sh`（728 KB）→ 删除全部学生并删掉 events 表 → `deploy/restore.sh` →
  各表行数与备份前完全一致（users 65、attempts 1201、events 6949、predictions 1202、hints 574、chat_messages 284 等）；
  恢复后学生照常登录，新提交的编号接着往下排（1202），判题正常。
- **资源限制**：`$display` 零延迟死循环的代码 0.6 秒被终止并按超时处理（不加限制时要等满 10 秒）。
- 并发测试按要求不做。
- **没有验证的**：两个镜像的完整构建（`docker compose build`）。开发云环境里容器访问外网要经过一个需要额外证书的代理，这个证书不允许装进镜像，所以只做了 Dockerfile 静态检查（`docker build --check`，无告警）和 nginx 配置检查（`nginx -t`）。第一次在学校服务器上部署时，请按第 2 节构建并确认 `docker compose ps` 四个容器正常。
