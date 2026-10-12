# DECISIONS - 架構決策記錄 (ADR)

本專案採用 [Architecture Decision Records](https://adr.github.io/) 記錄重要技術決策。

---

## ADR-001: 採用本地 Ollama 替代 Gemini API

**日期**: 2026-10-12
**狀態**: Accepted

### 背景
原專案使用 Google Gemini API (免費額度)，但免費版無 Grounding/Search 功能，且有 RPM/日額度限制。

### 決策
改用 **Ollama** 在本地運行開源模型 (qwen2.5, llama3.1, nemotron3-ultra 等)。

### 理由
- ✅ 完全免費、無請求限制、無 Token 成本
- ✅ 資料不出本機，隱私性最佳
- ✅ 支援 Function Calling (llama3.1+, nemotron3-ultra, command-r)
- ✅ 可離線運行，適合內網/敏感環境
- ❌ 需自備算力 (CPU/GPU/RAM)
- ❌ 模型能力不如最新商業模型

### 替代方案評估
| 方案 | 優點 | 缺點 | 結果 |
|------|------|------|------|
| Gemini API (付費) | 能力強、有 Grounding | 成本不可控、資料上傳 | ❌ |
| OpenRouter / Together.ai | 免費額度、多模型 | 仍有速率限制、資料上傳 | ❌ |
| **Ollama 本地** | **無限制、隱私、離線** | **需硬體資源** | ✅ |

---

## ADR-002: 採用 Function Calling 而非關鍵字觸發搜尋

**日期**: 2026-10-12
**狀態**: Accepted

### 背景
原 GAS 版本用 `shouldTriggerSearch()` 關鍵字判斷是否搜尋，準確度有限。

### 決策
使用模型原生 **Function Calling (Tool Use)**，讓模型自主決定：
1. 是否需要搜尋
2. 搜尋什麼關鍵字
3. 根據結果如何整理回答

### 理由
- ✅ 語義理解優於關鍵字匹配
- ✅ 模型可多輪搜尋 (搜尋 → 發現不足 → 再搜)
- ✅ 關鍵字提取更精準 (模型理解核心實體)
- ✅ 可擴展其他工具 (計算機、程式碼執行、RAG 等)

### 實作細節
- `llm/ollama_client.py` 定義 `SEARCH_TOOL` JSON Schema
- `bot/handler.py` 實作工具呼叫循環 (最多 3 輪)
- 搜尋結果以 `role: tool` 回傳給模型

---

## ADR-003: 雙搜尋引擎架構 (DuckDuckGo + Google News RSS)

**日期**: 2026-10-12
**狀態**: Accepted

### 決策
提供兩種搜尋引擎，透過 `SEARCH_ENGINE` 環境變數切換：
- `duckduckgo` (預設)：通用網頁搜尋、免費、無 API Key
- `google_news`：新聞專用、穩定、繁體中文支援好

### 理由
- DuckDuckGo HTML 抓取：通用性強，但易被反爬蟲、結構易變
- Google News RSS：標準格式、穩定、適合即時新聞
- 統一介面 `search/__init__.py` 工廠模式，易擴展第三方

---

## ADR-004: 本地 JSON 持久化替代 Google Sheets/CacheService

**日期**: 2026-10-12
**狀態**: Accepted

### 決策
所有狀態存在本地檔案：
- `data/cache/history/{user_id}.json` - 對話歷史
- `data/quota/quota.json` - 每日配額
- `data/logs/interactions_YYYY-MM-DD.jsonl` - 互動日誌

### 理由
- ✅ 無外部依賴，部署簡單
- ✅ 檔案可直接備份/遷移/查看
- ✅ 執行緒鎖 (`threading.Lock`) 保證並發安全
- ❌ 不適合多實例水平擴展 (單機架構接受)

### 替代方案
| 方案 | 適用場景 | 本專案決策 |
|------|----------|------------|
| SQLite | 需查詢/索引 | 目前資料量小，JSON 足夠 |
| Redis | 高併發、分散式 | 單機 Bot 不需要 |
| **本地 JSON** | **單機、資料量小、簡單** | ✅ 採用 |

---

## ADR-005: 採用 uv 管理 Python 環境

**日期**: 2026-10-12
**狀態**: Accepted

### 決策
使用 `uv` (Rust 寫的 Python 套件管理器) 取代 pip/venv/poetry。

### 理由
- ✅ 解析速度極快 (10-100x pip)
- ✅ 單一工具替代 `pip + venv + pip-tools + poetry`
- ✅ `uv.lock` 確保可重現建置
- ✅ 自動管理 Python 版本 (`uv venv --python 3.11`)
- ✅ `uv run` 無需手動激活虛擬環境

---

## ADR-006: 採用 Long Polling 而非 Webhook

**日期**: 2026-10-12
**狀態**: Accepted

### 決策
啟動時呼叫 `delete_webhook(drop_pending_updates=True)`，使用 `start_polling()`。

### 理由
- ✅ 本地開發/測試無需公網 IP/域名/SSL
- ✅ 無需設定反向代理 (nginx) + HTTPS 憑證
- ✅ 適合個人/小規模使用
- ❌ 效率略低於 Webhook (持續連線 vs 被動推送)
- ❌ 不適合高流量生產環境

### 未來擴展
若需生產部署，可加入 Webhook 模式：
- `WEBHOOK_URL` 環境變數
- `aiohttp` 建立 HTTPS 端點
- 配合 nginx + Let's Encrypt

---

## ADR-007: 模型選擇 qwen2.5 作為預設

**日期**: 2026-10-12
**狀態**: Accepted

### 決策
預設模型設為 `qwen2.5` (而非 llama3.1)。

### 理由
- 用戶環境已預裝 `qwen2.5:latest` (4.4 GB)
- qwen2.5 支援 Function Calling (Ollama 0.5+)
- 中文能力強、指令遵循好
- 體積較小 (llama3.1:8b 約 4.7 GB，qwen2.5:7b 約 4.4 GB)

### 建議升級路徑
```bash
# 工具呼叫能力最強
ollama pull nemotron3-ultra      # 48GB VRAM 需求高
ollama pull llama3.1             # 平衡選擇
ollama pull command-r            # 專為 RAG/工具設計
```
修改 `.env` → `OLLAMA_MODEL=llama3.1` 即可切換。

---

## ADR-008: 不使用 LangChain/LlamaIndex 等框架

**日期**: 2026-10-12
**狀態**: Accepted

### 決策
直接呼叫 Ollama REST API，不引入 LangChain/LlamaIndex。

### 理由
- ✅ 依賴極少 (僅 httpx, pydantic)
- ✅ 完全掌控提示詞、工具循環、錯誤處理
- ✅ 避免框架抽象層帶來的除錯困難
- ✅ 專案規模小，框架帶來的效益有限
- ❌ 手動實作 RAG/記憶/評估需自行開發

### 適用場景
| 專案規模 | 建議 |
|----------|------|
| 單一 Bot、簡單工具鏈 | **直接呼叫 API** ✅ |
| 複雜 RAG、多 Agent、需評估 | LangChain/LlamaIndex |

---

## ADR-009: 修復 Telegram Long Polling 衝突問題

**日期**: 2026-10-12
**狀態**: Accepted

### 背景
啟動 bot 時出現 `Conflict: terminated by other getUpdates request` 錯誤，導致無法正常輪詢。

### 決策
實作三層防護機制：
1. 啟動時呼叫 `deleteWebhook(drop_pending_updates=True)` 清理殘留更新
2. 確保單一實例運行 (`pkill -f "bot.main"`)
3. 使用 `drop_pending_updates=False` 避免重複清理

### 理由
- 避免多實例同時輪詢導致 Telegram 伺服器終止連線
- 確保啟動前環境乾淨，無殘留 pending updates

---

## ADR-010: 修復 DuckDuckGo 搜尋回傳 0 結果

**日期**: 2026-10-12
**狀態**: Accepted

### 背景
DuckDuckGo HTML 搜尋回傳 0 筆結果，雖然直接測試有結果但模組內部回傳 0。

### 決策
雙重修復：
1. 移除 `Accept-Encoding: br` (Brotli)，改用 `gzip, deflate` 避免解壓失敗
2. 簡化 CSS 選擇器從 `.result__body, .web-result, .result` 改為 `.result__body`，避免重複選取導致去重邏輯失效

### 理由
- Brotli 壓縮在某些環境下無法正確解壓，導致 HTML 解析失敗
- 多重選擇器導致重複元素，去重邏輯異常導致結果被過濾

---

## ADR-011: 修復 Google News XML 實體解碼錯誤

**日期**: 2026-10-12
**狀態**: Accepted

### 背景
`decode_xml_entities` 函數中的智慧引號字元導致 Python 語法錯誤。

### 決策
重寫 `decode_xml_entities` 使用 Unicode escape sequences (`\u2018`, `\u2019`, `\u201c`, `\u201d`) 替代字面字元。

### 理由
- 智慧引號在 Python 字串字面值中會導致語法錯誤
- Unicode escape sequences 更安全、可移植

---

## ADR-012: 修復 Markdown 解析器衝突

**日期**: 2026-10-12
**狀態**: Accepted

### 背景
Markdown 解析器中 inline code (`code`) 被斜體規則誤處理，導致 `__INLINE<i>CODE</i>0__` 等異常輸出。

### 決策
重寫 `markdown_to_html` 採用 **placeholder 保護策略**：
1. 階段 0: 保護所有特殊標記 (程式碼區塊、行內程式碼、HTML 標籤) 為 placeholder
2. 階段 1: HTML 跳脫
3. 階段 2: 處理 Markdown 語法 (粗體、斜體、標題、列表、連結)
4. 階段 3: 還原受保護內容並轉換為 HTML

### 理由
- 保護優先策略確保特殊內容不被後續規則誤處理
- 統一保護/還原機制簡化邏輯，避免正則表達式衝突

---

## ADR-013: 修復 `search_sync` event loop 衝突

**日期**: 2026-10-12
**狀態**: Accepted

### 背景
`search_sync` 在已有 event loop 執行時拋出 `RuntimeError: This event loop is already running`。

### 決策
使用 `ThreadPoolExecutor` 隔離執行：
- Python 3.12+ 使用 `asyncio.get_running_loop()` 檢測
- Python 3.11 及以下使用 `asyncio.get_event_loop()` + `is_running()` 檢測
- 已在 loop 中時，提交到執行緒池執行 `asyncio.run()`

### 理由
- 避免在已有 event loop 中巢狀呼叫 `asyncio.run()`
- 執行緒池隔離確保事件循環獨立

---

## 更新決策記錄

新增 ADR 格式：
```markdown
## ADR-XXX: 標題

**日期**: YYYY-MM-DD
**狀態**: Proposed | Accepted | Deprecated | Superseded

### 背景
...

### 決策
...

### 理由
...

### 後果
...
```