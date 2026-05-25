# Meeting Execution Agent

把会议纪要变成可审核、可派发、可追踪、可追问的执行闭环。

当前版本支持：

- 上传或粘贴会议纪要
- 使用阿里百炼 Qwen 抽取决策、待办、负责人、截止时间、风险和待澄清项
- LangGraph 编排可恢复的会议执行工作流
- 人工审核草稿，必要时强制跳过澄清继续执行
- 将确认后的待办派发到 Linear
- MySQL 保存业务事实，Qdrant 保存语义索引
- Redis + Celery 处理异步分析、派发和提醒
- Vue Web 客户端查看会议、草稿、Trace、提醒和追问
- LangSmith 离线评测抽取、追问和工具稳定性

## 技术栈

- Backend：FastAPI、Pydantic v2、SQLAlchemy async、Alembic
- Workflow：LangGraph
- Queue：Redis、Celery、Celery Beat
- Database：MySQL
- Vector DB：Qdrant
- LLM：阿里百炼 OpenAI-compatible API，默认 `qwen-plus`
- Embedding：阿里百炼 `text-embedding-v3`，默认 1024 维
- Integration：Linear GraphQL API
- Frontend：Vue 3、TypeScript、Vite、Pinia、Vue Router
- Evals：LangSmith

## 目录结构

```text
meeting-execution-agent/
  backend/                 # FastAPI 后端
    app/
      agents/              # LangGraph 工作流
      api/routers/         # APIRouter 分组
      core/                # 配置、日志、Redis 等基础设施
      db/                  # SQLAlchemy session/base
      evals/               # LangSmith 评测
      integrations/        # Linear 和外部工具 adapter
      llm/                 # 百炼 LLM / embedding 封装
      models/              # SQLAlchemy 模型
      retrieval/           # Qdrant 访问层
      schemas/             # Pydantic schema
      services/            # 业务服务
      workers/             # Celery app 和 task
    alembic/               # 数据库迁移
    tests/                 # 后端测试
  desktop/                 # Vue Web 客户端
  samples/                 # 示例会议纪要
  DEVELOPMENT_ROADMAP.md   # 开发路线
  PROJECT_OVERVIEW.md      # 架构图和流程图
```

## 环境配置

后端配置放在 `backend/.env`，可以参考 `backend/.env.example`。

关键配置：

```env
DASHSCOPE_API_KEY=
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-plus

EMBEDDING_MODEL=text-embedding-v3
EMBEDDING_DIMENSIONS=1024

LINEAR_API_KEY=
LINEAR_API_URL=https://api.linear.app/graphql
LINEAR_DEFAULT_TEAM_ID=

LANGSMITH_API_KEY=
LANGSMITH_TRACING=true
LANGSMITH_PROJECT=meeting-execution-agent-evals
```

不要把真实 API Key 写进代码或提交到 Git。

## 启动后端

先启动 MySQL、Redis 和 Qdrant。

Redis：

```powershell
redis-server.exe
```

Qdrant：

```powershell
cd D:\Qdrant
.\qdrant.exe
```

如果本机开了系统代理，建议每个后端相关终端先设置本地绕过：

```powershell
$env:NO_PROXY="localhost,127.0.0.1,::1"
$env:no_proxy=$env:NO_PROXY
```

启动 FastAPI：

```powershell
cd E:\MyWork\Agent\meeting-execution-agent\backend
& "D:\anaconda3\envs\Agent\python.exe" -m app.main
```

启动 Celery worker：

```powershell
cd E:\MyWork\Agent\meeting-execution-agent\backend
& "D:\anaconda3\envs\Agent\python.exe" -m celery -A app.workers.celery_app worker --loglevel=info --pool=solo
```

启动 Celery Beat：

```powershell
cd E:\MyWork\Agent\meeting-execution-agent\backend
& "D:\anaconda3\envs\Agent\python.exe" -m celery -A app.workers.celery_app beat --loglevel=info
```

健康检查：

```text
GET http://127.0.0.1:8003/health
GET http://127.0.0.1:8003/health/redis
GET http://127.0.0.1:8003/health/qdrant
```

## 启动前端

```powershell
cd E:\MyWork\Agent\meeting-execution-agent
npm.cmd --prefix desktop install
npm.cmd --prefix desktop run dev
```

默认访问：

```text
http://127.0.0.1:5173
```

## 常用接口

创建会议：

```text
POST /meetings
POST /meetings/upload
```

启动分析：

```text
POST /meetings/{meeting_id}/analyze
```

查看会议详情：

```text
GET /meetings/{meeting_id}
```

恢复工作流：

```text
POST /workflow-runs/{workflow_run_id}/continue
```

常见 action：

- `retry_input`
- `retry_extraction`
- `force_continue`
- `confirm_draft`
- `retry_dispatch`

确认草稿：

```text
POST /analysis-drafts/{draft_id}/confirm
```

会后追问：

```text
POST /meetings/{meeting_id}/ask
POST /ask
```

查看提醒：

```text
GET /reminders?status=unread
```

## 典型流程

1. 上传或粘贴会议纪要。
2. 调用分析接口，Celery 执行 LangGraph 工作流。
3. 工作流检查输入质量，调用百炼抽取结构化草稿。
4. 后端规则补齐未确认项，例如负责人缺失、截止时间缺失。
5. 有未确认项时进入 `wait_for_clarification`，用户可以补充信息或强制继续。
6. 草稿写入 MySQL，会议片段写入 Qdrant。
7. 用户审核并确认草稿。
8. 工作流继续派发 Linear Issue。
9. Celery Beat 扫描到期提醒。
10. 用户通过 MySQL + Qdrant 双路检索做会后追问。

## 测试

后端：

```powershell
cd E:\MyWork\Agent\meeting-execution-agent\backend
& "D:\anaconda3\envs\Agent\python.exe" -m ruff check app tests
& "D:\anaconda3\envs\Agent\python.exe" -m pytest
```

前端：

```powershell
cd E:\MyWork\Agent\meeting-execution-agent
npm.cmd --prefix desktop run typecheck
npm.cmd --prefix desktop run build
```

## LangSmith 评测

评测数据集：

```text
backend/app/evals/datasets/meeting_eval_cases.jsonl
```

第一次建议先跑小样本：

```powershell
cd E:\MyWork\Agent\meeting-execution-agent\backend
& "D:\anaconda3\envs\Agent\python.exe" -m app.evals.run_langsmith_evals --suite extraction --limit 3
```

完整评测：

```powershell
& "D:\anaconda3\envs\Agent\python.exe" -m app.evals.run_langsmith_evals --suite all
```

评测命令会自动同步本地 JSONL 到 LangSmith dataset：

```text
meeting-execution-agent-v1
```

评测套件：

- `extraction`：真实百炼抽取 + Pydantic 校验 + 澄清规则
- `qa`：真实 embedding + Qdrant 检索 + 百炼回答
- `tool_stability`：本地幂等与状态稳定性检查，不创建真实 Linear 任务

## 相关文档

- `PROJECT_OVERVIEW.md`：整体架构图和 LangGraph 流程图
- `DEVELOPMENT_ROADMAP.md`：阶段路线和模块规划
- `order.txt`：本地常用命令草稿
