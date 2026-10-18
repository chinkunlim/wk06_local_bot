# KNOWN_ISSUES - 已知問題與規避方案

---

## 🔴 高優先級 (影響核心功能)

### ISSUE-001: qwen2.5 Function Calling 穩定性不足
**現象**: 模型有時不呼叫搜尋工具、或呼叫後無法正確解析結果、或產生幻覺工具呼叫。
**原因**: qwen2.5 的工具呼叫能力不如 llama3.1/nemotron3-ultra 成熟。
**規避**:
- 修改 `.env`: `OLLAMA_MODEL=llama3.1` 並執行 `ollama pull llama3.1` ✅ **已切換**
- 或 `OLLAMA_MODEL=nemotron3-ultra` (需大顯存)
- 在 System Prompt 加強工具使用指引
**狀態**: ✅ **已解決** (v1.0.1 切換至 llama3.1)
**補充 (v1.0.3)**: 實測原生 Function Calling 下 llama3.1 反而每題都搜尋、qwen2.5 幾乎不搜；改用 `SEARCH_DECISION=router` 後兩者皆能正確判斷 (見 ADR-014)。

### ISSUE-014: 配額檢查死鎖 (已修復)
**現象**: 發送訊息後無反應、終端機無日誌、配額檔案不建立。
**原因**: `check_and_consume_quota` 內部呼叫 `load_quota_data()` 兩者都試圖取得同一把 `_quota_lock` 造成死鎖。
**修復**: 移除 `load_quota_data` 和 `save_quota_data` 內部鎖，由呼叫者 `check_and_consume_quota` 統一控制鎖。
**狀態**: ✅ **已修復** (v1.0.1)

### ISSUE-015: Telegram Long Polling 衝突 (已修復)
**現象**: `Conflict: terminated by other getUpdates request; make sure that only one bot instance is running`
**原因**: 多個 bot 實例同時運行輪詢，或未正確清理 webhook/pending updates
**修復**: 
- 啟動前呼叫 `deleteWebhook(drop_pending_updates=True)`
- 確保單一實例運行 (`pkill -f "bot.main"`)
- 使用 `drop_pending_updates=False` 避免重複清理
**狀態**: ✅ **已修復** (v1.0.2)

### ISSUE-016: DuckDuckGo 搜尋回傳 0 結果 (已修復)
**現象**: 搜尋關鍵字正確但回傳 0 筆結果
**原因**: 
1. `Accept-Encoding: br` (Brotli) 導致回應未正確解壓
2. CSS 選擇器 `.result__body, .web-result, .result` 導致重複選取，去重邏輯失效
**修復**:
1. 移除 `Accept-Encoding: br`，改用 `gzip, deflate`
2. 簡化選擇器為 `.result__body` 避免重複
**狀態**: ✅ **已修復** (v1.0.2)

### ISSUE-017: Google News XML 實體解碼錯誤 (已修復)
**現象**: `decode_xml_entities` 語法錯誤，智慧引號導致語法錯誤
**修復**: 重寫 `decode_xml_entities` 使用 Unicode escape sequences
**狀態**: ✅ **已修復** (v1.0.2)

### ISSUE-018: Markdown 解析器衝突 (已修復)
**現象**: 粗體 `**bold**` 顯示為 `**`，inline code 被斜體規則誤處理
**修復**: 重寫 `markdown_to_html` 使用 placeholder 保護策略
**狀態**: ✅ **已修復** (v1.0.2)

### ISSUE-019: `search_sync` event loop 衝突 (已修復)
**現象**: `RuntimeError: This event loop is already running`
**修復**: 使用 `ThreadPoolExecutor` 隔離執行
**狀態**: ✅ **已修復** (v1.0.2)

### ISSUE-002: DuckDuckGo HTML 抓取易失效
**現象**: 搜尋回傳空結果、或被導向驗證頁面 (CAPTCHA)。
**原因**: DuckDuckGo 反爬蟲機制 (同 IP 短時間大量請求時回傳 HTTP 202 + anomaly 驗證頁)、HTML 結構變更。
**規避** (v1.0.3 起自動處理):
- 偵測到驗證頁時，DuckDuckGo 暫停 10 分鐘 (`BLOCK_COOLDOWN_SECONDS`)，避免持續請求延長封鎖
- 主引擎無結果時自動改用 `SEARCH_FALLBACK_ENGINE` (預設 `google_news`)，日誌顯示 `🚫` / `↪️`
- 也可直接切換 `SEARCH_ENGINE=google_news` (RSS 格式穩定，但偏新聞)
- 不繞過 CAPTCHA；大量測試 (如 `test/e2e_bot.py` 連跑) 容易觸發

### ISSUE-020: 小模型心算不穩定
**現象**: llama3.1 (8B) 回答多位數乘法偶爾算錯 (如 123 × 456 答 56148)。
**原因**: 小型語言模型以文字預測數字，非真正計算。
**規避**: system prompt 要求逐步列出計算過程，正確率提升但仍非 100% (`test/e2e_bot.py` 第 3 題約半數通過)。
**計劃**: 新增計算工具 (以 Python 安全求值) 或改用較大模型。

### ISSUE-003: 長對話超出模型 Context Window
**現象**: 對話歷史過長導致模型截斷、遺忘早期內容、報錯。
**原因**: `MAX_HISTORY_TURNS=4` (8 則訊息) 但模型 context 可能較小 (qwen2.5: 32k, llama3.1: 128k)。
**規避**:
- 降低 `MAX_HISTORY_TURNS` (如設為 2-3)
- 實作對話摘要壓縮 (待開發)
- 監控 token 使用量 (Ollama 回傳 `eval_count`)

