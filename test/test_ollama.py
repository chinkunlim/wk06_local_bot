#!/usr/bin/env python3
"""
Ollama Client 測試
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm.ollama_client import SEARCH_TOOL, SYSTEM_PROMPT, get_ollama_client, init_ollama


async def test_connection():
    """測試 Ollama 連線"""
    print("=== 測試 Ollama 連線 ===")
    client = await init_ollama()
    models = await client.list_models()
    assert len(models) > 0, "應該有模型"
    print(f"✅ 連線成功，可用模型: {len(models)} 個")
    for m in models:
        print(f"  - {m['name']} ({m['size'] / 1024**3:.1f} GB)")


async def test_chat_basic():
    """測試基本對話"""
    print("\n=== 測試基本對話 ===")
    client = get_ollama_client()
    response = await client.chat_with_tools(
        messages=[
            {'role': 'system', 'content': '你是助理'},
            {'role': 'user', 'content': '請用繁體中文說 hello'}
        ],
        tools=None
    )
    assert 'message' in response
    content = response['message'].get('content', '')
    assert len(content) > 0
    print(f"✅ 基本對話: {content[:100]}")


async def test_chat_with_tools():
    """測試工具呼叫"""
    print("\n=== 測試工具呼叫 ===")
    client = get_ollama_client()
    response = await client.chat_with_tools(
        messages=[
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': '台灣今天天氣如何？'}
        ],
        tools=[SEARCH_TOOL],
        tool_choice='auto'
    )
    print(f"回應: {response}")
    message = response.get('message', {})
    tool_calls = message.get('tool_calls', [])
    print(f"工具呼叫數: {len(tool_calls)}")
    if tool_calls:
        for tc in tool_calls:
            print(f"  呼叫: {tc['function']['name']}({tc['function']['arguments']})")
    else:
        print("  模型未呼叫工具 (可能直接回答)")
    print("✅ 工具呼叫測試完成")


async def test_model_exists():
    """測試模型存在性"""
    print("\n=== 測試模型存在性 ===")
    client = get_ollama_client()
    exists = await client.check_model_exists()
    assert exists, "模型應該存在"
    print(f"✅ 模型 {client.model} 存在")


async def main():
    await test_connection()
    await test_model_exists()
    await test_chat_basic()
    await test_chat_with_tools()
    print("\n🎉 所有 Ollama 測試通過！")


if __name__ == '__main__':
    asyncio.run(main())
