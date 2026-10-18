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

class Settings:
    # === Telegram Bot 設定 ===
    TELEGRAM_BOT_TOKEN: str = os.getenv('TELEGRAM_BOT_TOKEN', '')
    ALLOWED_USER_IDS: list[int] = [
        int(x.strip()) for x in os.getenv('ALLOWED_USER_IDS', '').split(',') if x.strip()
    ]

    # === Ollama / 本地 LLM 設定 ===
    OLLAMA_BASE_URL: str = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
    # 支援 Function Calling 的模型建議：
    # - llama3.1 / llama3.2 (需較新版本 Ollama)
    # - nemotron3-ultra
    # - command-r / command-r-plus
    OLLAMA_MODEL: str = os.getenv('OLLAMA_MODEL', 'llama3.1')
    OLLAMA_TIMEOUT: int = int(os.getenv('OLLAMA_TIMEOUT', '120'))  # 秒

    # === 搜尋設定 ===
    SEARCH_ENGINE: str = os.getenv('SEARCH_ENGINE', 'duckduckgo')  # duckduckgo | google_news_rss
    SEARCH_MAX_RESULTS: int = int(os.getenv('SEARCH_MAX_RESULTS', '4'))
    SEARCH_TIMEOUT: int = int(os.getenv('SEARCH_TIMEOUT', '15'))  # 秒

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
        return errors


settings = Settings()
