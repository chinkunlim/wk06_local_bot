"""
Ollama Client - 支援 Function Calling / Tool Use
"""
import asyncio
import json
import logging
from collections.abc import AsyncGenerator

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)

# Ollama API 端點
OLLAMA_API_CHAT = f'{settings.OLLAMA_BASE_URL}/api/chat'
OLLAMA_API_GENERATE = f'{settings.OLLAMA_BASE_URL}/api/generate'
OLLAMA_API_TAGS = f'{settings.OLLAMA_BASE_URL}/api/tags'

# 搜尋工具定義 (Function Calling)
SEARCH_TOOL = {
    'type': 'function',
    'function': {
        'name': 'search_web',
        'description': (
            '搜尋網路上的即時資訊。只在答案會隨時間改變、你的內建知識無法提供時使用，'
            '例如：新聞、今天/最近發生的事、天氣、股價、匯率、比賽結果。'
            '程式、數學、翻譯、寫作、概念解釋、歷史常識、閒聊等問題請直接回答，不要呼叫此工具。'
        ),
        'parameters': {
            'type': 'object',
            'properties': {
                'query': {
                    'type': 'string',
                    'description': '搜尋關鍵字，請提取核心實體名詞，避免包含「請問」、「怎麼樣」等贅詞。例如：「台灣 亞運 金牌」而非「請問台灣在亞運獲得多少金牌」',
                },
            },
            'required': ['query'],
        },
    },
}

# 系統提示詞 ({today} 由 build_system_prompt 填入)
SYSTEM_PROMPT = """你是專業、友善且樂於助人的智慧助理，請用清晰、有條理且自然的繁體中文回答 (使用者要求翻譯或指定其他語言時，依其要求輸出)。
今天日期：{today}

【何時搜尋】
預設直接用你自己的知識回答。只有在答案取決於「現在」或「最近」的資料時，才呼叫 `search_web`：
- 需要搜尋：新聞、今天/近期事件、天氣、股價、匯率、比賽結果、某人或某公司的最新動態
- 不要搜尋：寫程式、數學計算、翻譯、寫作、解釋概念或原理、歷史與常識、打招呼閒聊、比較或分析使用者提供的內容

【搜尋後如何回答】
- 搜尋結果只是參考資料，請直接回答使用者原本的問題，用自己的話整理
- 不要說「我選擇結果 1」、「根據搜尋結果」之類的話，也不要列出來源或連結 (系統會自動附上)
- 若搜尋結果與問題無關，忽略它，改用自己的知識回答並說明無法取得即時資料

【回答格式】
- 直接回應使用者的要求，例如翻譯就只給譯文，計算就給算式與結果
- 內容較多時，重點用條列式與粗體標題
- 程式碼放在 ``` 程式碼區塊中
"""


# 搜尋判斷 (router 模式)：先讓模型輸出 JSON 決定要不要搜尋，再回答
# 部分模型 (如 llama3.1) 只要帶 tools 幾乎必定呼叫工具，無法自行判斷「不需要搜尋」
ROUTER_PROMPT = """今天日期：{today}
判斷回答使用者最新的問題是否需要上網搜尋即時資訊 (可參考前文理解指代)。
需要搜尋：新聞、今天/最近發生的事、天氣、股價、匯率、比賽結果、某人或公司的最新動態。
不需要搜尋：寫程式、數學、翻譯、寫作、解釋概念、歷史常識、閒聊、分析使用者提供的內容。
只輸出 JSON：{{"need_search": true 或 false, "query": "精簡的搜尋關鍵字，不需要時為空字串"}}"""

ROUTER_SCHEMA = {
    'type': 'object',
    'properties': {
        'need_search': {'type': 'boolean'},
        'query': {'type': 'string'},
    },
    'required': ['need_search', 'query'],
}


def build_system_prompt() -> str:
    """產生含今日日期的系統提示詞 (讓模型判斷「今天」「最近」)"""
    from datetime import date

    return SYSTEM_PROMPT.format(today=date.today().isoformat())


