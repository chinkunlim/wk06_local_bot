"""
Telegram Bot 主處理器 - 整合對話、搜尋、LLM 呼叫
"""
import html
import json
import logging

from telegram import Message, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from bot.conversation import (
    check_and_consume_quota,
    clear_conversation_history,
    get_conversation_history,
    get_quota_status,
    is_user_authorized,
    log_interaction,
    save_conversation_turn,
)
from config.settings import settings
from llm.ollama_client import (
    SEARCH_TOOL,
    SYSTEM_PROMPT,
    get_ollama_client,
    init_ollama,
)
from search import format_results, search


def markdown_to_html(text: str) -> str:
    """將 Markdown 轉換為 Telegram 支援的 HTML"""
    if not text:
        return ''

    import re

    # ===== 階段 0: 保護所有特殊標記 =====
    protected = {}
    prot_id = 0

    def protect(match):
        nonlocal prot_id
        key = f'__PROTECTED_{prot_id}__'
        prot_id += 1
        protected[key] = match.group(0)
        return key

    # 保護程式碼區塊
    text = re.sub(r'```[\s\S]*?```', protect, text)
    # 保護行內程式碼
    text = re.sub(r'`[^`\n]+`', protect, text)
    # 保護已有的 Telegram 支援 HTML 標籤 (其餘 < > 如 "5 < 10" 需跳脫)
    text = re.sub(
        r'</?(?:b|strong|i|em|u|ins|s|strike|del|code|pre|a|tg-spoiler|blockquote)(?:\s[^<>]*)?>',
        protect,
        text,
    )

    # ===== 階段 1: HTML 跳脫 =====
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    # ===== 階段 2: 處理 Markdown =====
    # 粗體 **text** (處理未閉合)
    bold_count = text.count('**')
    if bold_count % 2 != 0:
        text += '**'
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)

    # 斜體 *text* 或 _text_
    text = re.sub(r'(^|[^\*])\*([^\*\n]+)\*([^\*]|$)', r'\1<i>\2</i>\3', text)
    text = re.sub(r'(^|[^_])_([^_\n]+)_([^_]|$)', r'\1<i>\2</i>\3', text)

    # 標題 # text -> <b>text</b>
    text = re.sub(r'^#{1,6}\s*(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)

    # 項目符號 - 或 * 開頭
    text = re.sub(r'^[\*\-\+]\s+(.+)$', r'• \1', text, flags=re.MULTILINE)

    # 分割線
    text = re.sub(r'^---+$', '──────────────', text, flags=re.MULTILINE)

    # 超連結 [text](url)
    text = re.sub(r'\[([^\]]+)\]\((https?://[^\s)]+)\)', r'<a href="\2">\1</a>', text)

    # ===== 階段 2: 還原受保護內容 =====
    def restore_protected(match):
        key = match.group(0)
        if key in protected:
            content = protected[key]
            # 程式碼區塊
            if content.startswith('```') and content.endswith('```'):
                code = content[3:-3]
                # 移除語言指定符
                lines = code.split('\n')
                if lines and lines[0].strip() and ' ' not in lines[0].strip():
                    code = '\n'.join(lines[1:])
                escaped = code.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                return f'<pre><code>{escaped.strip()}</code></pre>'
            # 行內程式碼
            if content.startswith('`') and content.endswith('`'):
                code = content[1:-1]
                escaped = code.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                return f'<code>{escaped}</code>'
            # HTML 標籤直接還原
            return content
        return key

    text = re.sub(r'__PROTECTED_\d+__', restore_protected, text)

    return text

logger = logging.getLogger(__name__)


class BotHandler:
    """Telegram Bot 核心處理邏輯"""

    def __init__(self):
        self.ollama_client = get_ollama_client()
        self._status_messages: dict[int, int] = {}  # chat_id -> message_id

    async def send_status(
        self,
        update: Update,
        text: str,
        parse_mode: ParseMode = ParseMode.HTML,
    ) -> Message | None:
        """發送或更新狀態訊息"""
        chat_id = update.effective_chat.id

        if chat_id in self._status_messages:
            try:
                msg = await update.get_bot().edit_message_text(
                    chat_id=chat_id,
                    message_id=self._status_messages[chat_id],
                    text=text,
                    parse_mode=parse_mode,
                    disable_web_page_preview=True,
                )
                return msg
            except Exception:
                # 編輯失敗則發送新訊息
                pass

        msg = await update.message.reply_text(
            text,
            parse_mode=parse_mode,
            disable_web_page_preview=True,
        )
        self._status_messages[chat_id] = msg.message_id
        return msg

    async def send_final_response(
        self,
        update: Update,
        text: str,
        parse_mode: ParseMode = ParseMode.HTML,
    ) -> Message | None:
        """發送最終回覆 (替換狀態訊息)"""
        chat_id = update.effective_chat.id

        if chat_id in self._status_messages:
            try:
                msg = await update.get_bot().edit_message_text(
                    chat_id=chat_id,
                    message_id=self._status_messages[chat_id],
                    text=text,
                    parse_mode=parse_mode,
                    disable_web_page_preview=True,
                )
                del self._status_messages[chat_id]
                return msg
            except Exception as e:
                logger.warning(f'編輯訊息失敗，改發送新訊息: {e}')

        msg = await update.message.reply_text(
            text,
            parse_mode=parse_mode,
            disable_web_page_preview=True,
        )
        if chat_id in self._status_messages:
            del self._status_messages[chat_id]
        return msg

    async def send_error(
        self,
        update: Update,
        text: str,
    ):
        """發送錯誤訊息"""
        await self.send_final_response(update, f'❌ <b>錯誤</b>\n\n{text}')

    # === 指令處理器 ===

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """啟動指令"""
        logger.info(f'[DEBUG] cmd_start called by user {update.effective_user.id}')
        user = update.effective_user
        welcome = (
            f'👋 <b>歡迎使用本地 AI 助理！</b>\n\n'
            f'你好，{html.escape(user.first_name or "")}！我是運行在本地的開源模型助理。\n\n'
            f'🔧 <b>技術架構：</b>\n'
            f'• 模型：<code>{settings.OLLAMA_MODEL}</code> (via Ollama)\n'
            f'• 搜尋：<code>{settings.SEARCH_ENGINE}</code>\n'
            f'• 對話記憶：最近 {settings.MAX_HISTORY_TURNS} 輪\n\n'
            f'📌 <b>常用指令：</b>\n'
            f'/search <code>關鍵字</code> - 即時搜尋並總結\n'
            f'/news - 查看最新新聞頭條\n'
            f'/status - 查詢今日剩餘額度\n'
            f'/reset - 清除對話記憶\n'
            f'/models - 列出本地可用模型\n'
            f'/help - 顯示完整說明\n\n'
            f'請直接傳送文字向我提問！'
        )
        await update.message.reply_text(welcome, parse_mode=ParseMode.HTML)

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """說明指令"""
        help_text = (
            '📖 <b>本地 AI 助理使用說明</b>\n\n'
            '• <b>一般提問</b>：直接輸入問題，我會根據上下文回答\n'
            '• <b>自動搜尋</b>：詢問含「最新、新聞、即時、今天」等關鍵字時，我會自動搜尋網路\n'
            '• <b>/search <code>關鍵字</code></b>：主動搜尋特定主題\n'
            '• <b>/news</b>：瀏覽最新新聞頭條\n'
            '• <b>/status</b>：查看今日已用/剩餘額度\n'
            '• <b>/reset</b>：清除對話記憶，開啟新話題\n'
            '• <b>/models</b>：查看本地 Ollama 可用模型\n'
            '• <b>/help</b>：顯示本說明'
        )
        await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """查詢額度"""
        user_id = update.effective_user.id
        status = get_quota_status(user_id)

        text = (
            f'📊 <b>今日使用額度</b>\n\n'
            f'📅 日期：{status["date"]}\n'
            f'📈 已使用：<b>{status["current"]}</b> 次\n'
            f'🎯 剩餘：<b>{status["remaining"]}</b> 次\n'
            f'🔒 每日上限：{status["max"]} 次\n\n'
            f'<i>額度於每日午夜 00:00 自動重置</i>'
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async def cmd_reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """重置對話記憶"""
        user_id = update.effective_user.id
        clear_conversation_history(user_id)
        await update.message.reply_text(
            '🧹 <b>對話記憶已清空！</b>\n\n接下來的提問將以全新視角為您解答。',
            parse_mode=ParseMode.HTML,
        )

    async def cmd_models(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """列出本地模型"""
        await self.send_status(update, '🔍 正在查詢本地 Ollama 模型...')

        try:
            models = await self.ollama_client.list_models()
            if not models:
                await self.send_final_response(update, '⚠️ 本地無任何模型，請執行 <code>ollama pull <模型名></code>')
                return

            lines = ['📦 <b>本地可用模型：</b>\n']
            for m in models:
                name = m.get('name', '未知')
                size = m.get('size', 0)
                size_gb = size / (1024**3)
                modified = m.get('modified_at', '')[:10]
                current_mark = ' 👉' if settings.OLLAMA_MODEL in name else ''
                lines.append(f'• <code>{name}</code> ({size_gb:.1f} GB, {modified}){current_mark}')

            lines.append(f'\n目前使用：<b>{settings.OLLAMA_MODEL}</b>')
            lines.append('\n💡 切換模型：修改 .env 的 <code>OLLAMA_MODEL</code> 並重啟 Bot')

            await self.send_final_response(update, '\n'.join(lines))
        except Exception as e:
            await self.send_error(update, f'查詢模型失敗: {html.escape(str(e))}')

    async def cmd_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """搜尋指令"""
        user_id = update.effective_user.id

        # 檢查授權
        if not is_user_authorized(user_id):
            await self.send_error(update, '您未在授權白名單中')
            return

        # 檢查額度
        quota = check_and_consume_quota(user_id)
        if not quota['allowed']:
            await self.send_error(update, quota['message'])
            return

        # 取得查詢參數
        query = ' '.join(context.args) if context.args else ''
        if not query:
            await update.message.reply_text(
                '請提供搜尋關鍵字，例如：<code>/search 台灣 亞運 金牌</code>',
                parse_mode=ParseMode.HTML,
            )
            return

        await self._process_query(update, query, quota, is_search_command=True)

    async def cmd_news(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """新聞指令"""
        user_id = update.effective_user.id

        if not is_user_authorized(user_id):
            await self.send_error(update, '您未在授權白名單中')
            return

        quota = check_and_consume_quota(user_id)
        if not quota['allowed']:
            await self.send_error(update, quota['message'])
            return

        await self._process_query(update, '最新新聞頭條', quota, is_search_command=True)

    # === 核心處理邏輯 ===

    async def _process_query(
        self,
        update: Update,
        user_query: str,
        quota: dict,
        is_search_command: bool = False,
    ):
        """處理使用者查詢 (含工具呼叫循環)"""
        _debug_log(f'[DEBUG] _process_query started: query={user_query[:50]}')
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or update.effective_user.username or '匿名'

        # 發送初始狀態
        await self.send_status(update, '🤔 思考中...')

        # 取得對話歷史
        history = get_conversation_history(user_id)
        _debug_log(f'[DEBUG] History length: {len(history)}')

        # 構建訊息
        messages = [{'role': 'system', 'content': SYSTEM_PROMPT}]
        messages.extend(history)
        messages.append({'role': 'user', 'content': user_query})

        # 工具呼叫循環 (最多 3 輪)
        max_tool_rounds = 3
        tool_results = []

        for round_num in range(max_tool_rounds):
            _debug_log(f'[DEBUG] Tool round {round_num + 1}')
            # 呼叫 LLM
            response = await self.ollama_client.chat_with_tools(
                messages=messages,
                tools=[SEARCH_TOOL],
                tool_choice='auto',
            )
            _debug_log(f'[DEBUG] LLM response: {response}')

            message = response.get('message', {})
            tool_calls = message.get('tool_calls', [])
            _debug_log(f'[DEBUG] Tool calls: {tool_calls}')

            if not tool_calls:
                # 沒有工具呼叫，直接回覆
                assistant_reply = message.get('content', '').strip()
                _debug_log(f'[DEBUG] No tool calls, reply: {assistant_reply[:100] if assistant_reply else "empty"}')
                if assistant_reply:
                    await self._finalize_response(
                        update, user_id, user_name, user_query,
                        assistant_reply, tool_results, quota
                    )
                else:
                    await self.send_error(update, '模型未產生回覆')
                return

            # 有工具呼叫 - 執行搜尋
            await self.send_status(update, f'🔍 正在搜尋資訊 (第 {round_num + 1} 輪)...')

            # 將 assistant 的工具呼叫加入訊息
            messages.append(message)

            # 執行每個工具呼叫
            for tool_call in tool_calls:
                func_name = tool_call.get('function', {}).get('name')
                func_args = tool_call.get('function', {}).get('arguments', {})
                # Ollama 回傳 dict，OpenAI 相容格式回傳 JSON 字串
                if isinstance(func_args, str):
                    try:
                        func_args = json.loads(func_args) if func_args.strip() else {}
                    except json.JSONDecodeError:
                        logger.warning(f'工具參數 JSON 解析失敗: {func_args!r}')
                        func_args = {}

                if func_name == 'search_web':
                    query = func_args.get('query', '')
                    _debug_log(f'[DEBUG] Model calling search: "{query}"')

                    # 執行搜尋
                    results = await search(query, settings.SEARCH_MAX_RESULTS)
                    _debug_log(f'[DEBUG] Search results count: {len(results)}')
                    formatted = format_results(results)

                    tool_results.append({
                        'query': query,
                        'results': results,
                        'formatted': formatted,
                    })

                    # 將工具結果加入訊息
                    messages.append({
                        'role': 'tool',
                        'content': formatted,
                        'tool_call_id': tool_call.get('id', ''),
                    })
                else:
                    logger.warning(f'未知工具: {func_name}')
                    messages.append({
                        'role': 'tool',
                        'content': f'錯誤：未知工具 {func_name}',
                        'tool_call_id': tool_call.get('id', ''),
                    })

        # 工具循環結束，取得最終回覆
        await self.send_status(update, '🧠 整理回答中...')

        final_response = await self.ollama_client.chat_with_tools(
            messages=messages,
            tools=None,  # 最後一輪不需要工具
        )

        assistant_reply = final_response.get('message', {}).get('content', '').strip()
        if assistant_reply:
            await self._finalize_response(
                update, user_id, user_name, user_query,
                assistant_reply, tool_results, quota
            )
        else:
            await self.send_error(update, '模型未產生最終回覆')

    async def _finalize_response(
        self,
        update: Update,
        user_id: int,
        user_name: str,
        user_query: str,
        assistant_reply: str,
        tool_results: list[dict],
        quota: dict,
    ):
        """完成回覆：加上來源、額度、儲存歷史"""

        # 格式化來源
        sources_text = ''
        if tool_results:
            sources_text = '\n\n🔍 <b>搜尋來源：</b>'
            seen_urls = set()
            for tr in tool_results:
                for r in tr['results'][:3]:
                    url = r.get('url', '')
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        title = html.escape(r.get('title', '來源')[:60])
                        sources_text += f'\n• <a href="{html.escape(url)}">{title}</a>'

        # 加上額度資訊
        footer = f'\n\n<i>(本日已提問: {quota["current"]}/{quota["max"]})</i>'

        # 轉換 Markdown 為 HTML
        formatted_reply = markdown_to_html(assistant_reply)
        final_text = formatted_reply + sources_text + footer

        # 發送最終回覆
        await self.send_final_response(update, final_text)

        # 儲存對話歷史
        save_conversation_turn(user_id, user_query, assistant_reply)

        # 記錄日誌
        log_interaction(
            user_id=user_id,
            user_name=user_name,
            prompt=user_query,
            response=assistant_reply,
            tokens={},  # Ollama 不直接回傳 token 數
            daily_count=quota['current'],
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """處理一般文字訊息"""
        print(f'[DEBUG] handle_message called: user_id={update.effective_user.id}, text={update.message.text[:50] if update.message.text else "empty"}')
        _debug_log(f'[DEBUG] handle_message called: user_id={update.effective_user.id}, text={update.message.text[:50] if update.message.text else "empty"}')
        user_id = update.effective_user.id

        # 檢查授權
        if not is_user_authorized(user_id):
            _debug_log(f'[DEBUG] User {user_id} not authorized')
            await update.message.reply_text(
                f'⛔ <b>存取受限</b>\n\n'
                f'抱歉，您尚未加入授權白名單。\n'
                f'您的 Telegram User ID：<code>{user_id}</code>\n\n'
                f'請聯繫管理員將您的 ID 加入 <code>ALLOWED_USER_IDS</code>。',
                parse_mode=ParseMode.HTML,
            )
            return

        # 檢查額度
        quota = check_and_consume_quota(user_id)
        if not quota['allowed']:
            _debug_log(f'[DEBUG] User {user_id} quota exceeded')
            await self.send_error(update, quota['message'])
            return

        # 處理查詢
        user_query = update.message.text.strip()
        _debug_log(f'[DEBUG] Processing query: {user_query[:50]}')
        await self._process_query(update, user_query, quota)


# 全域處理器實例
bot_handler = BotHandler()

def _debug_log(msg):
    import logging
    logging.getLogger(__name__).info(f'[DEBUG] {msg}')

async def setup_bot() -> Application:
    """建立並設定 Telegram Bot Application"""
    # 初始化 Ollama
    await init_ollama()

    # 建立 Application
    application = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

    # 註冊指令
    _debug_log('Registering handlers...')
    application.add_handler(CommandHandler('start', bot_handler.cmd_start))
    application.add_handler(CommandHandler('help', bot_handler.cmd_help))
    application.add_handler(CommandHandler('status', bot_handler.cmd_status))
    application.add_handler(CommandHandler('reset', bot_handler.cmd_reset))
    application.add_handler(CommandHandler('models', bot_handler.cmd_models))
    application.add_handler(CommandHandler('search', bot_handler.cmd_search))
    application.add_handler(CommandHandler('news', bot_handler.cmd_news))

    # 註冊一般訊息處理
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_handler.handle_message))

    _debug_log('Handlers registered successfully')

    return application
