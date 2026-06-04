# 知識庫系統開發規格與 API / Webhook 規範

## 1. 文件目的
本文件定義知識庫系統的工程實作規格、元件責任、API 介面、GitLab Webhook 規範與同步任務流程，供後端、平台與維運團隊實作與驗證。

## 2. 系統目標
- GitLab 為唯一正式內容來源。
- 內容更新分為人工流程與 Agent 協作流程。
- 只索引 Markdown 內容，附件不建立索引。
- 內容合併後自動同步到 Embedding 與 Qdrant。
- Hermes 透過自身 MCP 寫入介面完成資料寫入。

## 3. 系統元件

### 3.1 來源與編寫端
- `Obsidian`：工程師編寫工具。
- `GitLab`：正式內容庫與版本來源。
- `Agent`：依使用者指令協助整理 md。

### 3.2 同步與索引端
- `Knowledge Base API`：同步協調、任務管理、索引串接核心。
- `MCP`：Hermes 的寫入介面。
- `Embedding Service`：負責 chunk 後的向量化。
- `Qdrant`：向量資料庫與 metadata 儲存。

## 4. 設計原則
- 單一來源原則：所有正式內容最終以 GitLab 為準。
- 增量更新原則：只處理變更檔案，不做預設全量重建。
- 任務化原則：Webhook 事件應轉成可追蹤的同步任務。
- 可重跑原則：失敗任務需可重試與補償。
- 索引分離原則：Markdown 索引與附件保留分離處理。

## 5. 資料流與處理流程

### 5.1 正常同步流程
1. GitLab merge 觸發 webhook。
2. Webhook 送到 Hermes。
3. Hermes 驗證來源與事件。
4. Hermes 建立同步任務。
5. Hermes 執行 `git pull`。
6. Hermes 比對變更檔案。
7. Hermes 僅處理 `.md`。
8. Markdown 進行 parse 與 chunk。
9. 送入 Embedding Service 取得向量。
10. 透過 Hermes MCP 寫入 Qdrant。
11. 任務標記成功並保存紀錄。

## 6. Hermes 職責
- 接收 webhook 事件。
- 驗證事件合法性。
- 建立與管理同步任務。
- 執行 git pull 與變更比對。
- 協調 markdown parse、chunk、embedding。
- 透過 MCP 寫入 Qdrant。
- 管理失敗重試、狀態查詢與審計紀錄。

## 7. Webhook 規範

### 7.1 觸發條件
- 只接受 `merge 到主分支` 的正式同步事件。
- 不以一般 push 作為正式索引觸發點。
- 若 GitLab 設定允許，建議額外保留 merge request merged 事件與 push 到 main 事件中的其中一種作為主觸發源，實作上需固定單一路徑避免重複觸發。

### 7.2 Webhook 驗證
建議採用以下其中一種或多種方式：
- `secret token`
- `signature / HMAC`
- `IP allowlist`

### 7.3 Webhook 事件處理原則
- 同一個 merge 事件需具備去重能力。
- webhook 只負責觸發任務，不承擔重型處理。
- webhook 接收成功與任務處理成功需分開紀錄。

### 7.4 建議事件欄位
以下為建議最小欄位集合：
- `event_type`
- `project_id`
- `project_path`
- `branch`
- `target_branch`
- `commit_sha`
- `before_sha`
- `after_sha`
- `merged_by`
- `merged_at`
- `timestamp`
- `delivery_id`
- `signature`

### 7.5 Webhook 驗證回應
- 驗證成功：回 `200 OK`
- 驗證失敗：回 `401 Unauthorized` 或 `403 Forbidden`
- 事件格式錯誤：回 `400 Bad Request`
- 系統暫時不可用：回 `503 Service Unavailable`

## 8. Hermes API 規範

### 8.1 任務建立 API
#### `POST /api/v1/sync-tasks`
建立一筆同步任務，通常由 webhook 呼叫。

##### Request body
```json
{
  "source": "gitlab_webhook",
  "event_type": "merge",
  "project_id": "123",
  "branch": "main",
  "commit_sha": "abc123",
  "delivery_id": "delivery-001",
  "trigger_reason": "merge_to_main"
}
```

##### Response
```json
{
  "task_id": "task_001",
  "status": "queued"
}
```

### 8.2 任務查詢 API
#### `GET /api/v1/sync-tasks/{task_id}`
查詢單筆同步任務狀態。

##### Response
```json
{
  "task_id": "task_001",
  "status": "running",
  "source": "gitlab_webhook",
  "commit_sha": "abc123",
  "started_at": "2026-06-03T10:00:00Z",
  "updated_at": "2026-06-03T10:02:00Z",
  "error": null
}
```

