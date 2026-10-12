#!/usr/bin/env python
"""
環境檢查腳本 - 驗證所有依賴與設定是否正確
"""
import sys
import subprocess
from pathlib import Path


def check_python_version():
    """檢查 Python 版本 >= 3.9 (建議 3.10+)"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 9):
        print(f'❌ Python 版本過舊: {version.major}.{version.minor} (需 >= 3.9)')
        return False
    if version.minor < 10:
        print(f'⚠️  Python {version.major}.{version.minor}.{version.micro} (建議升級到 3.10+ 以獲得最佳相容性)')
    else:
        print(f'✅ Python {version.major}.{version.minor}.{version.micro}')
    return True


def check_dependencies():
    """檢查 Python 套件"""
    required = [
        'telegram',
        'httpx',
        'dotenv',
        'bs4',
        'lxml',
        'pydantic',
        'pydantic_settings',
    ]
    
    missing = []
    for pkg in required:
        try:
            __import__(pkg)
            print(f'✅ {pkg}')
        except ImportError:
            print(f'❌ {pkg} (未安裝)')
            missing.append(pkg)
    
    if missing:
        print(f'\n請執行: pip install {" ".join(missing)}')
        return False
    return True


def check_env_file():
    """檢查 .env 檔案"""
    env_path = Path(__file__).parent / '.env'
    if not env_path.exists():
        print('❌ .env 檔案不存在 (請複製 .env.example 為 .env)')
        return False
    
    print('✅ .env 檔案存在')
    
    # 檢查必要欄位
    from dotenv import dotenv_values
    config = dotenv_values(env_path)
    
    required_keys = ['TELEGRAM_BOT_TOKEN', 'ALLOWED_USER_IDS']
    for key in required_keys:
        if not config.get(key) or config[key].startswith('123456'):
            print(f'⚠️  {key} 未正確設定')
        else:
            print(f'✅ {key} 已設定')
    
    return True


def check_ollama():
    """檢查 Ollama 服務與模型"""
    import httpx
    
    try:
        # 檢查 Ollama 服務
        resp = httpx.get('http://localhost:11434/api/tags', timeout=5.0)
        if resp.status_code != 200:
            print('❌ Ollama 服務未運行 (請執行: ollama serve)')
            return False
        
        models = resp.json().get('models', [])
        if not models:
            print('⚠️  Ollama 運行中但無已安裝模型')
            print('   請執行: ollama pull llama3.1')
            return False
        
        print('✅ Ollama 服務運行中')
        print(f'   已安裝模型: {len(models)} 個')
        for m in models[:5]:
            name = m.get('name', '未知')
            size_gb = m.get('size', 0) / (1024**3)
            print(f'     - {name} ({size_gb:.1f} GB)')
        
        # 檢查設定的模型是否存在
        from config.settings import settings
        model_exists = any(settings.OLLAMA_MODEL in m.get('name', '') for m in models)
        if model_exists:
            print(f'✅ 設定模型 {settings.OLLAMA_MODEL} 已安裝')
        else:
            print(f'⚠️  設定模型 {settings.OLLAMA_MODEL} 未安裝')
            print(f'   請執行: ollama pull {settings.OLLAMA_MODEL}')
        
        return True
        
    except httpx.ConnectError:
        print('❌ 無法連線到 Ollama (請確認 ollama serve 已啟動)')
        return False
    except Exception as e:
        print(f'❌ Ollama 檢查失敗: {e}')
        return False


def check_data_dirs():
    """檢查資料目錄權限"""
    dirs = ['data/cache/history', 'data/quota', 'data/logs', 'logs']
    for d in dirs:
        path = Path(__file__).parent / d
        try:
            path.mkdir(parents=True, exist_ok=True)
            # 測試寫入
            test_file = path / '.write_test'
            test_file.write_text('test')
            test_file.unlink()
            print(f'✅ {d} 可寫入')
        except Exception as e:
            print(f'❌ {d} 無法寫入: {e}')
            return False
    return True


def main():
    print('=' * 50)
    print('🔍 本地 AI Telegram Bot - 環境檢查')
    print('=' * 50)
    
    checks = [
        ('Python 版本', check_python_version),
        ('Python 套件', check_dependencies),
        ('環境設定', check_env_file),
        ('資料目錄', check_data_dirs),
        ('Ollama 服務', check_ollama),
    ]
    
    all_pass = True
    for name, check_fn in checks:
        print(f'\n--- {name} ---')
        if not check_fn():
            all_pass = False
    
    print('\n' + '=' * 50)
    if all_pass:
        print('🎉 所有檢查通過！可以啟動 Bot')
        print('   執行: python -m bot.main')
    else:
        print('❌ 部分檢查失敗，請修正後再試')
    print('=' * 50)
    
    return 0 if all_pass else 1


if __name__ == '__main__':
    sys.exit(main())