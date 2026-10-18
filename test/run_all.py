#!/usr/bin/env python3
"""
統一測試執行器
用法:
  python test/run_all.py          # 執行所有測試
  python test/run_all.py search   # 只執行搜尋測試
  python test/run_all.py markdown # 只執行 Markdown 測試
"""
import asyncio
import os
import subprocess
import sys

TESTS = {
    'settings': 'test_settings.py',
    'search': 'test_search.py',
    'markdown': 'test_markdown.py',
    'ollama': 'test_ollama.py',
    'conversation': 'test_conversation.py',
}


def run_test(test_name):
    """執行單一測試"""
    script = TESTS.get(test_name)
    if not script:
        print(f"❌ 未知測試: {test_name}")
        return False

    path = os.path.join(os.path.dirname(__file__), script)
    print(f"\n{'='*50}")
    print(f"執行測試: {test_name} ({script})")
    print(f"{'='*50}")

    result = subprocess.run([sys.executable, path], cwd=os.path.dirname(__file__))
    return result.returncode == 0


def run_async_test(test_name):
    """執行非同步測試"""
    script = TESTS.get(test_name)
    if not script:
        print(f"❌ 未知測試: {test_name}")
        return False

    path = os.path.join(os.path.dirname(__file__), script)
    print(f"\n{'='*50}")
    print(f"執行測試: {test_name} ({script})")
    print(f"{'='*50}")

    result = subprocess.run([sys.executable, path], cwd=os.path.dirname(__file__))
    return result.returncode == 0


async def main():
    args = sys.argv[1:] if len(sys.argv) > 1 else list(TESTS.keys())

    # 非同步測試
    async_tests = ['search', 'ollama']
    # 同步測試
    sync_tests = ['settings', 'markdown', 'conversation']

    all_passed = True

    # 執行同步測試
    for test in args:
        if test in sync_tests:
            if not run_test(test):
                all_passed = False

    # 執行非同步測試
    for test in args:
        if test in async_tests:
            if not run_async_test(test):
                all_passed = False

    print(f"\n{'='*50}")
    if all_passed:
        print("🎉 所有測試通過！")
    else:
        print("❌ 部分測試失敗")
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
