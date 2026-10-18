"""
模擬模式 (作業關卡 A)：不接 Telegram，在終端機打字，bot 用本機模型回答

用法: uv run python -m bot.main --simulate

走的是和 Telegram 完全相同的處理流程 (BotHandler._process_query：搜尋判斷 → 搜尋 → 讀網頁 → 回答)，
只把「Telegram 送訊息進來 / 送回覆出去」換成終端機的輸入與輸出，所以不需要 Bot Token。
對話歷史與額度記在模擬專用的使用者 ID 0，不影響真實使用者；每次啟動都是新的對話。
"""
import logging
import readline  # noqa: F401  載入後 input() 才有正確的行內編輯 (中文輸入法、方向鍵、刪除)
import sys
import time
from types import SimpleNamespace

from config.settings import settings

logger = logging.getLogger(__name__)

SIM_USER_ID = 0
QUIT_WORDS = {'quit', 'exit', 'q', '離開', '結束'}

HELP = """指令：
  直接打字   問問題 (需要時會自動上網搜尋)
  /reset     清除對話記憶
  /status    查看今日額度
  quit       結束模擬"""


def _use_short_log_format():
    """終端機日誌改成「[時:分:秒] 訊息」，截圖比較乾淨 (logs/bot.log 仍保留完整格式)"""
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            handler.setFormatter(logging.Formatter('[%(asctime)s] %(message)s', datefmt='%H:%M:%S'))


def _fake_update(update_id: int) -> SimpleNamespace:
    """與 Telegram Update 同樣欄位的假事件 (handler 只用到這些)"""
    return SimpleNamespace(
        update_id=update_id,
        effective_user=SimpleNamespace(id=SIM_USER_ID, first_name='模擬使用者', username=None),
        effective_chat=SimpleNamespace(id=SIM_USER_ID),
    )


async def run_simulation():
    from bot.conversation import (
        check_and_consume_quota,
        clear_conversation_history,
        get_quota_status,
    )
    from bot.handler import BotHandler, html_to_plain
    from llm.ollama_client import init_ollama

    _use_short_log_format()

    errors = settings.validate(require_telegram=False)
    if errors:
        for err in errors:
            logger.error(f'❌ {err}')
        sys.exit(1)

    logger.info(
        f'模擬模式：不接 Telegram。模型 {settings.OLLAMA_MODEL}，'
        f'搜尋 {settings.SEARCH_ENGINE} (備援 {settings.SEARCH_FALLBACK_ENGINE or "無"})'
    )
    logger.info('先載入模型 (第一次要等一下)…')
    start = time.monotonic()
    try:
        client = await init_ollama()
        await client.chat_with_tools(messages=[{'role': 'user', 'content': 'hi'}], max_tokens=1)
    except Exception as e:
        logger.error(f'❌ 無法使用本地模型：{e}')
        logger.error('   請確認 Ollama 已啟動 (macOS：open -a Ollama)，並已 ollama pull 模型')
        sys.exit(1)
    logger.info(f'✅ 模型可以用了 ({time.monotonic() - start:.0f} 秒)。打一句話按 Enter，bot 會回；打 quit 結束。')
    print(HELP + '\n', flush=True)

    # 每次啟動都是新的對話，避免上次模擬的內容混進回答
    clear_conversation_history(SIM_USER_ID)

    bh = BotHandler()
    bh.ollama_client = client

    async def show_status(update, text, parse_mode=None):
        print(f'   ⏳ {html_to_plain(text)}', flush=True)

    async def show_reply(update, text, parse_mode=None):
        print('\n🤖 bot 回覆：\n' + html_to_plain(text) + '\n', flush=True)

    bh.send_status = show_status
    bh.send_final_response = show_reply

    count = 0
    while True:
        try:
            # 在主執行緒讀取：readline 的行內編輯與 Ctrl+C 才能正常運作
            text = input('📱 你：').strip()
        except EOFError:
            break
        if not text:
            continue
        if text.lower() in QUIT_WORDS:
            break
        if text == '/reset':
            clear_conversation_history(SIM_USER_ID)
            print('🧹 對話記憶已清空\n', flush=True)
            continue
        if text == '/status':
            st = get_quota_status(SIM_USER_ID)
            print(f'📊 今日已用 {st["current"]} 次，剩餘 {st["remaining"]} 次\n', flush=True)
            continue

        quota = check_and_consume_quota(SIM_USER_ID)
        if not quota['allowed']:
            print(quota['message'] + '\n', flush=True)
            continue

        count += 1
        # 顯示程式實際收到的文字，若與畫面上打的不同可立即發現
        logger.info(f'📩 收到：「{text}」({len(text)} 字)，交給 {client.model}…')
        await bh._process_query(_fake_update(count), text, quota)

    await client.close()
    print('模擬結束。', flush=True)
