#!/usr/bin/env python3
"""
設定檔測試
"""
import sys
import os
sys.path.insert(0, '/Users/limchinkun/Desktop/wk06_bot_local')

from config.settings import settings, Settings


def test_settings_loading():
    """測試設定載入"""
    print("=== 測試設定載入 ===")
    assert settings.TELEGRAM_BOT_TOKEN != ''
    assert len(settings.ALLOWED_USER_IDS) > 0
    assert settings.OLLAMA_MODEL == 'llama3.1'
    assert settings.SEARCH_ENGINE == 'duckduckgo'
    assert settings.MAX_DAILY_REQUESTS == 50
    print("✅ 所有設定正常載入")
    print(f"  模型: {settings.OLLAMA_MODEL}")
    print(f"  搜尋引擎: {settings.SEARCH_ENGINE}")
    print(f"  白名單用戶: {len(settings.ALLOWED_USER_IDS)} 位")


def test_validation():
    """測試驗證"""
    print("\n=== 測試驗證 ===")
    errors = settings.validate()
    assert len(errors) == 0, f"驗證失敗: {errors}"
    print("✅ 驗證通過")


def test_directories():
    """測試目錄建立"""
    print("\n=== 測試目錄建立 ===")
    dirs = [
        settings.CACHE_DIR,
        settings.QUOTA_DIR,
    ]
    for d in dirs:
        assert d.exists(), f"目錄不存在: {d}"
        assert d.is_dir(), f"不是目錄: {d}"
    print("✅ 所有目錄存在")


def main():
    test_settings_loading()
    test_validation()
    test_directories()
    print("\n🎉 所有設定測試通過！")


if __name__ == '__main__':
    main()