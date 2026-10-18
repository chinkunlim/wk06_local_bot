"""
Telegram Bot 主處理器 - 整合對話、搜尋、LLM 呼叫
"""
import asyncio
import html
import json
import logging
import re
import time

import httpx
from telegram import Message, Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest, TelegramError
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
    refund_quota,
    save_conversation_turn,
)
from config.settings import settings
from llm.ollama_client import (
    SEARCH_TOOL,
    build_system_prompt,
    get_ollama_client,
    init_ollama,
)
from search import format_results, search
from search.page_fetch import enrich_results

logger = logging.getLogger(__name__)

# Telegram 單則訊息上限 4096 字元，保留緩衝
TELEGRAM_MAX_LENGTH = 4000


def _escape(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def markdown_to_html(text: str) -> str:
    """將 Markdown 轉換為 Telegram 支援的 HTML"""
    if not text:
        return ''

    # ===== 階段 0: 保護所有特殊標記 =====
    protected = {}
    prot_id = 0

    def store(content: str) -> str:
        nonlocal prot_id
        key = f'__PROTECTED_{prot_id}__'
        prot_id += 1
        protected[key] = content
        return key

    def protect(match):
        return store(match.group(0))

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
    text = _escape(text)

    # 保護超連結與網址，避免網址內的 _ * 被斜體/粗體規則破壞
    # [text](url)：文字仍可含粗體，網址直接保護
    text = re.sub(
        r'\[([^\]]+)\]\((https?://[^\s)]+)\)',
        lambda m: f'<a href="{store(m.group(2))}">{m.group(1)}</a>',
        text,
    )
    # 純網址 (不在 href="..." 內)
    text = re.sub(r'(?<!href=")https?://[^\s<>()（）。，、；：！？「」]+', protect, text)

    # ===== 階段 2: 處理 Markdown =====
    # 粗體 **text** (處理未閉合)
    bold_count = text.count('**')
    if bold_count % 2 != 0:
        text += '**'
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)

    # 斜體 *text* 或 _text_
    text = re.sub(r'(^|[^\*])\*([^\*\n]+)\*([^\*]|$)', r'\1<i>\2</i>\3', text)
    text = re.sub(r'(^|[^_\w])_([^_\n]+)_([^_\w]|$)', r'\1<i>\2</i>\3', text)

    # 標題 # text -> <b>text</b>
    text = re.sub(r'^#{1,6}\s*(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)

    # 項目符號 - * + 開頭；有縮排 (空白或 tab) 的視為子項目
    text = re.sub(r'^[\*\-\+][ \t]+(.+)$', r'• \1', text, flags=re.MULTILINE)
    text = re.sub(r'^[ \t]+[\*\-\+][ \t]+(.+)$', r'    ◦ \1', text, flags=re.MULTILINE)

    # 分割線
    text = re.sub(r'^---+$', '──────────────', text, flags=re.MULTILINE)

    # ===== 階段 3: 還原受保護內容 =====
    def restore_protected(match):
        key = match.group(0)
        if key not in protected:
            return key
        content = protected[key]
        # 程式碼區塊
        if content.startswith('```') and content.endswith('```'):
            code = content[3:-3]
            # 移除語言指定符
            lines = code.split('\n')
            if lines and lines[0].strip() and ' ' not in lines[0].strip():
                code = '\n'.join(lines[1:])
            return f'<pre><code>{_escape(code.strip())}</code></pre>'
        # 行內程式碼
        if content.startswith('`') and content.endswith('`'):
            return f'<code>{_escape(content[1:-1])}</code>'
        # HTML 標籤、網址直接還原
        return content

    # 受保護內容可能互相巢狀 (如連結文字含行內程式碼)，重複還原
    for _ in range(3):
        restored = re.sub(r'__PROTECTED_\d+__', restore_protected, text)
        if restored == text:
            break
        text = restored

    return text


def split_message(text: str, limit: int = TELEGRAM_MAX_LENGTH) -> list[str]:
    """依換行切割過長訊息，單行超長則硬切"""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ''
    for line in text.split('\n'):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ''
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = f'{current}\n{line}' if current else line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def html_to_plain(text: str) -> str:
    """移除 HTML 標籤並還原實體 (HTML 解析失敗時的退路)"""
    return html.unescape(re.sub(r'<[^>]+>', '', text))


class BotHandler:
    """Telegram Bot 核心處理邏輯"""

    def __init__(self):
        self.ollama_client = get_ollama_client()
        # update_id -> 狀態訊息 message_id (以請求區分，避免同聊天室並發互相覆蓋)
        self._status_messages: dict[int, int] = {}

    async def _reply(self, update: Update, text: str, parse_mode: ParseMode | None) -> Message:
        """回覆訊息；HTML 解析失敗時改送純文字"""
        try:
            return await update.message.reply_text(
                text, parse_mode=parse_mode, disable_web_page_preview=True,
            )
        except BadRequest as e:
            if parse_mode is None:
                raise
            logger.warning(f'HTML 解析失敗，改送純文字: {e}')
            return await update.message.reply_text(
                html_to_plain(text), disable_web_page_preview=True,
            )

    async def _edit(self, update: Update, message_id: int, text: str, parse_mode: ParseMode | None) -> Message:
        """編輯訊息；HTML 解析失敗時改送純文字"""
        bot = update.get_bot()
        chat_id = update.effective_chat.id
        try:
            return await bot.edit_message_text(
                chat_id=chat_id, message_id=message_id, text=text,
                parse_mode=parse_mode, disable_web_page_preview=True,
            )
        except BadRequest as e:
            if parse_mode is None or "can't parse entities" not in str(e).lower():
                raise
            logger.warning(f'HTML 解析失敗，改送純文字: {e}')
            return await bot.edit_message_text(
                chat_id=chat_id, message_id=message_id, text=html_to_plain(text),
                disable_web_page_preview=True,
            )

    async def send_status(
        self,
        update: Update,
        text: str,
        parse_mode: ParseMode = ParseMode.HTML,
    ) -> Message | None:
        """發送或更新狀態訊息"""
        key = update.update_id

        if key in self._status_messages:
            try:
                return await self._edit(update, self._status_messages[key], text, parse_mode)
            except TelegramError:
                # 編輯失敗則發送新訊息
                pass

        try:
            msg = await self._reply(update, text, parse_mode)
        except TelegramError as e:
            logger.warning(f'發送狀態訊息失敗: {e}')
            return None
        self._status_messages[key] = msg.message_id
        return msg

    async def send_final_response(
        self,
        update: Update,
        text: str,
        parse_mode: ParseMode = ParseMode.HTML,
    ) -> Message | None:
        """發送最終回覆 (替換狀態訊息，過長自動分段)"""
        status_id = self._status_messages.pop(update.update_id, None)
        chunks = split_message(text)
        msg = None

        for i, chunk in enumerate(chunks):
            try:
                if i == 0 and status_id is not None:
                    try:
                        msg = await self._edit(update, status_id, chunk, parse_mode)
                        continue
                    except TelegramError as e:
                        logger.warning(f'編輯訊息失敗，改發送新訊息: {e}')
                msg = await self._reply(update, chunk, parse_mode)
            except TelegramError as e:
                logger.error(f'發送回覆失敗 (第 {i + 1}/{len(chunks)} 段): {e}')
        return msg

    async def send_error(
        self,
        update: Update,
        text: str,
    ):
        """發送錯誤訊息"""
        await self.send_final_response(update, f'❌ <b>錯誤</b>\n\n{text}')

    async def _ensure_authorized(self, update: Update) -> bool:
        """檢查白名單，未授權則回覆並回傳 False"""
        user_id = update.effective_user.id
        if is_user_authorized(user_id):
            return True
        logger.debug(f'User {user_id} not authorized')
        await self._reply(
            update,
            f'⛔ <b>存取受限</b>\n\n'
            f'抱歉，您尚未加入授權白名單。\n'
            f'您的 Telegram User ID：<code>{user_id}</code>\n\n'
            f'請聯繫管理員將您的 ID 加入 <code>ALLOWED_USER_IDS</code>。',
            ParseMode.HTML,
        )
        return False

    # === 指令處理器 ===

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """啟動指令"""
        logger.debug(f'cmd_start called by user {update.effective_user.id}')
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
        if not await self._ensure_authorized(update):
            return
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
        if not await self._ensure_authorized(update):
            return
        user_id = update.effective_user.id
        clear_conversation_history(user_id)
        await update.message.reply_text(
            '🧹 <b>對話記憶已清空！</b>\n\n接下來的提問將以全新視角為您解答。',
            parse_mode=ParseMode.HTML,
        )

    async def cmd_models(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """列出本地模型"""
        if not await self._ensure_authorized(update):
            return
        await self.send_status(update, '🔍 正在查詢本地 Ollama 模型...')

        try:
            models = await self.ollama_client.list_models()
            if not models:
                await self.send_final_response(
                    update, '⚠️ 本地無任何模型 (或 Ollama 未啟動)，請執行 <code>ollama pull &lt;模型名&gt;</code>'
                )
                return

            lines = ['📦 <b>本地可用模型：</b>\n']
            for m in models:
                name = html.escape(m.get('name', '未知'))
                size = m.get('size', 0)
                size_gb = size / (1024**3)
                modified = m.get('modified_at', '')[:10]
                current_mark = ' 👉' if settings.OLLAMA_MODEL in name else ''
                lines.append(f'• <code>{name}</code> ({size_gb:.1f} GB, {modified}){current_mark}')

            lines.append(f'\n目前使用：<b>{settings.OLLAMA_MODEL}</b>')
            lines.append('\n💡 切換模型：修改 .env 的 <code>OLLAMA_MODEL</code> 並重啟 Bot')

            await self.send_final_response(update, '\n'.join(lines))
        except Exception as e:
            logger.exception('查詢模型失敗')
            await self.send_error(update, f'查詢模型失敗: {html.escape(str(e))}')

    async def cmd_search(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """搜尋指令"""
        if not await self._ensure_authorized(update):
            return

        # 先檢查參數，空查詢不扣額度
        query = ' '.join(context.args) if context.args else ''
        if not query:
            await update.message.reply_text(
                '請提供搜尋關鍵字，例如：<code>/search 台灣 亞運 金牌</code>',
                parse_mode=ParseMode.HTML,
            )
            return

        quota = check_and_consume_quota(update.effective_user.id)
        if not quota['allowed']:
            await self.send_error(update, quota['message'])
            return

        await self._process_query(update, query, quota, is_search_command=True)

    async def cmd_news(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """新聞指令"""
        if not await self._ensure_authorized(update):
            return

        quota = check_and_consume_quota(update.effective_user.id)
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
        """處理使用者查詢；失敗時回覆友善訊息並退還額度"""
        user_id = update.effective_user.id
        typing = asyncio.create_task(self._keep_typing(update))
        try:
            await self._run_query(update, user_query, quota)
        except httpx.TimeoutException:
            logger.exception('Ollama 請求逾時')
            refund_quota(user_id)
            await self.send_error(
                update, f'模型回應逾時 ({settings.OLLAMA_TIMEOUT} 秒)，請稍後再試或改問較短的問題。'
            )
        except httpx.HTTPError:
            logger.exception('Ollama 連線失敗')
            refund_quota(user_id)
            await self.send_error(
                update, '無法連線到本地模型，請確認 Ollama 已啟動 (macOS：<code>open -a Ollama</code>)。'
            )
        except Exception:
            logger.exception('處理查詢失敗')
            refund_quota(user_id)
            await self.send_error(update, '處理您的問題時發生錯誤，請稍後再試。本次不計入額度。')
        finally:
            typing.cancel()
            self._status_messages.pop(update.update_id, None)

    async def _keep_typing(self, update: Update):
        """處理期間持續顯示「正在輸入…」(Telegram 每次約維持 5 秒，需定期重送)"""
        if not hasattr(update, 'get_bot'):
            return  # 模擬模式 / 測試用的假 update
        while True:
            try:
                await update.get_bot().send_chat_action(
                    chat_id=update.effective_chat.id, action=ChatAction.TYPING
                )
            except TelegramError as e:
                logger.debug(f'送出輸入中狀態失敗: {e}')
            await asyncio.sleep(4)

    async def _run_search_tool(self, func_args: dict) -> tuple[str, dict | None]:
        """執行 search_web，回傳 (給模型的內容, 搜尋紀錄)；失敗不中斷工具循環"""
        query = str(func_args.get('query', '')).strip()
        if not query:
            return '錯誤：search_web 需要 query 參數', None
        logger.info(f'🔧 模型呼叫搜尋: "{query}"')
        try:
            results = await search(query, settings.SEARCH_MAX_RESULTS)
        except Exception:
            logger.exception(f'搜尋失敗: {query}')
            return '（搜尋失敗，請根據既有知識回答並說明無法取得即時資料）', None
        logger.debug(f'Search results count: {len(results)}')
        if results and settings.SEARCH_FETCH_PAGES > 0:
            try:
                await enrich_results(results, query)
            except Exception:
                logger.exception('讀取網頁內文失敗，改用搜尋摘要')
        formatted = format_results(results)
        return formatted, {'query': query, 'results': results, 'formatted': formatted}

    async def _run_query(self, update: Update, user_query: str, quota: dict):
        """搜尋判斷 (router / tools) + 最終回答"""
        logger.debug(f'_process_query started: query={user_query[:50]}')
        started = time.monotonic()
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or update.effective_user.username or '匿名'

        # 發送初始狀態
        await self.send_status(update, '🤔 思考中...')

        # 取得對話歷史
        history = get_conversation_history(user_id)
        logger.debug(f'History length: {len(history)}')

        # 構建訊息
        messages = [{'role': 'system', 'content': build_system_prompt()}]
        messages.extend(history)
        messages.append({'role': 'user', 'content': user_query})
        tool_results = []

        if settings.SEARCH_DECISION == 'router':
            await self._router_search(update, history, user_query, messages, tool_results)
            reply = None
        else:
            reply = await self._tool_loop(update, messages, tool_results)

        if reply is None:
            # 依 messages (含搜尋結果) 產生最終回答，此時不再提供工具
            if tool_results:
                await self.send_status(update, '🧠 整理回答中...')
            final_response = await self.ollama_client.chat_with_tools(messages=messages, tools=None)
            reply = (final_response.get('message', {}).get('content') or '').strip()

        if not reply:
            refund_quota(user_id)
            await self.send_error(update, '模型未產生回覆，本次不計入額度。')
            return

        await self._finalize_response(
            update, user_id, user_name, user_query, reply, tool_results, quota,
            elapsed=time.monotonic() - started,
        )

    async def _router_search(
        self,
        update: Update,
        history: list[dict],
        user_query: str,
        messages: list[dict],
        tool_results: list[dict],
    ):
        """router 模式：模型先判斷要不要搜尋，需要則搜尋並把結果以工具訊息加入 messages"""
        # 帶最近 2 輪對話，讓「那明天呢？」這類追問也能判斷
        decision = await self.ollama_client.decide_search(
            history[-4:] + [{'role': 'user', 'content': user_query}]
        )
        logger.info(f'🧭 搜尋判斷: {decision}')
        if not decision['need_search']:
            return

        query = decision['query'] or user_query
        await self.send_status(update, '🔍 正在搜尋資訊...')
        content, record = await self._run_search_tool({'query': query})
        if record:
            tool_results.append(record)
        messages.append({
            'role': 'assistant',
            'content': '',
            'tool_calls': [{'function': {'name': 'search_web', 'arguments': {'query': query}}}],
        })
        messages.append({'role': 'tool', 'content': content})

    async def _tool_loop(
        self,
        update: Update,
        messages: list[dict],
        tool_results: list[dict],
    ) -> str | None:
        """
        tools 模式：原生 Function Calling 循環 (最多 3 輪)
        模型不呼叫工具時回傳其回答；達上限則回傳 None 由呼叫者產生最終回答
        """
        max_tool_rounds = 3

        for round_num in range(max_tool_rounds):
            logger.debug(f'Tool round {round_num + 1}')
            response = await self.ollama_client.chat_with_tools(
                messages=messages,
                tools=[SEARCH_TOOL],
                tool_choice='auto',
            )
            logger.debug(f'LLM response: {response}')

            message = response.get('message', {})
            tool_calls = message.get('tool_calls') or []

            if not tool_calls:
                # 沒有工具呼叫，直接回覆 (空字串交由呼叫者處理)
                return (message.get('content') or '').strip()

            await self.send_status(update, f'🔍 正在搜尋資訊 (第 {round_num + 1} 輪)...')

            # 將 assistant 的工具呼叫加入訊息
            messages.append(message)

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
                if not isinstance(func_args, dict):
                    func_args = {}

                if func_name == 'search_web':
                    content, record = await self._run_search_tool(func_args)
                    if record:
                        tool_results.append(record)
                else:
                    logger.warning(f'未知工具: {func_name}')
                    content = f'錯誤：未知工具 {func_name}'

                messages.append({
                    'role': 'tool',
                    'content': content,
                    'tool_call_id': tool_call.get('id', ''),
                })

        return None

    async def _finalize_response(
        self,
        update: Update,
        user_id: int,
        user_name: str,
        user_query: str,
        assistant_reply: str,
        tool_results: list[dict],
        quota: dict,
        elapsed: float | None = None,
    ):
        """完成回覆：加上來源、模型與耗時、額度，並儲存歷史"""

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
        timing = f'{elapsed:.0f} 秒・' if elapsed is not None else ''
        model_name = html.escape(getattr(self.ollama_client, 'model', settings.OLLAMA_MODEL))
        footer = (
            f'\n\n<i>(本地模型 {model_name}・{timing}'
            f'本日已提問: {quota["current"]}/{quota["max"]})</i>'
        )

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
        user_query = (update.message.text or '').strip()
        logger.debug(f'handle_message called: user_id={update.effective_user.id}, text={user_query[:50]}')

        if not await self._ensure_authorized(update):
            return

        if not user_query:
            return

        quota = check_and_consume_quota(update.effective_user.id)
        if not quota['allowed']:
            await self.send_error(update, quota['message'])
            return

        await self._process_query(update, user_query, quota)

    async def on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """全域錯誤處理：記錄堆疊，盡量回覆使用者"""
        logger.error('未處理的例外', exc_info=context.error)
        if isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text('❌ 發生未預期的錯誤，請稍後再試。')
            except TelegramError:
                pass


# 全域處理器實例
bot_handler = BotHandler()


async def setup_bot() -> Application:
    """建立並設定 Telegram Bot Application"""
    # 初始化 Ollama
    await init_ollama()

    # 建立 Application (concurrent_updates：多用戶同時提問不互相排隊)
    application = (
        Application.builder()
        .token(settings.TELEGRAM_BOT_TOKEN)
        .concurrent_updates(True)
        .build()
    )

    # 註冊指令
    logger.debug('Registering handlers...')
    application.add_handler(CommandHandler('start', bot_handler.cmd_start))
    application.add_handler(CommandHandler('help', bot_handler.cmd_help))
    application.add_handler(CommandHandler('status', bot_handler.cmd_status))
    application.add_handler(CommandHandler('reset', bot_handler.cmd_reset))
    application.add_handler(CommandHandler('models', bot_handler.cmd_models))
    application.add_handler(CommandHandler('search', bot_handler.cmd_search))
    application.add_handler(CommandHandler('news', bot_handler.cmd_news))

    # 註冊一般訊息處理
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_handler.handle_message))

    # 全域錯誤處理
    application.add_error_handler(bot_handler.on_error)

    logger.debug('Handlers registered successfully')

    return application
