#!/usr/bin/env python3
"""
啟動流程測試 (離線)：Token 執行時詢問、設定驗證、模擬模式
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import main as main_mod
from config.settings import Settings

VALID_TOKEN = '123456789:' + 'A' * 35


def test_validate_simulate_skips_telegram(monkeypatch):
    monkeypatch.setattr(Settings, 'TELEGRAM_BOT_TOKEN', '')
    monkeypatch.setattr(Settings, 'ALLOWED_USER_IDS', [])
    assert not any('TELEGRAM' in e or 'ALLOWED' in e for e in Settings.validate(require_telegram=False))
    errors = Settings.validate()
    assert any('TELEGRAM_BOT_TOKEN 未設定' in e for e in errors)


def test_validate_token_format(monkeypatch):
    monkeypatch.setattr(Settings, 'ALLOWED_USER_IDS', [1])
    monkeypatch.setattr(Settings, 'TELEGRAM_BOT_TOKEN', 'not-a-token')
    assert any('格式不對' in e for e in Settings.validate())
    monkeypatch.setattr(Settings, 'TELEGRAM_BOT_TOKEN', VALID_TOKEN)
    assert not any('TELEGRAM' in e for e in Settings.validate())


def test_prompt_missing_secrets_asks_and_keeps_in_memory(monkeypatch):
    monkeypatch.setattr(Settings, 'TELEGRAM_BOT_TOKEN', '')
    monkeypatch.setattr(Settings, 'ALLOWED_USER_IDS', [])
    monkeypatch.setattr(Settings, 'INVALID_USER_IDS', [])
    monkeypatch.setattr(main_mod.sys.stdin, 'isatty', lambda: True)
    monkeypatch.setattr(main_mod.getpass, 'getpass', lambda prompt: f'  {VALID_TOKEN}  ')
    monkeypatch.setattr('builtins.input', lambda prompt: '111, 222')

    main_mod.prompt_missing_secrets()

    assert Settings.TELEGRAM_BOT_TOKEN == VALID_TOKEN
    assert Settings.ALLOWED_USER_IDS == [111, 222]
    assert Settings.validate() == []


def test_prompt_skipped_when_configured_or_not_tty(monkeypatch):
    def fail(*a, **k):
        raise AssertionError('不應詢問')

    monkeypatch.setattr(main_mod.getpass, 'getpass', fail)
    monkeypatch.setattr('builtins.input', fail)

    # 已設定：不詢問
    monkeypatch.setattr(Settings, 'TELEGRAM_BOT_TOKEN', VALID_TOKEN)
    monkeypatch.setattr(Settings, 'ALLOWED_USER_IDS', [1])
    monkeypatch.setattr(main_mod.sys.stdin, 'isatty', lambda: True)
    main_mod.prompt_missing_secrets()

    # 非互動終端 (例如背景執行)：不詢問，交給 validate 報錯
    monkeypatch.setattr(Settings, 'TELEGRAM_BOT_TOKEN', '')
    monkeypatch.setattr(main_mod.sys.stdin, 'isatty', lambda: False)
    main_mod.prompt_missing_secrets()


def test_simulate_fake_update_has_handler_fields():
    from bot.simulate import SIM_USER_ID, _fake_update

    u = _fake_update(3)
    assert u.update_id == 3
    assert u.effective_user.id == SIM_USER_ID and u.effective_chat.id == SIM_USER_ID
    assert not hasattr(u, 'get_bot')  # 模擬模式不送「輸入中」狀態
