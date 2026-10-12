# 🤖 本地 AI Telegram Bot

完全在本地運行的 Telegram Bot，使用 **Ollama** 運行開源模型，支援 **Function Calling (工具呼叫)** 自動搜尋網路資訊。

## ✨ 特色

- 🏠 **100% 本地運行** - 無需雲端 API Key，資料不出本機
- 🦙 **Ollama 整合** - 一行指令啟動模型，支援 llama3.1/3.2、Nemotron 3 Ultra、Command-R 等
- 🔧 **Function Calling** - 模型自主決定何時搜尋、搜什麼關鍵字、如何整理回答
- 🔍 **雙搜尋引擎** - DuckDuckGo HTML (通用) / Google News RSS (新聞)
- 🛡️ **白名單 + 配額** - 防止濫用，每日請求上限可調
- 💾 **本地持久化** - 對話歷史、配額、日誌皆存 JSON 檔案
- ⚡ **漸進式回覆** - 思考中 → 搜尋中 → 整理中 → 完成
- 📦 **uv 專案管理** - 極速依賴解析、Python 版本自動管理、單一鎖定檔
- 🧪 **完整測試套件** - 內建搜尋、Markdown、Ollama、對話、設定等單元測試
- 🐛 **完善除錯日誌** - 內建 DEBUG 等級日誌追蹤 handler 註冊、polling、訊息處理流程

## 🚀 快速開始

### 1. 安裝 Ollama 並拉取模型

```bash
# 安裝 Ollama (Mac/Windows/Linux)
curl -fsSL https://ollama.com/install.sh | sh

# 啟動 Ollama 服務
ollama serve

# 拉取支援 Function Calling 的模型 (任選一)
ollama pull llama3.1        # 推薦：Meta 官方，支援工具呼叫
ollama pull llama3.2        # 較新版本
ollama pull nemotron3-ultra # NVIDIA，工具呼叫能力強
ollama pull command-r       # Cohere，專為 RAG 設計
ollama pull qwen2.5         # 阿里巴巴，中文強、體積小
```

### 2. 建立 Python 環境 (使用 uv)

```bash
cd wk06_bot_local

# 安裝 uv (若未安裝)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 同步依賴 (自動建立 .venv、安裝套件、鎖定版本)
uv sync

# 或手動建立環境指定 Python 版本
uv venv --python 3.11
uv sync
```

### 3. 設定環境變數

```bash
# 複製範本
cp .env.example .env

# 編輯 .env 填入您的資訊
# 必填：TELEGRAM_BOT_TOKEN, ALLOWED_USER_IDS
# 選填：OLLAMA_MODEL, SEARCH_ENGINE 等
```

### 4. 取得 Telegram Bot Token 與 User ID

1. 找 `@BotFather` → `/newbot` → 取得 Token
2. 找 `@userinfobot` → 取得您的 User ID (數字)
3. 填入 `.env`：
   ```env
   TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRstuvwx
   ALLOWED_USER_IDS=123456789,987654321
   ```

### 5. 環境檢查與啟動

```bash
# 一鍵檢查環境 (Python、依賴、Ollama、模型、權限)
uv run python check_env.py

# 啟動 Bot
uv run python -m bot.main
```

看到 `✅ Bot 已啟動，開始輪詢訊息...` 即代表成功！

## 💬 使用指令

| 指令 | 說明 |
|------|------|
| `/start` | 歡迎訊息與功能介紹 |
| `/help` | 完整使用說明 |
| `/search <關鍵字>` | 主動搜尋並由 AI 總結 |
| `/news` | 瀏覽最新新聞頭條 |
| `/status` | 查看今日剩餘額度 |
| `/reset` | 清除對話記憶 |
| `/models` | 列出本地可用模型 |

## 🏗️ 專案架構

```
wk06_bot_local/
├── .env.example              # 環境變數範本
├── .env                      # 您的機密設定 (不納入版控)
├── pyproject.toml            # 專案設定、依賴、工具配置
├── uv.lock                   # 精確依賴鎖定檔 (納入版控)
├── requirements.txt          # pip 相容依賴清單
├── check_env.py              # 環境檢查腳本
├── README.md                 # 本文件
├── CHANGELOG.md              # 版本變更記錄
├── DECISIONS.md              # 架構決策記錄 (ADR)
├── KNOWN_ISSUES.md           # 已知問題與規避方案
├── WORKFLOW_GUIDE.md         # 開發流程、部署、測試策略
├── AGENTS.md                 # AI Agent 開發指南
├── config/
│   ├── __init__.py
│   └── settings.py           # 設定管理 (從 .env 讀取)
├── bot/
│   ├── __init__.py
│   ├── main.py               # 程式入口
│   ├── handler.py            # Telegram 處理器 (指令、訊息、工具循環)
│   └── conversation.py       # 對話歷史、配額、授權、日誌
├── llm/
│   ├── __init__.py
│   └── ollama_client.py      # Ollama API 客戶端 (支援 Function Calling)
├── search/
│   ├── __init__.py           # 搜尋引擎工廠
│   ├── duckduckgo.py         # DuckDuckGo HTML 搜尋
│   └── google_news.py        # Google News RSS 搜尋
├── test/                     # 測試套件
│   ├── __init__.py
│   ├── run_all.py            # 統一測試執行器
│   ├── test_settings.py      # 設定測試
│   ├── test_search.py        # 搜尋測試
│   ├── test_markdown.py      # Markdown 解析測試
│   ├── test_ollama.py        # Ollama 測試
│   ├── test_conversation.py  # 對話/配額測試
│   ├── test_settings.py      # 設定測試
│   └── README.md             # 測試說明
├── data/                     # 執行時自動建立
│   ├── cache/history/        # 對話歷史 (JSON)
│   ├── quota/                # 配額記錄 (JSON)
│   └── logs/                 # 互動日誌 (JSONL)
└── logs/                     # 系統日誌
```

