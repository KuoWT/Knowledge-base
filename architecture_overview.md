# 知識庫系統架構說明

## 1. 架構總覽
系統以 GitLab 作為唯一正式來源，Knowledge Base API 負責接收變更事件、執行同步、完成 embedding，最後寫入 Qdrant。

```mermaid
flowchart TD
  A[Engineer / User] --> B[Obsidian]
  B --> C[Git Push]
  C --> D[GitLab]
  E[User] --> F[Agent整理 md]
  F --> D
  D --> G[Webhook / API]

  G --> H[POST /webhooks/gitlab]
  G --> I[POST /api/v1/sync-tasks]
  G --> J[POST /api/v1/reindex]

  H --> K[Validate token / parse event]
  I --> L[Create sync task]
  J --> L
  K --> L

  L --> M[SQLite sync_tasks]
  M --> N[Background worker queue]
  N --> O[git pull --ff-only]
  O --> P[Detect changed files]
  P --> Q[Process .md only]
  Q --> R[Markdown Parse / Chunk]
  R --> S[Embedding]
  S --> T[Qdrant Writer]
  T --> U[Qdrant]

  L --> V[Task status]
  V --> W[GET /api/v1/sync-tasks]
  V --> X[GET /api/v1/sync-tasks/{task_id}]
  V --> Y[POST /api/v1/sync-tasks/{task_id}/retry]

  Z[GET /health] --> AA[Liveness]
  BB[GET /ready] --> CC[DB / Repo / Git checks]
```

## 2. 元件職責

### 2.1 Obsidian
- 工程師日常編寫知識內容的工具。
- 主要產出 Markdown。
- 可包含附件，但附件不進索引。

### 2.2 GitLab
- 唯一正式來源。
- 保存版本歷史、差異與回滾能力。
- merge 到主分支後才視為正式發布。

### 2.3 Webhook
- 只在 merge 事件後觸發正式同步。
- 將事件送往 Knowledge Base API。
- 建議加上驗證機制，避免偽造請求。

### 2.4 Knowledge Base API
- 知識庫同步與索引的核心協調層。
- 接收 webhook 後啟動增量同步。
- 透過自己的 MCP 寫入能力完成寫入。
- 管理任務狀態、重試與失敗紀錄。

### 2.5 MCP
- Knowledge Base API 的寫入介面。
- 負責把整理好的索引資料寫入後端。
- 可視為 API 內部已完成的能力之一。

### 2.6 Embedding
- 僅針對 Markdown 內容建立向量。
- 採 chunk 化處理。
- 變更內容需重新產生向量並更新 Qdrant。

### 2.7 Qdrant
- 儲存向量與 metadata。
- 供查詢端做相似度檢索。
- 支援增量 upsert 與刪除對應資料。

## 3. 兩種更新路徑

### 3.1 人工發布路徑
1. 工程師在 Obsidian 編寫內容。
2. Push 到 GitLab。
3. Merge 到主分支。
4. GitLab 發送 webhook。
5. API 建立同步任務。
6. 背景 worker 執行 `git pull --ff-only`。
7. API 只處理變更的 Markdown。
8. Chunk、embedding、寫入 Qdrant。

### 3.2 Agent 協作路徑
1. User 下指令給 agent。
2. agent 協助整理 md。
3. 內容進入 GitLab。
4. 仍以 merge 後版本作為正式內容。
5. 後續同步流程與人工路徑相同。

## 4. API 與狀態檢查

### 4.1 健康檢查
- `GET /health` 用來表示服務活著。
- `GET /ready` 用來檢查 DB、Repo、Git 是否可用。

### 4.2 任務 API
- `POST /webhooks/gitlab` 接收 GitLab webhook。
- `POST /api/v1/sync-tasks` 建立同步任務。
- `GET /api/v1/sync-tasks` 查詢任務列表。
- `GET /api/v1/sync-tasks/{task_id}` 查詢單筆任務。
- `POST /api/v1/sync-tasks/{task_id}/retry` 重新排程失敗任務。
- `POST /api/v1/reindex` 觸發手動重建。

## 5. 資料流原則
- GitLab 為唯一真實來源。
- Qdrant 只保存已合併版本對應的索引。
- 附件保留在 GitLab，但不進索引。
- 所有同步動作應可重跑且可追蹤。

## 6. 建議設計原則
- 事件驅動優先，不做手動批次重建。
- 增量處理優先，不做每次全量索引。
- 寫入與同步分離，避免 webhook 直接承擔重活。
- 失敗要可觀察，必要時可重試或人工介入。
