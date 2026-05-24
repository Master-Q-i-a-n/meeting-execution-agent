# Meeting Execution Agent 开发路线

本文档用于指导 `meeting-execution-agent` 项目的后续开发。它与 `PROJECT_OVERVIEW.md` 互补：`PROJECT_OVERVIEW.md` 负责说明整体架构与业务闭环，本文档负责说明开发顺序、模块拆分、接口模型和测试重点。

## 1. 开发原则

- 先做闭环，再做高级能力：优先跑通“会议纪要 -> 执行草案 -> 人工确认 -> 任务派发 -> 状态追踪 -> 会后追问”的最小可演示链路。
- MySQL 作为唯一事实源：会议、决策、待办、负责人、截止时间、确认记录、外部任务 ID、提醒状态都必须落在 MySQL。
- Qdrant 只做语义检索索引：会议原文 chunk、决策、待办和历史问答可向量化，但不能把 Qdrant 当作业务事实源。
- Agent 执行必须可恢复：每个工作流步骤、工具调用、失败原因、重试状态都要持久化，避免重复创建外部任务。
- 人工确认优先于自动执行：Agent 只生成执行草案，用户确认后才允许创建 Linear/Jira/飞书/日历任务。
- 每个阶段都要能演示：不要一开始同时做录音转写、多平台集成、复杂权限和完整桌面打包。

## 2. 阶段路线

### 阶段 1：基础工程与后端骨架

- 初始化 Python 后端工程，采用 `FastAPI + Pydantic v2 + SQLAlchemy async + Alembic`。
- 接入 MySQL，建立基础表结构和迁移流程。
- 接入 Redis、Celery 和 Celery Beat，预留异步任务和定时提醒能力。
- 接入 Qdrant，建立会议记忆 collection。
- 接入 OpenAI SDK 和 LangGraph，先完成最小工作流骨架。

### 阶段 2：文本会议纪要闭环

- 支持上传或粘贴文本、Markdown、PDF、Word 会议纪要。
- 解析会议内容，抽取决策摘要、待办事项、负责人、截止时间、风险项和未确认项。
- 将原始会议、解析结果、草案状态写入 MySQL。
- 将会议原文 chunk、决策和待办写入 Qdrant，支持后续语义追问。

### 阶段 3：人工确认与执行草案

- 生成可编辑执行草案，用户可以修改任务标题、负责人、截止时间、说明和优先级。
- 增加草案状态流转：`draft -> confirmed -> dispatching -> completed/failed`。
- 对每次确认保存快照，方便追踪 Agent 建议和用户最终选择的差异。

### 阶段 4：外部任务派发

- v1 先真接 Linear，使用 API Key 完成任务创建。
- Jira、飞书任务、Google Calendar 先保留 adapter 接口和 mock 实现。
- 所有外部工具调用必须记录请求、响应、外部 ID、状态和错误信息。
- 使用幂等键避免 Celery 重试时重复创建外部任务。

### 阶段 5：提醒与追问

- 使用 Celery Beat 定时扫描即将到期和已逾期的待办。
- v1 先支持应用内提醒或日志提醒，后续再扩展邮件、飞书、日历通知。
- 会后追问采用 MySQL + Qdrant 双路检索：MySQL 查结构化事实，Qdrant 查语义上下文。
- 回答必须带来源会议、相关待办和必要的原文片段引用。

### 阶段 6：桌面客户端

- 使用 `Tauri + Vue 3 + TypeScript + Vite` 构建桌面端。
- 桌面端只作为客户端，不内置 MySQL、Qdrant、Redis 或 Celery。
- 主要页面包括：会议列表、会议上传页、解析确认页、执行看板、任务详情页、追问对话页、集成配置页、工作流 Trace 页。
- 通过 HTTP 调用后端，通过 SSE 或 WebSocket 订阅长任务进度。

### 阶段 7：评测与项目打磨

- 准备 10-20 条会议纪要样例，覆盖中文会议、多人讨论、模糊截止时间、负责人缺失、多个决策混杂等场景。
- 评估待办抽取、负责人识别、截止时间解析、追问回答准确性和工具调用稳定性。
- 增加 README、架构图、演示数据和简历描述，保证项目能被快速理解。

## 3. 核心模块

