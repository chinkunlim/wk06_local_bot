"""
對話歷史、配額、授權管理
使用本地檔案儲存 (JSON)，不依賴 Google Sheets / CacheService
"""
import json
import os
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Optional, Any
from threading import Lock
import logging

from config.settings import settings

logger = logging.getLogger(__name__)

# 確保資料目錄存在
settings.CACHE_DIR.mkdir(parents=True, exist_ok=True)
settings.QUOTA_DIR.mkdir(parents=True, exist_ok=True)

# 檔案路徑
HISTORY_DIR = settings.CACHE_DIR / 'history'
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

QUOTA_FILE = settings.QUOTA_DIR / 'quota.json'

# 執行緒鎖
_history_locks: Dict[str, Lock] = {}
_quota_lock = Lock()


def _get_history_lock(user_id: str) -> Lock:
    if user_id not in _history_locks:
        _history_locks[user_id] = Lock()
    return _history_locks[user_id]


def _get_history_file(user_id: str) -> Path:
    return HISTORY_DIR / f'{user_id}.json'


def is_user_authorized(user_id: int) -> bool:
    """檢查使用者是否在白名單內"""
    return user_id in settings.ALLOWED_USER_IDS


def get_conversation_history(user_id: int) -> List[Dict[str, str]]:
    """
    取得使用者對話歷史
    回傳格式: [{'role': 'user', 'content': '...'}, {'role': 'assistant', 'content': '...'}, ...]
    """
    lock = _get_history_lock(str(user_id))
    with lock:
        history_file = _get_history_file(str(user_id))
        if not history_file.exists():
            return []
        
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 過濾空內容
            valid = []
            for turn in data:
                if (turn.get('user', '').strip() and 
                    turn.get('assistant', '').strip()):
                    valid.append({'role': 'user', 'content': turn['user']})
                    valid.append({'role': 'assistant', 'content': turn['assistant']})
            
            # 只保留最近 N 輪 (每輪 = user + assistant)
            max_messages = settings.MAX_HISTORY_TURNS * 2
            return valid[-max_messages:] if len(valid) > max_messages else valid
            
        except Exception as e:
            logger.error(f'讀取對話歷史失敗 (user_id={user_id}): {e}')
            return []


def save_conversation_turn(user_id: int, user_msg: str, assistant_msg: str):
    """儲存一輪對話"""
    if not user_msg.strip() or not assistant_msg.strip():
        return
    
    lock = _get_history_lock(str(user_id))
    with lock:
        history_file = _get_history_file(str(user_id))
        history = []
        
        if history_file.exists():
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except Exception:
                history = []
        
        history.append({
            'user': user_msg,
            'assistant': assistant_msg,
            'timestamp': datetime.now().isoformat(),
        })
        
        # 限制歷史長度
        max_turns = settings.MAX_HISTORY_TURNS
        if len(history) > max_turns:
            history = history[-max_turns:]
        
        try:
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f'儲存對話歷史失敗 (user_id={user_id}): {e}')


def clear_conversation_history(user_id: int):
    """清除使用者對話歷史"""
    lock = _get_history_lock(str(user_id))
    with lock:
        history_file = _get_history_file(str(user_id))
        if history_file.exists():
            try:
                history_file.unlink()
                logger.info(f'已清除使用者 {user_id} 的對話歷史')
            except Exception as e:
                logger.error(f'清除對話歷史失敗: {e}')


def get_today_date_str() -> str:
    """取得今天日期字串 (YYYY-MM-DD)"""
    return date.today().isoformat()


def load_quota_data() -> Dict:
    """載入配額資料 (不加鎖，由呼叫者控制)"""
    if not QUOTA_FILE.exists():
        return {}
    try:
        with open(QUOTA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_quota_data(data: Dict):
    """儲存配額資料 (不加鎖，由呼叫者控制)"""
    try:
        with open(QUOTA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f'儲存配額失敗: {e}')


def check_and_consume_quota(user_id: int) -> Dict[str, Any]:
    """
    檢查並消耗配額
    回傳: {'allowed': bool, 'current': int, 'remaining': int, 'max': int, 'message': str}
    """
    today = get_today_date_str()
    quota_key = f'{today}_{user_id}'
    
    with _quota_lock:
        data = load_quota_data()
        current = data.get(quota_key, 0)
        max_limit = settings.MAX_DAILY_REQUESTS
        
        if current >= max_limit:
            return {
                'allowed': False,
                'current': current,
                'remaining': 0,
                'max': max_limit,
                'message': f'⚠️ 今日免費提問次數已達上限 ({max_limit}/{max_limit} 次)。額度將於明天自動重置！'
            }
        
        new_count = current + 1
        data[quota_key] = new_count
        save_quota_data(data)
        
        return {
            'allowed': True,
            'current': new_count,
            'remaining': max(0, max_limit - new_count),
            'max': max_limit,
        }


def get_quota_status(user_id: int) -> Dict[str, Any]:
    """查詢配額狀態 (不消耗)"""
    today = get_today_date_str()
    quota_key = f'{today}_{user_id}'
    
    data = load_quota_data()
    current = data.get(quota_key, 0)
    max_limit = settings.MAX_DAILY_REQUESTS
    
    return {
        'date': today,
        'current': current,
        'remaining': max(0, max_limit - current),
        'max': max_limit,
    }


def reset_user_quota(user_id: int):
    """重置特定使用者今日配額 (除錯用)"""
    today = get_today_date_str()
    quota_key = f'{today}_{user_id}'
    
    with _quota_lock:
        data = load_quota_data()
        if quota_key in data:
            del data[quota_key]
            save_quota_data(data)
            logger.info(f'已重置使用者 {user_id} 的今日配額')


def log_interaction(
    user_id: int,
    user_name: str,
    prompt: str,
    response: str,
    tokens: Dict[str, int] = None,
    daily_count: int = 0,
):
    """記錄互動到日誌檔案 (類似 Google Sheets)"""
    log_dir = Path(__file__).parent.parent / 'data' / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = log_dir / f'interactions_{get_today_date_str()}.jsonl'
    
    record = {
        'timestamp': datetime.now().isoformat(),
        'user_id': user_id,
        'user_name': user_name,
        'prompt': prompt,
        'response': response[:500] + '...' if len(response) > 500 else response,  # 避免日誌過大
        'tokens': tokens or {},
        'daily_count': daily_count,
    }
    
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
    except Exception as e:
        logger.error(f'寫入互動日誌失敗: {e}')