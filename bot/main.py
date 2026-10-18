"""
本地 AI Telegram Bot - 主程式入口
運行方式:
  uv run python -m bot.main              # 接 Telegram (Token 未設定時啟動會詢問，不存檔)
  uv run python -m bot.main --simulate   # 模擬模式：終端機打字，不需要 Telegram
"""
import asyncio
import getpass
import logging
import sys
from pathlib import Path

from config.settings import Settings, _parse_user_ids, settings

# 設定日誌
log_dir = Path(__file__).parent.parent / 'logs'
log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(log_dir / 'bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ],
)

# 設定第三方庫日誌等級
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
# ddgs 會記錄每個引擎的回應與失敗 (屬正常切換)，只保留真正錯誤
logging.getLogger('ddgs').setLevel(logging.ERROR)
logging.getLogger('primp').setLevel(logging.WARNING)  # ddgs 底層 HTTP 套件，會記錄每個引擎的回應
logging.getLogger('telegram').setLevel(logging.INFO)

logger = logging.getLogger(__name__)


def prompt_missing_secrets():
    """
    .env 沒有 Token / 白名單時，啟動當下詢問 (Token 用 getpass 不顯示在畫面)
    只存在這次執行的記憶體裡，不寫進任何檔案
    """
    if not sys.stdin.isatty():
        return
    if not Settings.TELEGRAM_BOT_TOKEN:
        token = getpass.getpass(
            '🔑 請貼上 Telegram Bot Token (@BotFather 提供；貼上時畫面不會顯示，也不會存檔)：'
        ).strip()
        Settings.TELEGRAM_BOT_TOKEN = token
    if not Settings.ALLOWED_USER_IDS and not Settings.INVALID_USER_IDS:
        raw = input('👤 請輸入允許使用的 Telegram User ID (@userinfobot 可查，多個用逗號分隔)：')
        Settings.ALLOWED_USER_IDS, Settings.INVALID_USER_IDS = _parse_user_ids(raw)


async def main():
    """主程式"""
    from bot.handler import setup_bot

    # 驗證設定 (缺 Token / 白名單時先詢問)
    prompt_missing_secrets()
    errors = settings.validate()
    if errors:
        logger.error('❌ 設定錯誤:')
        for err in errors:
            logger.error(f'  - {err}')
        logger.error('請在 .env 設定，或啟動時依提示貼上 (不想存檔可留空)；只想在終端機測試請加 --simulate')
        sys.exit(1)

    logger.info('=' * 50)
    logger.info('🤖 本地 AI Telegram Bot 啟動中...')
    logger.info(f'   模型: {settings.OLLAMA_MODEL}')
    logger.info(f'   Ollama: {settings.OLLAMA_BASE_URL}')
    logger.info(f'   搜尋引擎: {settings.SEARCH_ENGINE}')
    logger.info(f'   白名單用戶: {len(settings.ALLOWED_USER_IDS)} 位')
    logger.info(f'   每日額度: {settings.MAX_DAILY_REQUESTS} 次')
    logger.info('=' * 50)

    # 建立並啟動 Bot
    application = await setup_bot()

    # 初始化
    await application.initialize()
    await application.start()

    # 刪除現有 webhook (使用 polling 模式)
    await application.bot.delete_webhook(drop_pending_updates=True)

    logger.info('✅ Bot 已啟動，開始輪詢訊息... (Ctrl+C 停止)')

    try:
        # 開始 polling
        logger.debug('Starting polling...')
        await application.updater.start_polling(
            allowed_updates=['message', 'callback_query'],
            drop_pending_updates=False,
        )
        logger.debug('Polling started successfully')

        # 保持運行
        while True:
            await asyncio.sleep(3600)

    except KeyboardInterrupt:
        logger.info('\n⏹️ 收到停止訊號，正在關閉...')
    except Exception as e:
        logger.error(f'❌ 執行錯誤: {e}', exc_info=True)
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        logger.info('👋 Bot 已停止')


if __name__ == '__main__':
    if '--simulate' in sys.argv:
        from bot.simulate import run_simulation
        entry = run_simulation
    else:
        entry = main
    try:
        asyncio.run(entry())
    except KeyboardInterrupt:
        print('\n👋 已停止')
