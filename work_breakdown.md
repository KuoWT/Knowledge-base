# 知識庫系統任務拆分清單

## 1. 需求確認
- 確認 GitLab 為唯一正式來源。
- 確認附件可附上但不建立索引。
- 確認正式同步只在 merge 後觸發。
- 確認系統支援人工流程與 agent 協作流程。

## 2. 來源與版本管理
- 建立 Obsidian 的資料夾與命名規範。
- 定義 Markdown 文件格式與模板。
- 定義附件放置方式。
- 定義 GitLab 分支策略與 merge 規則。

## 3. Webhook 與事件處理
- 設計 GitLab webhook 事件格式。
- 驗證 webhook 來源。
- 限定只有 merge 事件進入正式同步。
- 設計事件去重與重試機制。

## 4. Hermes 同步流程
- 接收 webhook 後建立同步任務。
- 透過 git pull 取得最新內容。
- 比對變更檔案。
- 對刪除、修改、新增做不同處理。

## 5. Markdown 處理
- 解析 Markdown 結構。
- 去除不需要進索引的內容。
- 依段落或標題切 chunk。
- 保留必要 metadata。

## 6. Embedding 與索引
- 選定 embedding model。
- 建立 chunk -> embedding -> Qdrant 的流程。
- 支援增量 upsert。
- 支援刪除已失效的索引資料。

## 7. Qdrant 設計
- 定義 collection 命名規則。
- 定義 payload schema。
- 定義查詢所需 metadata。
- 定義版本更新與刪除策略。

## 8. Hermes MCP 寫入層
- 確認 MCP 寫入介面已完成並可用。
- 確認 Hermes 透過 MCP 寫入索引資料。
- 確認寫入失敗時的錯誤回報方式。

## 9. 監控與維運
- 建立同步成功與失敗紀錄。
- 建立重試機制。
- 建立任務狀態查詢方式。
- 視需要加入告警與報表。

## 10. 測試項目
- 測試 merge 後 webhook 是否正常觸發。
- 測試 Markdown 新增、修改、刪除是否正確同步。
- 測試附件存在時不會進入索引。
- 測試 Qdrant 是否正確 upsert 與 delete。
- 測試 Hermes MCP 寫入流程是否穩定。

## 11. 建議開發順序
1. 先確認 GitLab webhook 與 merge 事件。
2. 完成 Hermes 拉取與變更辨識。
3. 完成 Markdown chunk 與 embedding。
4. 完成 Qdrant 寫入與刪除。
5. 補上重試、狀態與監控。
6. 最後整理 agent 協作流程與使用規範。
