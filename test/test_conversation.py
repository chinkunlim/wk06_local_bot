#!/usr/bin/env python3
"""
對話歷史、配額、授權測試
"""
import sys
import tempfile
import os
sys.path.insert(0, '/Users/limchinkun/Desktop/wk06_bot_local')

from bot.conversation import (
    is_user_authorized,
    get_conversation_history,
    save_conversation_turn,
    clear_conversation_history,
    check_and_consume_quota,
    get_quota_status,
    log_interaction,
    reset_user_quota,
    QUOTA_FILE,
)


def setup_test_env():
    """設定測試環境"""
    # 暫存目錄
    test_dir = tempfile.mkdtemp()
    os.environ['HOME'] = test_dir  # 影響 settings 的路徑
    return test_dir


def test_authorization():
    """測試授權檢查"""
    print("=== 測試授權檢查 ===")
    from config.settings import settings
    test_id = settings.ALLOWED_USER_IDS[0]
    assert is_user_authorized(test_id), "白名單用戶應授權"
    assert not is_user_authorized(99999999), "非白名單用戶應拒絕"
    print("✅ 授權檢查正常")


def test_conversation_history():
    """測試對話歷史"""
    print("\n=== 測試對話歷史 ===")
    user_id = 123456789
    clear_conversation_history(user_id)
    
    # 空歷史
    history = get_conversation_history(user_id)
    assert history == [], "初始應為空"
    
    # 儲存一輪
    save_conversation_turn(user_id, "你好", "你好！有什麼可以幫您？")
    history = get_conversation_history(user_id)
    assert len(history) == 2, "應有 user + assistant 兩則"
    assert history[0]['role'] == 'user'
    assert history[1]['role'] == 'assistant'
    print("✅ 基本儲存/讀取正常")
    
    # 多輪
    for i in range(3):
        save_conversation_turn(user_id, f"問題{i}", f"回答{i}")
    history = get_conversation_history(user_id)
    max_turns = 4 * 2  # MAX_HISTORY_TURNS * 2
    assert len(history) <= max_turns, "不應超過最大輪數"
    print(f"✅ 多輪歷史限制正常 (當前 {len(history)} 則，上限 {max_turns})")
    
    # 清除
    clear_conversation_history(user_id)
    assert get_conversation_history(user_id) == []
    print("✅ 清除歷史正常")


def test_quota():
    """測試配額"""
    print("\n=== 測試配額 ===")
    user_id = 987654321
    reset_user_quota(user_id)
    
    # 初始狀態
    status = get_quota_status(user_id)
    assert status['current'] == 0
    assert status['remaining'] == 50  # MAX_DAILY_REQUESTS
    
    # 消耗配額
    for i in range(3):
        result = check_and_consume_quota(user_id)
        assert result['allowed']
        assert result['current'] == i + 1
    print(f"✅ 配額消耗正常 (已用 {get_quota_status(user_id)['current']} 次)")
    
    # 重置
    reset_user_quota(user_id)
    assert get_quota_status(user_id)['current'] == 0
    print("✅ 配額重置正常")


def test_logging():
    """測試日誌記錄"""
    print("\n=== 測試日誌記錄 ===")
    log_interaction(
        user_id=111111111,
        user_name="測試用戶",
        prompt="測試問題",
        response="測試回答",
        tokens={'promptTokens': 10, 'candidatesTokens': 20, 'totalTokens': 30},
        daily_count=1
    )
    print("✅ 日誌記錄正常")


def main():
    test_authorization()
    test_conversation_history()
    test_quota()
    test_logging()
    print("\n🎉 所有對話/配額測試通過！")


if __name__ == '__main__':
    main()