## 🔧 進階設定

### 切換模型
修改 `.env`：
```env
OLLAMA_MODEL=nemotron3-ultra
```
重啟 Bot 即可。需先 `ollama pull nemotron3-ultra`。

### 切換搜尋引擎
```env
# 通用網頁搜尋 (預設)
SEARCH_ENGINE=duckduckgo

# 新聞專用 (Google News RSS，穩定、繁體中文好)
SEARCH_ENGINE=google_news
```

### 調整配額
```env
MAX_DAILY_REQUESTS=100
```

### 調整對話輪數
```env
MAX_HISTORY_TURNS=6
```

## 🛠️ 開發指南

### 常用 uv 指令
```bash
# 同步依賴
uv sync

# 新增套件
uv add httpx
uv add --dev pytest

# 移除套件
uv remove httpx

# 程式碼檢查
uv run ruff check .
uv run ruff check . --fix

# 執行測試
uv run pytest -v

# 執行腳本
uv run python check_env.py
uv run python -m bot.main
```

### 新增搜尋引擎
1. 在 `search/` 建立新模組 (如 `search/brave.py`)
2. 實作 `async def search_xxx(query, max_results)` 回傳 `List[Dict]`
3. 實作 `format_results(results)` 回傳格式化文字
4. 在 `search/__init__.py` 的 `SEARCH_ENGINES` 註冊

### 自訂工具
在 `llm/ollama_client.py` 的 `SEARCH_TOOL` 陣列新增工具定義，並在 `handler.py` 的工具循環中處理。

### 文件說明
| 文件 | 用途 |
|------|------|
| `CHANGELOG.md` | 版本變更記錄 |
| `DECISIONS.md` | 架構決策記錄 (ADR-001 ~ ADR-008) |
| `KNOWN_ISSUES.md` | 已知問題、優先級、規避方案、追蹤表 |
| `WORKFLOW_GUIDE.md` | 開發流程、Git 策略、測試、部署、除錯 |
| `AGENTS.md` | AI Agent 協作規範、模組職責、擴充指南 |

## 🐛 常見問題

### Q: 模型不支援 Function Calling 怎麼辦？
A: 請使用支援工具呼叫的模型：`llama3.1`、`llama3.2`、`nemotron3-ultra`、`command-r`、`command-r-plus`、`qwen2.5`。舊版 `llama3`、`mistral`、`gemma` (舊版) 等不支援。

### Q: 搜尋結果不準確？
A: 
- 嘗試切換 `SEARCH_ENGINE=google_news` (適合新聞)
- 確認模型正確提取關鍵字 (查看日誌 `🔧 模型呼叫搜尋: "..."`)
- 增加 `SEARCH_MAX_RESULTS`
- 使用能力更強的模型 (`llama3.1`、`nemotron3-ultra`)

### Q: 回覆很慢？
A: 
- 確認使用 GPU 加速：`OLLAMA_BASE_URL=http://localhost:11434` (預設會自動偵測 GPU)
- 使用較小模型：`llama3.2:3b`、`qwen2.5:3b`、`gemma2:2b`
- 調整 `OLLAMA_TIMEOUT`

### Q: 如何查看日誌？
```bash
# 系統日誌
tail -f logs/bot.log

# 互動日誌 (JSONL 格式)
cat data/logs/interactions_$(date +%F).jsonl | jq

# 配狀態
cat data/quota/quota.json | jq
```

### Q: qwen2.5 工具呼叫不穩定？
A: 這是已知問題 (ISSUE-001)。建議切換到 `llama3.1` 或 `nemotron3-ultra`：
```bash
ollama pull llama3.1
# .env: OLLAMA_MODEL=llama3.1
```

### Q: Telegram 出現 `Conflict: terminated by other getUpdates request` 錯誤？
A: 這是多實例衝突 (ISSUE-015)。解決方法：
```bash
# 1. 強制清理所有 bot 實例
pkill -f "bot.main" && pkill -f "uv run"

# 2. 清理 Telegram pending updates
uv run python -c "
import httpx, asyncio
from config.settings import settings
async def clear():
    url = f'https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/deleteWebhook'
    params = {'drop_pending_updates': True}
    async with httpx.AsyncClient() as client:
        await client.post(url, params=params)
    url2 = f'https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/getUpdates'
    async with httpx.AsyncClient() as client:
        await client.get(url2, params={'offset': -1})
asyncio.run(clear())
"
```

### Q: DuckDuckGo 搜尋回傳 0 結果？
A: 這是 ISSUE-016，已在 v1.0.2 修復。確保已更新 `search/duckduckgo.py`：
- 移除 `Accept-Encoding: br` (避免 Brotli 解壓失敗)
- 選擇器簡化為 `.result__body` (避免重複)

### Q: Google News 搜尋語法錯誤？
A: 這是 ISSUE-017，已在 v1.0.2 修復 `search/google_news.py` 的 `decode_xml_entities` 函數。

### Q: Markdown 粗體/斜體/程式碼顯示異常？
A: 這是 ISSUE-018，已在 v1.0.2 修復 `bot/handler.py` 的 `markdown_to_html` 函數。

### Q: `search_sync` 出現 `RuntimeError: This event loop is already running`？
A: 這是 ISSUE-019，已在 v1.0.2 修復 `search/__init__.py` 的 `search_sync` 函數，使用 `ThreadPoolExecutor` 隔離執行。