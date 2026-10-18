# CHANGELOG

本專案遵循 [Semantic Versioning](https://semver.org/) 與 [Keep a Changelog](https://keepachangelog.com/) 規範。

## [1.0.0] - 2026-10-12

### 新增
- 🎉 專案初始化：本地 AI Telegram Bot 架構
- 🦙 Ollama 整合：支援本地開源模型 (qwen2.5, llama3.1 等)
- 🔧 Function Calling 支援：模型自主決定搜尋時機與關鍵字
- 🔍 雙搜尋引擎：
  - DuckDuckGo HTML 搜尋 (免費、無 API Key、通用網頁)
  - Google News RSS 搜尋 (穩定、繁體中文新聞)
- 🛡️ 權限控管：白名單 (ALLOWED_USER_IDS) + 每日配額 (MAX_DAILY_REQUESTS)
- 💾 本地持久化：對話歷史、配額、日誌皆存 JSON 檔案
- ⚡ 漸進式回覆：思考中 → 搜尋中 → 整理中 → 完成
- 📦 uv 專案管理：pyproject.toml + uv.lock 鎖定依賴
- 🧪 環境檢查腳本：check_env.py 一鍵驗證

### 變更
- 從 Google Apps Script (GAS) 架構遷移至本地 Python + Ollama
- 移除 Gemini API 依賴，改用本地模型無限制使用
- 移除 Google Sheets/CacheService 依賴，改用本地檔案儲存

### 修復
- Python 3.9 相容性調整 (建議 3.10+)
- HTML 實體解析錯誤修復 (歡迎訊息中 `<關鍵字>` 改為 `<code>關鍵字</code>`)
- 配額檢查死鎖修復 (`check_and_consume_quota` 雙重鎖問題)

---

## [1.0.1] - 2026-10-12

### 修復
- 修復 `check_and_consume_quota` 遞迴鎖死鎖問題
- 修復 Telegram HTML 解析錯誤 (歡迎訊息、說明訊息)
- 預設模型更新為 `llama3.1` (Function Calling 更穩定)

---
## [1.0.2] - 2026-10-12

### 修復
- **修復 Telegram Long Polling 衝突問題**：解決 `Conflict: terminated by other getUpdates request` 錯誤，根因是多個 bot 實例同時輪詢
- **修復 DuckDuckGo 搜尋失效**：移除 `Accept-Encoding: br` (Brotli) 避免解壓失敗，簡化 CSS 選擇器為 `.result__body` 避免重複解析
- **修復 Google News XML 實體解碼**：修正 `decode_xml_entities` 中的智慧引號處理 (`\u2018`, `\u2019`, `\u201c`, `\u201d`)
- **修復 Markdown 解析器衝突**：使用 placeholder 保護策略，避免程式碼區塊被斜體/粗體規則誤處理
- **修復 `search_sync` event loop 衝突**：使用 `ThreadPoolExecutor` 隔離執行避免 `RuntimeError: This event loop is already running`

### 新增
- 完善除錯日誌：新增 `_debug_log` 輔助函數，追蹤 handler 註冊、polling 啟動、訊息處理流程
- 完善測試套件：`test/` 目錄新增 `test_settings.py`, `test_search.py`, `test_markdown.py`, `test_ollama.py`, `test_conversation.py`, `test_settings.py`, `run_all.py`

---

## [1.0.3] - 2026-10-18

### 修復
- **修復 HTML 跳脫失效**：`markdown_to_html` 的 `&`/`<`/`>` 跳脫原本是空操作 (`replace('&', '&')`)，回答含 `<`、`&` 時 Telegram HTML 解析失敗
- **修復誤判 HTML 標籤**：只保留 Telegram 支援的標籤 (`b`/`i`/`code`/`a`…)，`5 < 10 & 3 > 2` 這類文字不再被當成標籤原樣送出
- **修復來源標題、使用者名稱未跳脫**：搜尋來源標題、`/start` 名稱、錯誤訊息改用 `html.escape`
- **修復 Google News 實體解碼**：`decode_xml_entities` 原本為空操作，改用 `html.unescape`；`clean_html` 改為先解碼再移除標籤
- **工具參數相容 JSON 字串**：`tool_calls[].function.arguments` 若為字串則 `json.loads`，解析失敗記錄警告
- **修復長回覆發送失敗**：超過 Telegram 4096 字元上限時自動分段；HTML 解析失敗改送純文字
- **修復錯誤時卡在「思考中」**：`_process_query` 捕獲 Ollama 逾時/連線錯誤並回覆友善訊息，失敗時退還額度 (`refund_quota`)；註冊全域 `error handler`
- **修復多用戶排隊**：啟用 `concurrent_updates(True)`；狀態訊息改以 `update_id` 區分，避免同聊天室並發互相覆蓋
- **修復上下文被截斷**：新增 `OLLAMA_NUM_CTX` (預設 8192)，`num_predict` 預設降為 2048
- **修復網址被斜體破壞**：`markdown_to_html` 保護連結與純網址，`foo_bar_baz` 不再變成 `<i>`
- **修復關鍵字提取誤刪字**：「和平」不再變「平」；保留 `C++`、`C#`、`llama3.1`
- **修復 `/search` 空查詢扣額度**：先檢查參數再扣額度
- **修復未授權可用指令**：`/status`、`/reset`、`/models` 加入白名單檢查
- **修復無效 SEARCH_ENGINE 崩潰**：啟動時驗證 `SEARCH_ENGINE`、`ALLOWED_USER_IDS` 格式
- **修復 LOG_LEVEL 無效**：日誌等級依 `.env`；除錯訊息改為 DEBUG 等級，移除 `print`
- **修復 `*_sync` 使用已棄用的 `get_event_loop`**：統一使用 `search.run_sync`
- **修復模型每題都搜尋、照抄搜尋結果**：新增 `SEARCH_DECISION` (預設 `router`)，模型先輸出 JSON 判斷是否需要搜尋；system prompt 改為預設直接回答並加入今日日期 (ADR-014)
- **修復翻譯題不翻譯、計算不穩定**：system prompt 允許依要求輸出其他語言；回答 temperature 0.7 → 0.3
- **縮短回覆時間**：實測瓶頸為回答過長 (輸出約 23 tok/s)，要求清單精簡、不逐項附網址，回答 `num_predict` 上限 1024；115-1 課程題 72~108 秒降至約 40 秒
- **修復 ddgs 天氣等查詢 0 筆**：排除 wikipedia/grokipedia 引擎 (region `tw-tzh` 會查詢不存在的網域)
- **修復縮排子項目未轉換**：`\t*`、`  -` 開頭的子項目轉為 `◦`
- **改善網頁內文摘錄**：全文放得下就全給；關鍵字不再拆出「11」「15」等數字片段；超過上限時依序保留命中行、短行 (標題/清單)、長段落；`SEARCH_PAGE_CHARS` 預設 2000；指定學期時只列出該學期資料
- **搜尋後讀取網頁內文**：讀取前 2 筆結果網頁，依問題關鍵字摘錄相關段落給模型，回答更完整 (`SEARCH_FETCH_PAGES`、`SEARCH_PAGE_CHARS`)
- **新增 ddgs 多引擎搜尋**並設為預設備援 (`SEARCH_FALLBACK_ENGINE=ddgs`)，取代只有新聞的 Google News
- **修復查詢特定人物/單位時不搜尋而編造**：router 與工具規則加入「特定對象的具體資料」「使用者要求查詢」
- **修復 router 模式拒答**：回答階段 system prompt 不再描述無法使用的 `search_web`
- **改善心算**：要求逐步列出計算過程 (仍不穩定，見 ISSUE-020)
- **DuckDuckGo 被封鎖時自動備援**：偵測機器人驗證頁 (HTTP 202 / anomaly) 後冷卻 10 分鐘，主引擎無結果時改用 `SEARCH_FALLBACK_ENGINE` (預設 `google_news`)；`format_results` 依結果來源引擎選擇格式
- **新增端對端輸出測試** `test/e2e_bot.py`：真實 Ollama + 搜尋跑完整流程，檢查搜尋判斷、HTML 合法性、禁用字樣，報告寫入 `logs/e2e_report.md`
- **修復 OllamaClient 換 event loop 失效**：偵測 loop 變更時重建 httpx 連線池
- **修復 pytest 找不到測試**：`testpaths` 改為 `test`，加入 `pythonpath = ["."]`；移除測試中寫死的 `sys.path`

### 變更
- 移除未使用依賴 `pydantic`、`pydantic-settings`、`lxml` (`uv remove`)
- ruff 設定移至 `[tool.ruff.lint]`
- 測試文件改用 `uv run` 指令
- 文件更正：`.env` 修改皆需重啟生效 (原誤寫「即時生效」)

---

## 版本規劃

### [1.1.0] - 規劃中
- [ ] Webhook 模式支援 (目前僅 polling)
- [ ] 多模型動態切換指令 (/model <name>)
- [ ] 串流式回覆 (streaming)
- [ ] Docker 部署支援

### [1.2.0] - 規劃中
- [ ] RAG 向量檢索 (本地文件問答)
- [ ] 圖片/檔案處理支援
- [ ] 管理員儀表板 (Web UI)