# Test Folder

所有測試腳本集中在這裡。

## 執行方式

```bash
# 執行所有測試
cd /Users/limchinkun/Desktop/wk06_bot_local
python test/run_all.py

# 執行特定測試
python test/run_all.py search
python test/run_all.py markdown
python test/run_all.py ollama
python test/run_all.py conversation
python test/run_all.py settings

# 直接執行單一測試檔案
python test/test_search.py
python test/test_markdown.py
python test/test_ollama.py
python test/test_conversation.py
python test/test_settings.py
```

## 測試項目

| 測試檔案 | 說明 | 類型 |
|----------|------|------|
| test_settings.py | 設定檔載入、驗證、目錄檢查 | 同步 |
| test_search.py | DuckDuckGo / Google News 搜尋、格式化 | 非同步 |
| test_markdown.py | Markdown 解析器 (粗體、斜體、程式碼、連結等) | 同步 |
| test_ollama.py | Ollama 連線、模型、對話、工具呼叫 | 非同步 |
| test_conversation.py | 對話歷史、配額、授權、日誌 | 同步 |

## 開發指南

新增測試時：
1. 在 `test/` 下建立 `test_xxx.py`
2. 在 `run_all.py` 的 `TESTS` 字典加入
3. 依類型決定同步/非同步執行

## 常用指令

```bash
# 執行前先確保環境
cd /Users/limchinkun/Desktop/wk06_bot_local
uv sync

# 執行特定測試
uv run python test/test_search.py
uv run python test/test_markdown.py

# 執行所有
uv run python test/run_all.py
```