# AGENTS.md - 本地 AI Telegram Bot 開發指南

本文件為 AI Agents 與開發者提供本專案的架構規範、程式碼慣例與維護原則。

---

## 1. 專案願景與核心原則

- **100% 本地運行**：核心邏輯在本地 Python 執行，透過 Ollama 運行開源模型，無雲端 API 依賴。
- **零外部服務依賴**：
  - 模型：Ollama 本地服務 (HTTP API)
  - 搜尋：DuckDuckGo HTML / Google News RSS (公開網頁，無 API Key)
  - 儲存：本地 JSON 檔案系統
  - 通訊：Telegram Bot API (長輪詢)
- **隱私優先**：所有用戶資料、對話歷史、配額記錄皆存本機，不上傳任何第三方。
- **Function Calling 原生**：模型自主決定何時搜尋、搜尋什麼、如何整理，而非關鍵字硬編碼觸發。

---

## 2. 模組分工與職責劃分

| 模組路徑 | 職責定義 | 關鍵類別/函式 |
|----------|----------|---------------|
| `config/settings.py` | 環境變數載入、驗證、預設值管理 | `Settings` class, `settings` singleton |
| `bot/main.py` | 程式入口、Application 生命週期、啟動檢查 | `main()`, `setup_bot()` |
| `bot/handler.py` | Telegram 指令路由、訊息處理、工具呼叫循環 | `BotHandler` class, `cmd_*`, `handle_message`, `_process_query` |
| `bot/conversation.py` | 對話歷史、白名單、配額、日誌 (JSON 持久化) | `get_conversation_history`, `save_conversation_turn`, `check_and_consume_quota`, `log_interaction` |
| `llm/ollama_client.py` | Ollama REST API 封裝、Function Calling 支援 | `OllamaClient`, `chat_with_tools`, `chat_stream`, `SEARCH_TOOL` |
| `search/__init__.py` | 搜尋引擎工廠、統一介面 | `search()`, `format_results()`, `get_search_engine()` |
| `search/duckduckgo.py` | DuckDuckGo HTML 抓取與解析 | `search_duckduckgo()`, `extract_search_keywords()` |
| `search/google_news.py` | Google News RSS 抓取、相關性過濾 | `search_google_news()`, `filter_relevant_articles()` |

---

## 3. 程式碼編寫規範

### 3.1 Python 環境限制
1. **Python ≥ 3.10** (專案使用 3.11)，支援 `list[dict]`、`union` `|` 語法
2. **非同步優先**：所有 I/O (HTTP、檔案、Telegram) 使用 `async/await`
3. **型別標註**：公開函式**必須**有型別標註，內部建議加上
4. **依賴極小化**：核心依賴 < 10 個，避免重型框架

### 3.2 非同步模式規範
```python
# ✅ 正確：async 函式完整 await
async def search(query: str) -> list[dict]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
    return parse(resp.text)

# ❌ 錯誤：同步阻塞 event loop
def search(query: str) -> list[dict]:
    resp = httpx.get(url)  # 阻塞！
    return parse(resp.text)

# ✅ 同步介面需明確標註 (僅供非 async 呼叫)
def search_sync(query: str) -> list[dict]:  # 命名含 _sync
    return asyncio.run(search(query))
```

### 3.3 錯誤處理規範
- **外部 API 呼叫** (`httpx`)：必須設定 `timeout`、捕獲 `httpx.HTTPError`、`TimeoutException`
- **Telegram 發送**：捕獲 `telegram.error.TelegramError`，避免單一發送失敗阻塞主流程
- **工具循環**：單輪工具失敗記錄日誌並繼續，不中斷整個對話
- **使用者面向錯誤**：回覆友善訊息，堆疊只寫日誌

### 3.4 並發安全
- `bot/conversation.py` 使用 `threading.Lock` 保護檔案讀寫
- 單用戶鎖 `_get_history_lock(user_id)` 避免同用戶並發寫入歷史
- 全域配額鎖 `_quota_lock` 保護 `quota.json`

---

## 4. 核心流程詳解