- 桌面客户端：会议上传、执行草案确认、任务看板、追问对话、系统集成配置。
- FastAPI API 层：鉴权、会议管理、草案确认、任务查询、追问接口、工作流事件流。
- LangGraph 工作流：会议解析、草案生成、等待人工确认、外部派发、失败恢复。
- MySQL 持久化：业务事实、工作流状态、工具调用记录、提醒状态。
- Qdrant 检索层：会议原文、决策、待办、历史问答的向量检索。
- Redis + Celery：后台解析、向量入库、外部系统调用、失败重试、到期提醒。
- 外部集成层：Linear v1 真集成，Jira、飞书、Google Calendar 保留统一 adapter。

## 4. 数据模型与接口

### 主要数据模型

- `meetings`：会议基本信息、来源类型、原始内容路径、解析状态、创建时间。
- `meeting_chunks`：会议分块、chunk 类型、Qdrant point ID、来源位置。
- `decisions`：决策摘要、相关会议、置信度、来源片段。
- `action_items`：待办标题、说明、负责人、截止时间、优先级、状态、来源片段。
- `workflow_runs`：工作流类型、当前节点、运行状态、错误信息、重试次数。
- `tool_calls`：工具名称、请求参数、响应结果、幂等键、状态、错误信息。
- `reminders`：提醒目标、提醒时间、发送状态、发送渠道。
- `integrations`：外部系统类型、配置状态、凭证引用、启用状态。
- `external_task_mappings`：本地待办与 Linear/Jira/飞书/日历外部对象的映射。

### 核心 API

- `POST /meetings`：创建会议并上传或粘贴会议内容。
- `POST /meetings/{meeting_id}/analyze`：触发会议解析工作流。
- `GET /meetings/{meeting_id}`：查看会议详情、决策、待办和执行状态。
- `PATCH /meetings/{meeting_id}/draft`：修改执行草案。
- `POST /meetings/{meeting_id}/confirm`：确认草案并触发外部派发。
- `GET /action-items`：查看待办列表，支持状态、负责人和截止时间筛选。
- `POST /meetings/{meeting_id}/ask`：针对单场会议追问。
- `POST /ask`：跨会议追问。
- `GET /workflows/{workflow_id}/events`：查看工作流执行进度，使用 SSE 或 WebSocket。
- `POST /integrations/linear/test`：测试 Linear 配置。

### 状态约定

- 会议状态：`uploaded`、`analyzing`、`draft`、`confirmed`、`dispatching`、`completed`、`failed`。
- 待办状态：`draft`、`confirmed`、`dispatched`、`done`、`overdue`、`cancelled`。
- 工具调用状态：`pending`、`running`、`succeeded`、`failed`、`retrying`、`skipped`。

## 5. 测试与评测

- 单元测试：结构化抽取 schema、状态流转、截止时间解析、Qdrant metadata 构造、幂等键生成。
- API 测试：会议创建、解析触发、草案修改、确认执行、待办查询、追问接口。
- 集成测试：MySQL 事务、Celery 任务执行、Redis broker、Qdrant 检索、Linear mock 工具调用。
- 工作流测试：上传纪要后生成草案，人工确认后创建外部任务，失败后重试且不重复创建。
- 追问测试：能回答负责人、截止时间、未完成事项，并返回来源会议和相关待办。
- 评测指标：待办抽取准确率、负责人识别准确率、截止时间识别准确率、工具调用成功率、追问引用正确率。

## 6. 当前假设

- v1 先支持文本、Markdown、PDF、Word 会议纪要，录音转写放到 v2。
- v1 先真接 Linear，Jira、飞书任务、Google Calendar 先做 adapter 预留和 mock。
- 后端技术栈固定为 `FastAPI + MySQL + Qdrant + Redis + Celery + LangGraph`。
- 桌面端技术栈固定为 `Tauri + Vue 3 + TypeScript + Vite`。
- Python 环境使用 `D:\anaconda3\envs\Agent`。
- 当前保留 `langchain==1.2.15`，因此 `langgraph` 固定为 `>=1.1.5,<1.2.0`。
- MySQL 是业务事实源，Qdrant 是语义检索索引，二者职责不能混用。
- 桌面端不直接连接数据库或队列，只通过 FastAPI 后端访问业务能力。
