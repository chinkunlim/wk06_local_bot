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