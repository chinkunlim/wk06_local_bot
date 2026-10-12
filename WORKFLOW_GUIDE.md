# WORKFLOW_GUIDE - 開發流程指南 (SOP)

本文件定義專案的標準作業程序，確保開發、測試、部署的一致性。

---

## 🌳 Git 分支策略 (GitHub Flow 簡化版)

```
main (生產就緒)
  │
  ├── feature/xxx  (新功能)
  ├── fix/xxx      (Bug 修復)
  ├── docs/xxx     (文件更新)
  └── refactor/xxx (重構)
```

### 規則
1. **main 分支受保護** - 僅允許 PR 合併，需通過 CI
2. **功能分支命名** - `type/short-description` (如 `feature/webhook-support`)
3. **提交訊息** - 遵循 [Conventional Commits](https://www.conventionalcommits.org/)
   ```
   feat: 新增 Webhook 模式支援
   fix: 修正 DuckDuckGo 解析失敗
   docs: 更新 README 部署說明
   refactor: 重構工具循環邏輯
   chore: 更新依賴套件
   ```
4. **PR 模板** - 必填：動機、變更說明、測試方式、相關 Issue

---

## 🛠️ 本地開發環境設置

### 1. 初始化 (僅首次)
```bash
git clone <repo-url>
cd wk06_bot_local

# 安裝 uv (若未安裝)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 建立環境並安裝依賴
uv sync

# 複製環境變數範本
cp .env.example .env
# 編輯 .env 填入 TELEGRAM_BOT_TOKEN、ALLOWED_USER_IDS

# 啟動 Ollama 並拉取模型
ollama serve &
ollama pull qwen2.5  # 或 llama3.1

# 執行環境檢查
uv run python check_env.py
```

### 2. 日常開發
```bash
# 同步最新依賴
uv sync

# 執行 Bot (開發模式，含自動重載)
uv run python -m bot.main

# 程式碼檢查
uv run ruff check .
uv run ruff check . --fix

# 執行測試
uv run pytest -v
```

---

## 🧪 測試策略

### 測試金字塔
```
       ┌─────────────┐
       │  E2E 測試   │  少量：完整流程 (Bot 啟動 → 發送訊息 → 收到回覆)
       ├─────────────┤
       │ 整合測試    │  中量：搜尋+模型、配額+對話、工具循環
       ├─────────────┤
       │ 單元測試    │  大量：關鍵字提取、JSON 解析、配額計算、日期邏輯
       └─────────────┘
```

### 執行指令
```bash
# 全部測試
uv run pytest

# 單元測試 (快速)
uv run pytest tests/unit -v

# 整合測試 (需 Ollama 運行)
uv run pytest tests/integration -v

# 覆蓋率
uv run pytest --cov=bot --cov=llm --cov=search --cov=config
```

### 測試命名
- 檔案: `test_<module>.py`
- 函式: `test_<function>_<scenario>_<expected>`
  ```python
  def test_extract_keywords_chinese_stopwords_removed():
  def test_quota_exceeded_returns_false():
  def test_tool_loop_max_rounds_respected():
  ```

---

## 📦 依賴管理

### 新增套件
```bash
# 生產依賴
uv add httpx

# 開發依賴
uv add --dev pytest-mock

# 指定版本
uv add "pydantic>=2.9,<3.0"
```

### 更新套件
```bash
# 檢查可更新
uv pip list --outdated

# 更新全部 (會更新 uv.lock)
uv sync --upgrade

# 更新單一套件
uv add httpx@latest
```

### 鎖定檔
- `uv.lock` **必須納入版控** - 確保所有環境版本一致
- PR 審查時檢查 `uv.lock` 變更合理性

---

## 🚀 發布流程

### 版本號規範 (SemVer)
- **MAJOR**: 不相容 API 變更
- **MINOR**: 向下相容新功能
- **PATCH**: 向下相容 Bug 修復

### 發布步驟
```bash
# 1. 更新版本號 (pyproject.toml)
# 2. 更新 CHANGELOG.md
# 3. 提交
git commit -am "chore: release v1.1.0"

# 4. 打標籤
git tag -a v1.1.0 -m "Release v1.1.0"

# 5. 推送
git push origin main --tags

# 6. GitHub Actions 自動建構 Docker image / 發布 Release
```

---

## 🐳 部署指南

### 本地開發機 (現在)
```bash
uv run python -m bot.main
```

### 生產環境 (Systemd 服務)
```ini
# /etc/systemd/system/telegram-bot.service
[Unit]
Description=Local Telegram AI Bot
After=network.target ollama.service
Requires=ollama.service

[Service]
Type=simple
User=botuser
WorkingDirectory=/opt/telegram-bot
Environment=PATH=/opt/telegram-bot/.venv/bin
ExecStart=/opt/telegram-bot/.venv/bin/python -m bot.main
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now telegram-bot
sudo journalctl -u telegram-bot -f
```

### Docker 部署 (規劃中)
```yaml
# docker-compose.yml
services:
  ollama:
    image: ollama/ollama:latest
    volumes:
      - ollama_data:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  bot:
    build: .
    depends_on:
      - ollama
    environment:
      - OLLAMA_BASE_URL=http://ollama:11434
    env_file: .env
    restart: unless-stopped

volumes:
  ollama_data:
```

---

## 🔧 除錯技巧

### 1. 查看即時日誌
```bash
# 系統日誌
tail -f logs/bot.log

# 互動日誌 (JSONL 格式)
tail -f data/logs/interactions_$(date +%F).jsonl | jq
```

### 2. 除錯模式
```bash
# 設定 DEBUG 等級
LOG_LEVEL=DEBUG uv run python -m bot.main

# 或在程式碼加入 breakpoint()
import pdb; pdb.set_trace()
```

### 3. 測試搜尋獨立運作
```bash
uv run python -c "
from search import search
import asyncio
r = asyncio.run(search('台灣 亞運 金牌'))
print(r)
"
```

### 4. 測試模型獨立運作
```bash
uv run python -c "
from llm.ollama_client import get_ollama_client
import asyncio
c = get_ollama_client()
models = asyncio.run(c.list_models())
print([m['name'] for m in models])
"
```

### 5. 檢查配額狀態
```bash
cat data/quota/quota.json | jq
```

### 6. 測試搜尋模組
```bash
# 測試 DuckDuckGo 搜尋
uv run python -c "
from search import search
import asyncio
r = asyncio.run(search('台灣 天氣', max_results=3))
print(f'結果: {len(r)} 筆')
for r in r:
    print(f'  - {r[\"title\"][:60]}')
"

# 測試 Google News 搜尋
uv run python -c "
from search import search
import asyncio
r = asyncio.run(search('台灣 天氣', max_results=3, engine='google_news'))
print(f'結果: {len(r)} 筆')
"

# 測試搜尋同步版本
uv run python -c "
from search import search_sync
r = search_sync('台灣 天氣', max_results=3)
print(f'同步搜尋: {len(r)} 筆')
"
```

### 7. 測試模型工具呼叫
```bash
uv run python -c "
from llm.ollama_client import get_ollama_client, SEARCH_TOOL
import asyncio

async def test():
    c = get_ollama_client()
    resp = await c.chat_with_tools(
        messages=[{'role': 'user', 'content': '台灣今天天氣如何？'}],
        tools=[SEARCH_TOOL],
        tool_choice='auto'
    )
    print('回應:', resp)

asyncio.run(test())
"
```

### 8. 測試 Markdown 解析器
```bash
uv run python -c "
from bot.handler import markdown_to_html

# 測試粗體
print(markdown_to_html('**粗體**'))

# 測試斜體
print(markdown_to_html('*斜體*'))

# 測試程式碼
print(markdown_to_html('\`行內程式碼\`'))

# 測試程式碼區塊
print(markdown_to_html('\`\`\`python\nprint(\"hello\")\n\`\`\`'))

# 測試連結
print(markdown_to_html('[連結](https://example.com)'))

# 測試混合
print(markdown_to_html('**粗體** 和 *斜體*'))
"
```

### 9. 清理 Telegram 衝突
```bash
# 強制停止所有 bot 實例並清理
pkill -f "bot.main" && pkill -f "uv run"

# 清理 Telegram pending updates
uv run python -c "
import httpx, asyncio
from config.settings import settings
async def clear():
    url = f'https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/deleteWebhook'
    async with httpx.AsyncClient() as c:
        await c.post(url, params={'drop_pending_updates': True})
    url2 = f'https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/getUpdates'
    async with httpx.AsyncClient() as c:
        await c.get(url2, params={'offset': -1})
asyncio.run(clear())
"
```

### 10. 常見問題快速診斷
| 症狀 | 可能原因 | 解決方案 |
|------|----------|----------|
| `Conflict: terminated by other getUpdates request` | 多實例運行或殘留 pending updates | 執行 `pkill -f "bot.main"` 並清理 webhook |
| DuckDuckGo 搜尋 0 結果 | Brotli 解壓失敗或選擇器重複 | 更新 `search/duckduckgo.py` (移除 br, 簡化 selector) |
| Google News 語法錯誤 | 智慧引號語法錯誤 | 更新 `search/google_news.py` 的 `decode_xml_entities` |
| Markdown 顯示異常 (粗體/程式碼異常) | 解析器衝突 | 更新 `bot/handler.py` 的 `markdown_to_html` |
| `RuntimeError: This event loop is already running` | event loop 衝突 | 更新 `search/__init__.py` 的 `search_sync` 使用 ThreadPoolExecutor |
| 搜尋同步版本卡住 | event loop 衝突 | 更新 `search/__init__.py` 使用 ThreadPoolExecutor |

---

## 📝 程式碼風格規範

## 📝 程式碼風格規範

### Ruff 設定 (已在 pyproject.toml)
- 行長: 100 字元
- 目標: Python 3.10+
- 檢查: E, F, I, UP, W

### 命名慣例
| 類型 | 慣例 | 範例 |
|------|------|------|
| 模組/檔案 | snake_case | `ollama_client.py` |
| 類別 | PascalCase | `OllamaClient` |
| 函式/變數 | snake_case | `search_web`, `max_turns` |
| 常數 | UPPER_SNAKE | `SEARCH_TOOL`, `MAX_HISTORY_TURNS` |
| 私有 | `_prefix` | `_execute_search` |

### 類型標註
- **公開函式必須** 有型別標註
- 使用 `from __future__ import annotations` (Python 3.11+ 預設)
- 複雜型別用 `typing` 或 Python 3.9+ 內建語法

```python
# 好
async def search(query: str, max_results: int = 4) -> list[dict]:
    ...

# 避免
async def search(query, max_results=4):
    ...
```

### 文件字串
```python
def search_duckduckgo(query: str, max_results: int = 4) -> List[Dict]:
    """
    使用 DuckDuckGo HTML 版搜尋。

    Args:
        query: 搜尋關鍵字
        max_results: 最大結果數

    Returns:
        列表，每項包含 title, url, snippet

    Raises:
        httpx.TimeoutException: 請求逾時
    """
```

---

## 🔐 安全性檢查清單

### 開發前
- [ ] `.env` 不納入版控 (已在 `.gitignore`)
- [ ] 無硬編碼 Token/Key/API 憑證
- [ ] 依賴掃描: `uv run pip-audit` (需安裝)

### 程式碼審查
- [ ] 輸入驗證 (用戶訊息、指令參數)
- [ ] SQL/命令注入防護 (本專案無 DB/Shell，低風險)
- [ ] 路徑遍歷防護 (檔案讀寫用 `pathlib` 安全路徑)
- [ ] 錯誤訊息不洩露堆疊/內部路徑

### 部署前
- [ ] 生產 `.env` 權限 `600`
- [ ] 非 root 用戶運行
- [ ] 防火牆僅開必要埠
- [ ] 定期更新基礎映像/系統套件

---

## 📊 監控與告警 (生產環境建議)

| 指標 | 方式 | 告警閾值 |
|------|------|----------|
| Bot 存活 | systemd watchdog / healthcheck endpoint | 連續 3 次失敗 |
| 回應延遲 | 日誌解析 `chat_with_tools` 耗時 | P99 > 30s |
| 錯誤率 | 日誌 `ERROR` 計數 | > 5%/min |
| 佇列積壓 | `pending_update_count` (Webhook) | > 100 |
| 磁碟空間 | `df -h /opt/telegram-bot` | > 80% |
| Ollama 狀態 | `GET /api/tags` 回應 | 非 200 |

---

## 📚 參考資源

- [uv 官方文件](https://docs.astral.sh/uv/)
- [Ollama API 文件](https://github.com/ollama/ollama/blob/main/docs/api.md)
- [python-telegram-bot 文件](https://docs.python-telegram-bot.org/)
- [Conventional Commits](https://www.conventionalcommits.org/)
- [Semantic Versioning](https://semver.org/)