### 8.3 任務列表 API
#### `GET /api/v1/sync-tasks`
查詢任務列表，支援過濾條件。

##### Query 建議參數
- `status`
- `source`
- `from`
- `to`
- `project_id`

### 8.4 手動重跑 API
#### `POST /api/v1/sync-tasks/{task_id}/retry`
針對失敗任務進行重試。

##### Response
```json
{
  "task_id": "task_001",
  "status": "queued"
}
```

### 8.5 強制重新索引 API
#### `POST /api/v1/reindex`
指定範圍重新建立索引，供維運或修復使用。

##### Request body
```json
{
  "scope": "repository",
  "commit_sha": "abc123",
  "paths": [
    "docs/a.md",
    "docs/b.md"
  ],
  "reason": "manual_rebuild"
}
```

##### 使用條件
- 需有管理權限。
- 僅供維運或修復用途。
- 不應作為日常同步主流程。

## 9. Markdown 處理規範

### 9.1 解析規則
- 只處理 `.md` 檔。
- 先清理 frontmatter 與不需要進索引的區塊。
- 保留標題層級、段落與內容順序。

### 9.2 Chunk 規則
- 以標題或段落切 chunk。
- chunk 需可追溯到原始檔案與位置。
- chunk 長度上限需依 embedding model 與查詢品質調整。

### 9.3 Metadata
每個 chunk 建議保存以下 metadata：
- `file_path`
- `file_name`
- `chunk_id`
- `heading_path`
- `commit_sha`
- `updated_at`
- `repository`
- `branch`
- `content_hash`

## 10. Embedding 規範
- 只對 Markdown chunk 產生 embedding。
- 同一檔案變更後，需更新對應 chunk 的向量。
- 若檔案刪除，需同步刪除對應向量資料。
- embedding model 需可版本化，以利未來重建與比較。

## 11. Qdrant 寫入規範

### 11.1 Collection 設計
- collection 命名需可區分環境與資料域。
- 建議命名方式保留：
  - 環境
  - 系統名稱
  - 內容域

### 11.2 寫入方式
- 採 `upsert` 更新新增或變更 chunk。
- 採 `delete` 移除已刪除內容。
- 寫入需具備 idempotency，避免重複事件造成重複資料。

### 11.3 Payload 建議欄位
- `file_path`
- `file_name`
- `chunk_id`
- `heading_path`
- `commit_sha`
- `updated_at`
- `content_hash`
- `repository`
- `branch`

## 12. Hermes MCP 規範
- Hermes 透過自己的 MCP 寫入能力完成索引寫入。
- MCP 視為已完成能力，不另行對外暴露為獨立正式來源。
- 寫入失敗需能回傳明確錯誤碼與錯誤訊息。
- MCP 寫入需支持重試與去重。

## 13. 任務狀態機

### 13.1 狀態定義
- `queued`
- `running`
- `succeeded`
- `failed`
- `retrying`
- `skipped`

### 13.2 狀態轉移原則
- 任務建立後進入 `queued`
- 開始處理後進入 `running`
- 成功後進入 `succeeded`
- 失敗後進入 `failed`
- 重試時進入 `retrying`
- 無需處理或重複事件可進入 `skipped`

## 14. 錯誤處理

### 14.1 Webhook 錯誤
- 驗證失敗：拒絕處理
- 格式錯誤：回傳 400
- 重複事件：記錄後跳過或合併為同一任務

### 14.2 同步錯誤
- `git pull` 失敗：任務保留為失敗或重試中
- Markdown parse 失敗：記錄檔案層級錯誤
- Embedding 失敗：保留原始 chunk 與重試狀態
- Qdrant 寫入失敗：可重試或人工介入

## 15. 監控與可觀測性
- 需記錄 webhook 接收時間與結果。
- 需記錄任務建立、開始、完成、失敗時間。
- 需記錄每次同步的 commit_sha 與處理範圍。
- 需記錄 Qdrant 寫入成功率與失敗原因。
- 需保留重試次數與最後錯誤訊息。

## 16. 驗收條件
- merge 後 webhook 可觸發 Hermes。
- Hermes 能建立同步任務並完成增量處理。
- 只有 Markdown 進入索引。
- 附件保留但不建立索引。
- Qdrant 內容可正確 upsert 與 delete。
- 任務狀態與錯誤紀錄可查詢。

## 17. 上線前檢查清單
- Webhook 驗證已啟用。
- 任務狀態機已實作。
- 重試機制已實作。
- Qdrant collection 命名已確認。
- MCP 寫入介面已可用。
- 權限與管理 API 已加保護。

## 18. 待確認項目
- 主分支是否固定為 `main`。
- 是否以 merge request merged 為唯一 webhook 來源。
- chunk 長度與切分策略。
- Embedding model 的版本與切換方式。