class OllamaClient:
    """Ollama API 客戶端，支援 Function Calling"""

    def __init__(
        self,
        base_url: str = None,
        model: str = None,
        timeout: int = None,
    ):
        self.base_url = base_url or settings.OLLAMA_BASE_URL
        self.model = model or settings.OLLAMA_MODEL
        self.timeout = timeout or settings.OLLAMA_TIMEOUT
        self._client: httpx.AsyncClient | None = None
        self._client_loop: asyncio.AbstractEventLoop | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        # 連線池綁定建立時的 event loop；換 loop (如 asyncio.run / 測試) 需重建
        loop = asyncio.get_running_loop()
        if self._client is None or self._client.is_closed or self._client_loop is not loop:
            self._client_loop = loop
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def list_models(self) -> list[dict]:
        """列出本地可用模型"""
        client = await self._get_client()
        try:
            resp = await client.get(OLLAMA_API_TAGS)
            resp.raise_for_status()
            data = resp.json()
            return data.get('models', [])
        except Exception as e:
            logger.error(f'列出模型失敗: {e}')
            return []

    async def check_model_exists(self) -> bool:
        """檢查指定模型是否存在"""
        models = await self.list_models()
        return any(self.model in m.get('name', '') for m in models)

    async def pull_model(self) -> bool:
        """拉取模型 (若不存在)"""
        client = await self._get_client()
        try:
            logger.info(f'正在拉取模型: {self.model}...')
            async with client.stream(
                'POST',
                f'{self.base_url}/api/pull',
                json={'name': self.model, 'stream': True},
                timeout=httpx.Timeout(300.0),  # 拉取模型可能很久
            ) as resp:
                async for line in resp.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            if 'status' in data:
                                logger.info(f'  {data["status"]}')
                        except json.JSONDecodeError:
                            pass
            logger.info(f'✅ 模型 {self.model} 拉取完成')
            return True
        except Exception as e:
            logger.error(f'拉取模型失敗: {e}')
            return False

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict] = None,
        tool_choice: str = 'auto',
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> dict:
        """
        支援 Function Calling 的對話
        回傳: {'message': {...}, 'tool_calls': [...], 'usage': {...}}
        """
        client = await self._get_client()

        payload = {
            'model': self.model,
            'messages': messages,
            'stream': False,
            'options': {
                'temperature': temperature,
                'num_predict': max_tokens,
                'num_ctx': settings.OLLAMA_NUM_CTX,
                'top_k': 40,
                'top_p': 0.95,
            },
        }

        if tools:
            payload['tools'] = tools
            payload['tool_choice'] = tool_choice

        try:
            resp = await client.post(OLLAMA_API_CHAT, json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException:
            logger.error(f'Ollama 請求逾時 ({self.timeout}秒)')
            raise
        except httpx.HTTPStatusError as e:
            logger.error(f'Ollama HTTP 錯誤: {e.response.status_code} - {e.response.text}')
            raise
        except Exception as e:
            logger.error(f'Ollama 請求失敗: {e}')
            raise

    async def decide_search(self, conversation: list[dict]) -> dict:
        """
        讓模型判斷是否需要搜尋 (router 模式)
        conversation: 不含 system 的 user/assistant 訊息 (最後一則為使用者問題)
        回傳: {'need_search': bool, 'query': str}；解析失敗視為不搜尋
        """
        from datetime import date

        client = await self._get_client()
        payload = {
            'model': self.model,
            'messages': [
                {'role': 'system', 'content': ROUTER_PROMPT.format(today=date.today().isoformat())},
                *conversation,
            ],
            'stream': False,
            'format': ROUTER_SCHEMA,
            'options': {
                'temperature': 0,
                'num_predict': 64,
                'num_ctx': settings.OLLAMA_NUM_CTX,
            },
        }
        resp = await client.post(OLLAMA_API_CHAT, json=payload)
        resp.raise_for_status()
        content = resp.json().get('message', {}).get('content', '')
        try:
            data = json.loads(content)
            return {
                'need_search': bool(data.get('need_search')),
                'query': str(data.get('query') or '').strip(),
            }
        except (json.JSONDecodeError, AttributeError):
            logger.warning(f'搜尋判斷 JSON 解析失敗，視為不搜尋: {content!r}')
            return {'need_search': False, 'query': ''}

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] = None,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> AsyncGenerator[str, None]:
        """
        串流對話 (不支援 Function Calling，僅用於最終回答生成)
        """
        client = await self._get_client()

        payload = {
            'model': self.model,
            'messages': messages,
            'stream': True,
            'options': {
                'temperature': temperature,
                'num_predict': max_tokens,
                'num_ctx': settings.OLLAMA_NUM_CTX,
                'top_k': 40,
                'top_p': 0.95,
            },
        }

        try:
            async with client.stream('POST', OLLAMA_API_CHAT, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            if 'message' in data and 'content' in data['message']:
                                yield data['message']['content']
                            if data.get('done'):
                                break
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.error(f'Ollama 串流失敗: {e}')
            raise


# 全域單例
_ollama_client: OllamaClient | None = None


def get_ollama_client() -> OllamaClient:
    global _ollama_client
    if _ollama_client is None:
        _ollama_client = OllamaClient()
    return _ollama_client


async def init_ollama() -> OllamaClient:
    """初始化並檢查模型"""
    client = get_ollama_client()

    # 檢查模型是否存在
    exists = await client.check_model_exists()
    if not exists:
        logger.warning(f'模型 {client.model} 不存在於本地，嘗試拉取...')
        success = await client.pull_model()
        if not success:
            raise RuntimeError(f'無法取得模型 {client.model}，請手動執行: ollama pull {client.model}')

    logger.info(f'✅ Ollama 就緒: {client.model} @ {client.base_url}')
    return client
