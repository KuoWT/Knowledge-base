# Agent Query Contract v1

## 1. 目的

本文件定義 Hermes agent 與 Knowledge Base API 的查詢契約，讓 agent 以一致、可控、可追蹤的方式存取知識庫內容與任務狀態。

目標如下：

- 讓 agent 透過單一入口查詢知識內容
- 避免 agent 直接連線向量資料庫
- 讓回傳格式穩定，方便引用、摘要與後續 patch 產生
- 保留權限邊界，避免 agent 直接變更正式資料來源

## 2. 角色與責任

### 2.1 Agent

- 發出查詢請求
- 根據回傳內容生成回答、摘要、引用或修改建議
- 不直接操作 Qdrant
- 不直接操作 SQLite
- 不直接修改 Git repo

### 2.2 Knowledge Base API

- 接收 agent 查詢請求
- 驗證請求格式與參數
- 查詢 Qdrant 向量索引
- 查詢任務狀態資料
- 回傳標準化 JSON 結果

### 2.3 Qdrant

- 儲存 Markdown chunk 向量
- 儲存索引 payload
- 提供語意搜尋與文件 scroll

### 2.4 SQLite

- 儲存同步任務狀態
- 儲存索引紀錄與最後同步資訊

## 3. 可用查詢 API

### 3.1 搜尋知識

- `GET /api/v1/search?q=...`

用途：

- 搜尋與問題語意相近的 chunk
- 支援文件檢索、摘要與引用來源查找

建議參數：

- `q`：查詢文字，必填
- `limit`：回傳筆數，選填，預設 `10`
- `branch`：分支過濾，選填
- `file_path`：檔案過濾，選填
- `path`：`file_path` 的別名，選填

### 3.2 讀取文件 chunks

- `GET /api/v1/documents?path=...`

用途：

- 取得某個 Markdown 檔案的完整 chunks
- 支援按原文件順序回傳

建議參數：

- `path`：檔案路徑，必填
- `branch`：分支過濾，選填
- `limit`：回傳筆數上限，選填，預設 `100`
- `file_path`：`path` 的別名，選填

### 3.3 查詢任務狀態

- `GET /api/v1/sync-tasks/{task_id}`

用途：

- 查詢 webhook 或 reindex 任務的執行結果
- 查看失敗原因與時間戳

## 4. 搜尋請求格式

### 4.1 搜尋範例

```bash
GET /api/v1/search?q=meeting%20index&limit=5&branch=master
```

### 4.2 搜尋規則

- `q` 為必填
- `limit` 必須為正整數
- `branch` 若有提供，需與目前索引資料中的 `branch` 一致
- `file_path` 或 `path` 若有提供，僅回傳該文件相關 chunks

### 4.3 搜尋回傳格式

```json
{
  "query": "meeting index",
  "limit": 2,
  "items": [
    {
      "id": "uuid",
      "score": 0.98,
      "file_path": "Meeting/2026/Meeting Index.md",
      "file_name": "Meeting Index.md",
      "chunk_id": "chunk-1",
      "heading_path": "Agenda / Summary",
      "position": 120,
      "branch": "master",
      "commit_sha": "abc123",
      "content_hash": "hash",
      "text": "full chunk text",
      "text_preview": "first 256 chars",
      "payload": {
        "task_id": "task_xxx"
      }
    }
  ]
}
```

### 4.4 搜尋結果欄位定義

- `id`：Qdrant point id
- `score`：相似度分數
- `file_path`：原始 Markdown 路徑
- `file_name`：檔名
- `chunk_id`：chunk 識別碼
- `heading_path`：章節路徑
- `position`：chunk 在文件中的順序位置
- `branch`：索引分支
- `commit_sha`：來源 commit
- `content_hash`：檔案內容雜湊
- `text`：完整 chunk 內容
- `text_preview`：內容預覽
- `payload`：原始 payload

## 5. 文件請求格式

### 5.1 文件範例

```bash
GET /api/v1/documents?path=README.md&branch=master
```

### 5.2 文件回傳格式

```json
{
  "file_path": "README.md",
  "count": 3,
  "items": [
    {
      "id": "uuid",
      "score": null,
      "file_path": "README.md",
      "file_name": "README.md",
      "chunk_id": "chunk-0",
      "heading_path": "Intro",
      "position": 0,
      "branch": "master",
      "commit_sha": "abc123",
      "content_hash": "hash",
      "text": "full chunk text",
      "text_preview": "first 256 chars",
      "payload": {
        "task_id": "task_xxx"
      }
    }
  ]
}
```

### 5.3 文件查詢規則

- 回傳順序應以 `position` 為準
- 若 `branch` 有指定，只回傳該分支索引內容
- `path` 與 `file_path` 視為同義

## 6. 任務查詢格式

### 6.1 任務回傳格式

```json
{
  "task_id": "task_xxx",
  "status": "succeeded",
  "source": "gitlab_webhook",
  "event_type": "merge_request",
  "project_id": "27",
  "branch": "master",
  "commit_sha": "abc123",
  "delivery_id": "delivery-001",
  "trigger_reason": "webhook",
  "error": null,
  "created_at": "2026-06-05T14:51:30.441300+00:00",
  "updated_at": "2026-06-05T14:51:31.465104+00:00",
  "started_at": "2026-06-05T14:51:30.446481+00:00",
  "finished_at": "2026-06-05T14:51:31.464814+00:00"
}
```

### 6.2 可用狀態

- `queued`
- `running`
- `succeeded`
- `failed`
- `retrying`

## 7. 權限邊界

### 7.1 允許

- 搜尋知識內容
- 讀取文件 chunks
- 查詢任務狀態
- 產生修改建議

### 7.2 不允許

- 直接操作 Qdrant
- 直接操作 SQLite
- 直接修改 Git repo
- 直接刪除正式索引資料

### 7.3 寫入正式內容的流程

1. Agent 先產生建議或 patch
2. 人工審核
3. 寫入 Git repo
4. 透過 webhook / sync 更新索引

## 8. 錯誤處理

### 8.1 常見錯誤

- `400 query_required`
- `400 invalid_limit`
- `400 path_required`
- `404 not_found`
- `500` 系統錯誤

### 8.2 Agent 處理原則

- 查詢失敗時，先重試一次
- 若仍失敗，回報錯誤原因並停止推論
- 不可在資料未確認的情況下自行補寫正式內容

## 9. Citation 規範

Agent 回答時，建議引用以下格式之一：

- `[file_path#chunk_id]`
- `[file_path#heading_path]`
- `[task_id]`

範例：

- `參考來源：[README.md#chunk-1]`
- `根據 [Meeting/2026/Meeting Index.md#Agenda / Summary] 的內容...`

## 10. 版本策略

- 本契約版本：`v1`
- 若 API 回傳欄位變更，需同步升版
- 若搜尋或文件順序規則變更，需同步更新 agent 工具層與測試

## 11. 驗收標準

- agent 可透過 `/api/v1/search` 找到相關 chunk
- agent 可透過 `/api/v1/documents` 讀到完整文件 chunks
- agent 可透過 `/api/v1/sync-tasks/{task_id}` 查到任務狀態
- 回傳欄位可支援引用、摘要與 patch 生成
- agent 不需要直接存取 Qdrant 或 SQLite
