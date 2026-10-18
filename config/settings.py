"""
本地 Bot 設定檔 - 從環境變數或 .env 讀取
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 載入 .env 檔案
env_path = Path(__file__).parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

SUPPORTED_SEARCH_ENGINES = ('duckduckgo', 'google_news', 'ddgs')
SUPPORTED_SEARCH_DECISIONS = ('router', 'tools')


def _parse_user_ids(raw: str) -> tuple[list[int], list[str]]:
    """解析逗號分隔的 User ID，回傳 (有效 ID, 無效項目)"""
    ids, invalid = [], []
    for x in raw.split(','):
        x = x.strip()
        if not x:
            continue
        if x.lstrip('-').isdigit():
            ids.append(int(x))
        else:
            invalid.append(x)
    return ids, invalid


_allowed_ids, _invalid_ids = _parse_user_ids(os.getenv('ALLOWED_USER_IDS', ''))


class Settings:
    # 注意：設定於啟動時讀取，修改 .env 後需重啟 Bot 才會生效

    # === Telegram Bot 設定 ===
    TELEGRAM_BOT_TOKEN: str = os.getenv('TELEGRAM_BOT_TOKEN', '')
    ALLOWED_USER_IDS: list[int] = _allowed_ids
    INVALID_USER_IDS: list[str] = _invalid_ids

    # === Ollama / 本地 LLM 設定 ===
    OLLAMA_BASE_URL: str = os.getenv('OLLAMA_BASE_URL', 'http://127.0.0.1:11434')
    # 支援 Function Calling 的模型建議：
    # - llama3.1 / llama3.2 (需較新版本 Ollama)
    # - nemotron3-ultra
    # - command-r / command-r-plus
    OLLAMA_MODEL: str = os.getenv('OLLAMA_MODEL', 'llama3.1')
    OLLAMA_TIMEOUT: int = int(os.getenv('OLLAMA_TIMEOUT', '120'))  # 秒
    # 上下文長度 (tokens)；Ollama 預設僅 2048~4096，容不下 system prompt + 歷史 + 搜尋結果
    OLLAMA_NUM_CTX: int = int(os.getenv('OLLAMA_NUM_CTX', '8192'))

    # === 搜尋設定 ===
    SEARCH_ENGINE: str = os.getenv('SEARCH_ENGINE', 'duckduckgo')  # duckduckgo | google_news | ddgs
    # 主引擎無結果或被封鎖時的備援引擎；設為空字串則停用
    SEARCH_FALLBACK_ENGINE: str = os.getenv('SEARCH_FALLBACK_ENGINE', 'ddgs')
    # 搜尋後讀取前 N 筆結果的網頁內文給模型 (0 = 只用搜尋摘要)
    SEARCH_FETCH_PAGES: int = int(os.getenv('SEARCH_FETCH_PAGES', '2'))
    # 每頁內文摘錄上限字數 (受 OLLAMA_NUM_CTX 限制，過大會擠掉對話歷史)
    SEARCH_PAGE_CHARS: int = int(os.getenv('SEARCH_PAGE_CHARS', '1500'))
    SEARCH_MAX_RESULTS: int = int(os.getenv('SEARCH_MAX_RESULTS', '4'))
    SEARCH_TIMEOUT: int = int(os.getenv('SEARCH_TIMEOUT', '15'))  # 秒
    # 搜尋判斷方式：
    # - router：先讓模型輸出 JSON 判斷要不要搜 (適用所有模型，llama3.1 / qwen2.5 建議)
    # - tools ：原生 Function Calling，模型自行呼叫工具 (需模型能正確判斷，如 gemma4)
    SEARCH_DECISION: str = os.getenv('SEARCH_DECISION', 'router')

    # === 對話記憶設定 ===
    MAX_HISTORY_TURNS: int = int(os.getenv('MAX_HISTORY_TURNS', '4'))
    CACHE_DIR: Path = Path(__file__).parent.parent / 'data' / 'cache'

    # === 配額設定 ===
    MAX_DAILY_REQUESTS: int = int(os.getenv('MAX_DAILY_REQUESTS', '50'))
    QUOTA_DIR: Path = Path(__file__).parent.parent / 'data' / 'quota'

    # === 日誌設定 ===
    LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO')
    LOG_FILE: Path = Path(__file__).parent.parent / 'logs' / 'bot.log'

    # === Webhook 設定 (若使用 webhook 模式) ===
    WEBHOOK_URL: str = os.getenv('WEBHOOK_URL', '')
    WEBHOOK_PORT: int = int(os.getenv('WEBHOOK_PORT', '8443'))
    WEBHOOK_HOST: str = os.getenv('WEBHOOK_HOST', '0.0.0.0')

    @classmethod
    def validate(cls) -> list[str]:
        """驗證必要設定"""
        errors = []
        if not cls.TELEGRAM_BOT_TOKEN:
            errors.append('TELEGRAM_BOT_TOKEN 未設定')
        if not cls.ALLOWED_USER_IDS:
            errors.append('ALLOWED_USER_IDS 未設定 (至少需一個用戶 ID)')
        if cls.INVALID_USER_IDS:
            errors.append(f'ALLOWED_USER_IDS 含非數字項目: {", ".join(cls.INVALID_USER_IDS)}')
        if cls.SEARCH_DECISION not in SUPPORTED_SEARCH_DECISIONS:
            errors.append(
                f'SEARCH_DECISION={cls.SEARCH_DECISION} 不支援 (可用: {" | ".join(SUPPORTED_SEARCH_DECISIONS)})'
            )
        if cls.SEARCH_FALLBACK_ENGINE and cls.SEARCH_FALLBACK_ENGINE not in SUPPORTED_SEARCH_ENGINES:
            errors.append(
                f'SEARCH_FALLBACK_ENGINE={cls.SEARCH_FALLBACK_ENGINE} 不支援 '
                f'(可用: {" | ".join(SUPPORTED_SEARCH_ENGINES)}，或留空停用)'
            )
        if cls.SEARCH_ENGINE not in SUPPORTED_SEARCH_ENGINES:
            errors.append(
                f'SEARCH_ENGINE={cls.SEARCH_ENGINE} 不支援 (可用: {" | ".join(SUPPORTED_SEARCH_ENGINES)})'
            )
        return errors


settings = Settings()
