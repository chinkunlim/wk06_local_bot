# Test Folder

所有測試腳本集中在這裡。

## 執行方式

```bash
# 用 pytest 執行全部 (testpaths = test)
uv run pytest -v

# 執行所有測試
cd wk06_bot_local
uv run python test/run_all.py

# 執行特定測試
uv run python test/run_all.py search
uv run python test/run_all.py markdown
uv run python test/run_all.py ollama
uv run python test/run_all.py conversation
uv run python test/run_all.py settings

# 直接執行單一測試檔案
uv run python test/test_search.py
uv run python test/test_markdown.py
uv run python test/test_ollama.py
uv run python test/test_conversation.py
uv run python test/test_settings.py
```

## 測試項目

| 測試檔案 | 說明 | 類型 |
|----------|------|------|
| test_settings.py | 設定檔載入、驗證、目錄檢查 | 同步 |
| test_search.py | DuckDuckGo / Google News 搜尋、格式化 | 非同步 |
| test_markdown.py | Markdown 解析器 (粗體、斜體、程式碼、連結等) | 同步 |
| test_ollama.py | Ollama 連線、模型、對話、工具呼叫 | 非同步 |
| test_conversation.py | 對話歷史、配額、授權、日誌 | 同步 |
| test_handler_utils.py | Markdown/分段/關鍵字/錯誤處理/router (離線，mock Ollama) | 非同步 |
| e2e_bot.py | **端對端輸出測試**：真實 Ollama + 搜尋跑完整流程，檢查是否該搜才搜、HTML 合法、禁用字樣 | 非同步 (非 pytest) |

## 端對端輸出測試 (e2e_bot.py)

不經 Telegram，直接跑 Bot 的真實流程並檢查回覆，不會寫入 `data/`：

```bash
# 內建 8 題 (是否搜尋、程式碼區塊、計算、翻譯、天氣追問、新聞)
uv run python test/e2e_bot.py

# 自訂問題 (依序執行並共用對話歷史，可測追問)
uv run python test/e2e_bot.py "台灣今天天氣如何？" "那台北明天呢？" --full

# 比較模型 / 搜尋判斷方式
uv run python test/e2e_bot.py --model gemma4 --decision tools
```

完整輸出 (送往 Telegram 的 HTML) 寫在 `logs/e2e_report.md`。需 Ollama 已啟動 (`open -a Ollama`)。

## 開發指南

新增測試時：
1. 在 `test/` 下建立 `test_xxx.py`
2. 在 `run_all.py` 的 `TESTS` 字典加入
3. 依類型決定同步/非同步執行

## 常用指令

```bash
# 執行前先確保環境
cd wk06_bot_local
uv sync

# 執行特定測試
uv run python test/test_search.py
uv run python test/test_markdown.py

# 執行所有
uv run python test/run_all.py
```