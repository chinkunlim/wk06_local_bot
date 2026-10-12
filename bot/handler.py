"""
Telegram Bot 主處理器 - 整合對話、搜尋、LLM 呼叫
"""
import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from telegram import Update, Message
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.constants import ParseMode

from config.settings import settings
from bot.conversation import (
    is_user_authorized,
    get_conversation_history,
    save_conversation_turn,
    clear_conversation_history,
    check_and_consume_quota,
    get_quota_status,
    log_interaction,
)
from llm.ollama_client import (
    get_ollama_client,
    init_ollama,
    SYSTEM_PROMPT,
    SEARCH_TOOL,
)
from search import search, format_results

logger = logging.getLogger(__name__)


class BotHandler:
    """Telegram Bot 核心處理邏輯"""
    
    def __init__(self):
        self.ollama_client = get_ollama_client()
        self._status_messages: Dict[int, int] = {}  # chat_id -> message_id
    
    async def send_status(
        self,
        update: Update,
        text: str,
        parse_mode: ParseMode = ParseMode.HTML,
    ) -> Optional[Message]:
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
    ) -> Optional[Message]:
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
        user = update.effective_user
        welcome = (
            f'👋 <b>歡迎使用本地 AI 助理！</b>\n\n'
            f'你好，{user.first_name}！我是運行在本地的開源模型助理。\n\n'
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
            f'📖 <b>本地 AI 助理使用說明</b>\n\n'
            f'• <b>一般提問</b>：直接輸入問題，我會根據上下文回答\n'
            f'• <b>自動搜尋</b>：詢問含「最新、新聞、即時、今天」等關鍵字時，我會自動搜尋網路\n'
            f'• <b>/search <code>關鍵字</code></b>：主動搜尋特定主題\n'
            f'• <b>/news</b>：瀏覽最新新聞頭條\n'
            f'• <b>/status</b>：查看今日已用/剩餘額度\n'
            f'• <b>/reset</b>：清除對話記憶，開啟新話題\n'
            f'• <b>/models</b>：查看本地 Ollama 可用模型\n'
            f'• <b>/help</b>：顯示本說明'
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
            await self.send_error(update, f'查詢模型失敗: {e}')
    
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
        quota: Dict,
        is_search_command: bool = False,
    ):
        """處理使用者查詢 (含工具呼叫循環)"""
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or update.effective_user.username or '匿名'
        
        # 發送初始狀態
        await self.send_status(update, '🤔 思考中...')
        
        # 取得對話歷史
        history = get_conversation_history(user_id)
        
        # 構建訊息
        messages = [{'role': 'system', 'content': SYSTEM_PROMPT}]
        messages.extend(history)
        messages.append({'role': 'user', 'content': user_query})
        
        # 工具呼叫循環 (最多 3 輪)
        max_tool_rounds = 3
        tool_results = []
        
        for round_num in range(max_tool_rounds):
            # 呼叫 LLM
            response = await self.ollama_client.chat_with_tools(
                messages=messages,
                tools=[SEARCH_TOOL],
                tool_choice='auto',
            )
            
            message = response.get('message', {})
            tool_calls = message.get('tool_calls', [])
            
            if not tool_calls:
                # 沒有工具呼叫，直接回覆
                assistant_reply = message.get('content', '').strip()
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
                
                if func_name == 'search_web':
                    query = func_args.get('query', '')
                    logger.info(f'🔧 模型呼叫搜尋: "{query}"')
                    
                    # 執行搜尋
                    results = await search(query, settings.SEARCH_MAX_RESULTS)
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
        tool_results: List[Dict],
        quota: Dict,
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
                        title = r.get('title', '來源')[:60]
                        sources_text += f'\n• <a href="{url}">{title}</a>'
        
        # 加上額度資訊
        footer = f'\n\n<i>(本日已提問: {quota["current"]}/{quota["max"]})</i>'
        
        final_text = assistant_reply + sources_text + footer
        
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
        user_id = update.effective_user.id
        
        # 檢查授權
        if not is_user_authorized(user_id):
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
            await self.send_error(update, quota['message'])
            return
        
        # 處理查詢
        user_query = update.message.text.strip()
        await self._process_query(update, user_query, quota)


# 全域處理器實例
bot_handler = BotHandler()


async def setup_bot() -> Application:
    """建立並設定 Telegram Bot Application"""
    # 初始化 Ollama
    await init_ollama()
    
    # 建立 Application
    application = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()
    
    # 註冊指令
    application.add_handler(CommandHandler('start', bot_handler.cmd_start))
    application.add_handler(CommandHandler('help', bot_handler.cmd_help))
    application.add_handler(CommandHandler('status', bot_handler.cmd_status))
    application.add_handler(CommandHandler('reset', bot_handler.cmd_reset))
    application.add_handler(CommandHandler('models', bot_handler.cmd_models))
    application.add_handler(CommandHandler('search', bot_handler.cmd_search))
    application.add_handler(CommandHandler('news', bot_handler.cmd_news))
    
    # 註冊一般訊息處理
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_handler.handle_message))
    
    return application