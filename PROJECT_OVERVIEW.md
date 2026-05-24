# Meeting Execution Agent 项目架构图

这个项目的核心目标是：把会议内容变成可确认、可派发、可追踪、可恢复、可追问的执行闭环。

## 总体架构

```mermaid
flowchart LR
    User[用户] --> Desktop[Tauri 桌面客户端<br/>Vue + TypeScript]

    Desktop -->|HTTP / SSE / WebSocket| API[FastAPI 后端 API]

    API --> Auth[用户与权限]
    API --> Meeting[会议服务]
    API --> QA[会后追问服务]
    API --> Workflow[LangGraph Agent 工作流]

    Workflow --> LLM[OpenAI / 大模型<br/>结构化抽取 + 总结 + 推理]
    Workflow --> MySQL[(MySQL<br/>业务事实源)]
    Workflow --> Qdrant[(Qdrant<br/>向量记忆)]
    Workflow --> Queue[Celery 异步任务]

    Queue --> Redis[(Redis<br/>Broker / 缓存 / 锁)]
    Queue --> External[外部系统<br/>Jira / Linear / 飞书 / Google Calendar]
    Queue --> Reminder[到期提醒任务]

    API --> MySQL
    API --> Qdrant
```

## 核心业务流程

```mermaid
flowchart TD
    A[上传会议纪要 / 录音] --> B[文本解析 / 录音转写]
    B --> C[会议内容结构化抽取]

    C --> D[生成决策摘要]
    C --> E[生成待办事项]
    C --> F[识别负责人和截止时间]
    C --> G[识别风险与未确认项]

    D --> H[生成执行草案]
    E --> H
    F --> H
    G --> H

    H --> I[人工确认 / 修改]
    I -->|确认| J[创建外部任务和日历]
    I -->|退回修改| H

    J --> K[记录执行状态]
    K --> L[定时提醒]
    K --> M[会后追问]

    M --> N[MySQL 查结构化事实]
    M --> O[Qdrant 查语义记忆]
    N --> P[生成可溯源回答]
    O --> P
```

## 模块职责

- 桌面客户端：上传会议、查看解析结果、人工确认、任务看板、追问对话、集成配置。
- FastAPI 后端：业务 API、鉴权、会议管理、任务管理、追问接口、工作流触发。
- LangGraph：编排会议解析、执行草案、人工确认、外部任务创建、失败恢复。
- MySQL：保存会议、纪要、决策、待办、负责人、截止时间、确认记录、外部任务 ID、提醒状态。
- Qdrant：保存会议原文、决策、待办和历史问答的向量索引，用于语义追问。
- Redis + Celery：处理转写、解析、向量入库、外部系统调用、失败重试、到期提醒。

## 项目能力闭环

```text
会议输入
  -> Agent 理解
  -> 人审确认
  -> 外部执行
  -> 状态追踪
  -> 到期提醒
  -> 历史追问
```