### 4.1 訊息處理管線
```
Telegram Update
    │
    ▼
Application.dispatcher
    │
    ├── CommandHandler (/start, /search, /status...) → BotHandler.cmd_*
    │
    └── MessageHandler (TEXT) → BotHandler.handle_message
                                    │
                                    ▼
                            is_user_authorized() → 否 → 回覆拒絕
                                    │
                                    ▼
                            check_and_consume_quota() → 否 → 回覆額度用盡
                                    │
                                    ▼
                            _process_query() (核心邏輯)
                                    │
                                    ├── 取得對話歷史 get_conversation_history()
                                    ├── 建立 messages (build_system_prompt() 含今日日期 + history + user)
                                    ├── 搜尋判斷 (SEARCH_DECISION)
                                    │     ├── router (預設) _router_search()
                                    │     │     ├── ollama.decide_search() → JSON {need_search, query}
                                    │     │     └── 需要時 search() → messages.append(assistant tool_calls + role=tool)
                                    │     └── tools _tool_loop() (最多 3 輪)
                                    │           ├── ollama.chat_with_tools(messages, tools=[SEARCH_TOOL])
                                    │           ├── 解析 tool_calls → 執行 search() → role=tool
                                    │           └── 無 tool_calls 時直接取得回答
                                    │
                                    ├── 尚無回答時 ollama.chat_with_tools(messages, tools=None)
                                    ├── 組裝最終回覆 (含來源、額度)
                                    ├── send_final_response() (edit 或 send)
                                    ├── save_conversation_turn()
                                    └── log_interaction()
```

### 4.2 Function Calling 細節
```python
# 定義於 llm/ollama_client.py
SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search_web",
        "description": "搜尋網路即時資訊...",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜尋關鍵字..."}
            },
            "required": ["query"]
        }
    }
}
```

**模型回傳工具呼叫格式**：
```json
{
  "message": {
    "role": "assistant",
    "content": "",
    "tool_calls": [
      {
        "id": "call_abc123",
        "function": {"name": "search_web", "arguments": "{\"query\": \"台灣 亞運 金牌\"}"}
      }
    ]
  }
}
```

**處理邏輯**：`handler.py` → `_process_query()` → 迴圈解析 `tool_calls` → 呼叫 `search()` → 回傳 `role: tool`

---

## 5. 擴充指南

### 5.1 新增搜尋引擎
1. 在 `search/` 建立 `new_engine.py`
2. 實作：
   ```python
   async def search_new_engine(query: str, max_results: int) -> List[Dict]: ...
   def format_results(results: List[Dict]) -> str: ...
   ```
3. 在 `search/__init__.py` 的 `SEARCH_ENGINES` 註冊
4. `.env` 設定 `SEARCH_ENGINE=new_engine`

### 5.2 新增工具
1. 在 `llm/ollama_client.py` 的工具陣列新增定義
2. 在 `handler.py` 的工具循環 `if func_name == 'new_tool':` 處理
3. 回傳 `role: tool` 給模型

### 5.3 新增 Telegram 指令
1. 在 `handler.py` 新增 `async def cmd_xxx(self, update, context):`
2. 在 `setup_bot()` 註冊：`application.add_handler(CommandHandler('xxx', bot_handler.cmd_xxx))`
3. 更新 `README.md` 指令表、`cmd_help()` 說明

### 5.4 切換/新增模型
```bash
ollama pull llama3.1
# 修改 .env
OLLAMA_MODEL=llama3.1
# 重啟 Bot
```

---

## 6. 本地驗證流程

### 語法/類型檢查
```bash
uv run ruff check .
uv run python -m py_compile bot/**/*.py llm/**/*.py search/**/*.py config/**/*.py
```

### 功能測試
```bash
# 環境檢查
uv run python check_env.py

# 單元測試 (待補全)
uv run pytest test/ -v

# 手動測試指令
uv run python -c "
from search import search
import asyncio
print(asyncio.run(search('test')))
"
```

---

## 7. 常見修改場景