---

## 🟡 中優先級 (影響體驗)

### ISSUE-004: 無串流式回覆
**現象**: 必須等待模型完整生成才收到回覆，體感較慢。
**原因**: 目前用 `chat_with_tools` (stream=false) 簡化工具循環邏輯。
**計劃**: 實作串流 + 工具呼叫混合模式 (需解析增量 JSON)。

### ISSUE-005: 單執行緒阻塞
**現象**: 處理一個請求時，其他用戶需排隊等待。
**原因**: Python asyncio 單執行緒 + 同步搜尋/模型推論。
**修復**: v1.0.3 啟用 `concurrent_updates(True)`，多個請求可同時處理；實際吞吐仍受 Ollama 推論速度限制 (`OLLAMA_NUM_PARALLEL`)。
**狀態**: ✅ **已修復** (v1.0.3)

### ISSUE-006: 配額重置依賴系統時間
**現象**: 若主機時區錯誤或手動改時間，配額重置異常。
**原因**: `date.today()` 取本地日期。
**規避**:
- 確保主機 NTP 同步: `timedatectl set-ntp true`
- 或改用固定時區 (如 `Asia/Taipei`) 計算日期

### ISSUE-007: 無 Webhook 模式
**現象**: 僅支援 Long Polling，不適合生產部署。
**計劃**: 新增 Webhook 支援 (需 HTTPS 域名、nginx、憑證)。

### ISSUE-008: 日誌輪轉缺失
**現象**: `logs/bot.log` 與 `data/logs/interactions_*.jsonl` 會無限增長。
**規避**:
- 定期手動清理: `find logs -name "*.log" -mtime +30 -delete`
- 計劃加入 `logging.handlers.TimedRotatingFileHandler`

---

## 🟢 低優先級 (改善項目)

### ISSUE-009: 錯誤訊息過於技術化
**現象**: 例外堆疊直接回覆給用戶，非技術用戶難以理解。
**計劃**: 統一錯誤碼對應友善訊息對照表。

### ISSUE-010: 搜尋結果去重不完善
**現象**: 多輪搜尋可能回傳重複連結。
**規避**: `handler.py` 中用 `seen_urls` set 去重，但跨輪次未共享。

### ISSUE-011: 無單元測試
**現象**: `test/` 目錄測試尚未完整 (多數依賴網路/Ollama)。
**計劃**: 
- `pytest` + `pytest-asyncio` 測試搜尋、工具循環、配額邏輯
- Mock Ollama 回應測試各種工具呼叫場景

### ISSUE-012: 無 Docker 支援
**現象**: 部署需手動安裝 Python、Ollama、拉取模型。
**計劃**: 提供 `Dockerfile` + `docker-compose.yml` (含 Ollama service)。

### ISSUE-013: Windows 相容性未測試
**現象**: 路徑分隔符、執行緒鎖、信號處理可能有問題。
**規避**: 建議在 WSL2 或 Linux/macOS 運行。

---

## 📋 追蹤表

| ID | 標題 | 優先級 | 狀態 | 目標版本 | 負責人 |
|----|------|--------|------|----------|--------|
| 001 | qwen2.5 Function Calling 穩定性 | 🔴 高 | ✅ **已解決** (切換 llama3.1) | 1.0.1 | - |
| 014 | 配額檢查死鎖 | 🔴 高 | ✅ **已修復** | 1.0.1 | - |
| 015 | Telegram Long Polling 衝突 | 🔴 高 | ✅ **已修復** | 1.0.2 | - |
| 016 | DuckDuckGo 搜尋回傳 0 結果 | 🔴 高 | ✅ **已修復** | 1.0.2 | - |
| 017 | Google News XML 實體解碼錯誤 | 🔴 高 | ✅ **已修復** | 1.0.2 | - |
| 018 | Markdown 解析器衝突 | 🔴 高 | ✅ **已修復** | 1.0.2 | - |
| 019 | search_sync event loop 衝突 | 🔴 高 | ✅ **已修復** | 1.0.2 | - |
| 002 | DuckDuckGo HTML 抓取易失效 | 🔴 高 | 自動備援 (v1.0.3) | 1.1.0 | - |
| 020 | 小模型心算不穩定 | 🟡 中 | 規避中 | 1.1.0 | - |
| 003 | Context Window 溢位 | 🔴 高 | 監控中 | 1.1.0 | - |
| 004 | 無串流回覆 | 🟡 中 | 規劃中 | 1.2.0 | - |
| 005 | 單執行緒阻塞 | 🟡 中 | ✅ **已修復** | 1.0.3 | - |
| 006 | 配額時區依賴 | 🟡 中 | 文檔說明 | 1.1.0 | - |
| 007 | 無 Webhook | 🟡 中 | 規劃中 | 1.2.0 | - |
| 008 | 日誌輪轉 | 🟡 中 | 規劃中 | 1.1.0 | - |
| 009 | 錯誤訊息友善化 | 🟢 低 | ✅ **已修復** | 1.0.3 | - |
| 010 | 搜尋去重優化 | 🟢 低 | 待辦 | 1.2.0 | - |
| 011 | 單元測試 | 🟢 低 | 待辦 | 1.1.0 | - |
| 012 | Docker 支援 | 🟢 低 | 待辦 | 1.2.0 | - |
| 013 | Windows 測試 | 🟢 低 | 待辦 | - | - |

---

## 回報新 Issue

請在專案建立 Issue 並包含：
1. **復現步驟** (最小化)
2. **預期行為** vs **實際行為**
3. **環境資訊** (Python/uv/Ollama/模型版本、OS)
4. **相關日誌** (`logs/bot.log` 擷取)