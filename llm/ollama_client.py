"""
Ollama Client - 支援 Function Calling / Tool Use
"""
import json
import httpx
from typing import List, Dict, Any, Optional, AsyncGenerator
import logging

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
        'description': '搜尋網路即時資訊。當使用者詢問最新新聞、即時股價、天氣、近期事件、特定人物最新動態等需要即時資料時，必須使用此工具。',
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

# 系統提示詞
SYSTEM_PROMPT = """你是專業、友善且樂於助人的智慧助理。請以清晰、有條理且自然的繁體中文回答使用者的問題。

【可用工具】
你可以使用 `search_web` 工具搜尋即時資訊。當遇到以下情況時，**必須**主動呼叫搜尋工具：
1. 使用者詢問「最新」、「新聞」、「即時」、「今天」、「近期」等時效性關鍵字
2. 詢問即時股價、匯率、天氣、賽事比分、選舉開票等動態數據
3. 詢問特定人物/公司/產品的最新動態
4. 你的內建知識無法回答或可能已過時的問題

【工具使用原則】
- 搜尋查詢請精簡，只保留核心關鍵字 (實體名詞、事件、數字)
- 若搜尋結果不相關，可嘗試不同關鍵字再次搜尋
- 獲得搜尋結果後，請**綜合分析並用自己的話回答**，**不要**在回答中包含來源引用、連結或參考文獻格式
- 系統會自動在回答末尾附上參考來源

【回答格式】
- 使用條列式、粗體標題讓重點清晰
- 直接回答問題，不需列出「資料來源：」或「參考來源：」等字樣
- 系統會自動附上來源連結
"""


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
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._client
    
    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    async def list_models(self) -> List[Dict]:
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
        messages: List[Dict],
        tools: List[Dict] = None,
        tool_choice: str = 'auto',
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ) -> Dict:
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
    
    async def chat_stream(
        self,
        messages: List[Dict],
        tools: List[Dict] = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
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
_ollama_client: Optional[OllamaClient] = None


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