| 需求 | 修改檔案 | 備註 |
|------|----------|------|
| 改模型 | `.env` → `OLLAMA_MODEL` | 需 `ollama pull` |
| 改搜尋引擎 | `.env` → `SEARCH_ENGINE` | `duckduckgo` \| `google_news` |
| 改配額 | `.env` → `MAX_DAILY_REQUESTS` | 重啟生效 |
| 改對話輪數 | `.env` → `MAX_HISTORY_TURNS` | 重啟生效 |
| 改上下文長度 | `.env` → `OLLAMA_NUM_CTX` | 預設 8192，越大越吃記憶體 |
| 改 System Prompt | `llm/ollama_client.py` → `SYSTEM_PROMPT` | 影響所有回答風格 |
| 加白名單用戶 | `.env` → `ALLOWED_USER_IDS` | 逗號分隔，重啟生效 |
| 修改工具描述 | `llm/ollama_client.py` → `SEARCH_TOOL` | 影響模型呼叫意願 (僅 tools 模式) |
| 修改搜尋判斷規則 | `llm/ollama_client.py` → `ROUTER_PROMPT` | router 模式下決定何時搜尋 |
| 切換搜尋判斷方式 | `.env` → `SEARCH_DECISION` | `router` \| `tools`，重啟生效 |
| 修改搜尋關鍵字提取 | `search/duckduckgo.py` → `extract_search_keywords()` | 通用中文清洗邏輯 |

---

## 8. 除錯檢查清單

| 現象 | 排查步驟 |
|------|----------|
| Bot 無回應 | 1. `logs/bot.log` 檢查錯誤 2. `uv run python check_env.py` 3. 確認 Ollama 運行 `ollama ps` |
| 搜尋無結果 | 1. 日誌看 `🔧 模型呼叫搜尋` 關鍵字 2. 手動測試 `search_duckduckgo_sync()` 3. 切換 `SEARCH_ENGINE=google_news` |
| 模型不呼叫工具 / 每題都搜尋 | 1. 日誌看 `🧭 搜尋判斷` 2. 預設 `SEARCH_DECISION=router` 調整 `ROUTER_PROMPT` 3. tools 模式下 llama3.1 會每題都搜、qwen2.5 幾乎不搜，改用 router 或 gemma4 |
| 配額不重置 | 1. 檢查主機時區 `date` 2. `data/quota/quota.json` 手動刪除 3. 確認 `date.today()` 正確 |
| 記憶體暴增 | 1. 檢查 `MAX_HISTORY_TURNS` 2. 確認 `data/cache/history/` 檔案大小 3. 重啟 Bot 釋放 |
| `Conflict: terminated by other getUpdates request` | 1. `pkill -f "bot.main"` 停止所有實例 2. 執行 `deleteWebhook(drop_pending_updates=True)` 清理 pending updates |
| DuckDuckGo 搜尋 0 結果 | 1. 確認 `search/duckduckgo.py` 移除 `Accept-Encoding: br` 2. 確認選擇器簡化為 `.result__body` 3. 手動測試 `search_duckduckgo_sync()` |
| Google News 語法錯誤 | 1. 檢查 `search/google_news.py` 的 `decode_xml_entities` 是否使用 Unicode escape sequences |
| Markdown 顯示異常 (粗體/程式碼異常) | 1. 確認 `bot/handler.py` 的 `markdown_to_html` 使用 placeholder 保護策略 |
| `RuntimeError: This event loop is already running` | 1. 確認 `search/__init__.py` 的 `search_sync` 使用 `ThreadPoolExecutor` |
| 搜尋同步版本卡住 | 1. 確認 `search/__init__.py` 的 `search_sync` 使用 `ThreadPoolExecutor` 隔離執行 |

---

## 9. 版本控管規範

- **分支**：`main` (保護) ← PR ← `feature/*` `fix/*` `docs/*`
- **提交**：Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `chore:`)
- **PR**：需通過 `ruff check`、`pytest`、人工審查
- **發布**：語意化版本 + `CHANGELOG.md` + Git Tag

---

## 10. 參考文件

- `README.md` - 專案說明、快速開始、架構圖
- `CHANGELOG.md` - 版本變更記錄
- `DECISIONS.md` - 架構決策記錄 (ADR)
- `KNOWN_ISSUES.md` - 已知問題與規避
- `WORKFLOW_GUIDE.md` - 開發流程、部署、測試策略
- `pyproject.toml` - 專案設定、依賴、工具配置