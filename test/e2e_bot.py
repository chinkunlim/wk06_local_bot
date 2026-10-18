#!/usr/bin/env python3
"""
端對端輸出測試 - 不經 Telegram，直接跑 Bot 的真實處理流程 (Ollama + 搜尋)

用法:
  uv run python test/e2e_bot.py                       # 執行內建測試題
  uv run python test/e2e_bot.py "問題一" "問題二"       # 自訂問題 (依序、共用對話歷史)
  uv run python test/e2e_bot.py --model gemma4 --decision tools
  uv run python test/e2e_bot.py --report logs/e2e.md  # 指定報告位置

需求: Ollama 已啟動 (open -a Ollama)、可連網搜尋。
不會寫入 data/ 的對話歷史、配額、互動日誌。
"""
import argparse
import asyncio
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@dataclass
class Case:
    question: str
    expect_search: bool | None = None  # None = 不檢查
    must_contain: list[str] = field(default_factory=list)
    new_session: bool = True  # False = 延續上一題的對話歷史 (測追問)


# 內建測試題
DEFAULT_CASES = [
    Case('比較 5 < 10 & 3 > 2，並寫一段 Python 範例', expect_search=False, must_contain=['<pre><code>']),
    Case('你好，簡單自我介紹', expect_search=False),
    Case('123 * 456 等於多少？', expect_search=False, must_contain=['56088']),
    Case('把「今天天氣很好」翻譯成英文', expect_search=False, must_contain=['weather']),
    Case('光合作用的原理是什麼？', expect_search=False),
    Case('台灣今天天氣如何？', expect_search=True),
    Case('那台北明天呢？', expect_search=True, new_session=False),
    Case('最近有什麼重大科技新聞？', expect_search=True),
    # 地方資訊：小模型憑記憶容易張冠李戴，應搜尋
    Case('介紹花蓮的5個景點', expect_search=True, must_contain=['花蓮']),
    # 特定人物的具體資料：需搜尋並讀取網頁內文才能完整列出 (同名同姓需依單位辨識)
    Case(
        '幫我查找東華大學，通識中心，同時也是資訊工程的陳文盛老師的課。有哪些。',
        expect_search=True,
        # 未指定學期時，列出目前學期 (課程入口網頁) 或老師頁的課程皆屬合理，只檢查核心課程
        must_contain=['人工智慧概論'],
    ),
    # 指定學期：課程入口網頁的開課清單需完整讀到，且不混入其他學期的課
    Case(
        '幫我查找東華大學，通識中心，同時也是資訊工程的陳文盛老師，在115-1有哪些課。',
        expect_search=True,
        must_contain=['人工智慧概論', '資訊科技與應用', '創客入門', 'AIoT', '和AI一起寫程式', 'AI未來應用與趨勢探索'],
    ),
]

# 不應出現在回答中的字樣 (照抄搜尋結果、自行列來源)
FORBIDDEN = ['我選擇結果', '我會選擇', '資料來源：', '參考來源：']

TELEGRAM_TAGS = {'b', 'strong', 'i', 'em', 'u', 'ins', 's', 'strike', 'del',
                 'code', 'pre', 'a', 'tg-spoiler', 'blockquote', 'span'}


class _TagChecker(HTMLParser):
    """檢查是否只用 Telegram 支援的標籤且正確閉合"""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.stack: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in TELEGRAM_TAGS:
            self.errors.append(f'不支援的標籤 <{tag}>')
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f'標籤未正確閉合 </{tag}>')
            if tag in self.stack:
                while self.stack and self.stack.pop() != tag:
                    pass
        else:
            self.stack.pop()

    def handle_entityref(self, name):
        if name not in ('lt', 'gt', 'amp', 'quot'):
            self.errors.append(f'Telegram 不支援的實體 &{name};')


def _normalize(text: str) -> str:
    """比對預期內容時忽略大小寫、空白、千分位與連字號/括號寫法差異"""
    return re.sub(r'[\s,\-－–—()（）:：]', '', text).lower()


def check_html(text: str) -> list[str]:
    checker = _TagChecker()
    checker.feed(text)
    checker.close()
    errors = checker.errors
    if checker.stack:
        errors.append(f'未閉合標籤: {checker.stack}')
    return errors


@dataclass
class Result:
    case: Case
    seconds: float = 0.0
    searches: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    output: str = ''
    chunks: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.errors


def patch_environment(handler_mod) -> list[dict]:
    """把歷史/配額/日誌換成記憶體版，避免污染 data/"""
    history: list[dict] = []
    handler_mod.get_conversation_history = lambda uid: list(history)
    handler_mod.save_conversation_turn = lambda uid, q, a: history.extend(
        [{'role': 'user', 'content': q}, {'role': 'assistant', 'content': a}]
    )
    handler_mod.log_interaction = lambda **kwargs: None
    handler_mod.refund_quota = lambda uid: None
    return history


async def run_case(bh, handler_mod, case: Case, index: int) -> Result:
    result = Result(case=case)
    finals: list[str] = []

    async def fake_status(update, text, parse_mode=None):
        result.statuses.append(text)

    async def fake_final(update, text, parse_mode=None):
        finals.append(text)

    original_search_tool = type(bh)._run_search_tool

    async def recording_search_tool(func_args):
        result.searches.append(str(func_args.get('query', '')))
        return await original_search_tool(bh, func_args)

    bh.send_status = fake_status
    bh.send_final_response = fake_final
    bh._run_search_tool = recording_search_tool

    update = SimpleNamespace(
        update_id=index,
        effective_user=SimpleNamespace(id=1, first_name='E2E', username=None),
        effective_chat=SimpleNamespace(id=1),
    )

    start = time.time()
    await bh._process_query(update, case.question, {'current': index, 'max': 999})
    result.seconds = time.time() - start

    # ===== 檢查 =====
    if not finals:
        result.errors.append('沒有任何回覆')
        return result
    result.output = finals[-1]
    result.chunks = len(handler_mod.split_message(result.output))

    if result.output.startswith('❌'):
        result.errors.append('回覆為錯誤訊息')

    searched = bool(result.searches)
    if case.expect_search is not None and searched != case.expect_search:
        result.errors.append(f'預期{"要" if case.expect_search else "不"}搜尋，實際{"有" if searched else "沒有"}搜尋')

    if case.expect_search is False and '搜尋來源' in result.output:
        result.errors.append('不需搜尋的題目卻附上搜尋來源')

    for word in FORBIDDEN:
        if word in result.output:
            result.errors.append(f'出現禁用字樣「{word}」')

    normalized = _normalize(result.output)
    for word in case.must_contain:
        if _normalize(word) not in normalized:
            result.errors.append(f'缺少預期內容「{word}」')

    result.errors.extend(f'HTML: {e}' for e in check_html(result.output))
    return result


def write_report(path: Path, results: list[Result], meta: dict):
    lines = [
        '# Bot 端對端輸出測試報告',
        '',
        f'- 時間：{meta["time"]}',
        f'- 模型：`{meta["model"]}`，搜尋判斷：`{meta["decision"]}`，搜尋引擎：`{meta["engine"]}`',
        f'- 結果：**{sum(r.passed for r in results)}/{len(results)} 通過**，總耗時 {meta["total"]:.1f}s',
        '',
        '| # | 結果 | 問題 | 搜尋 | 耗時 |',
        '|---|---|---|---|---|',
    ]
    for i, r in enumerate(results, 1):
        search = '、'.join(r.searches) if r.searches else '—'
        lines.append(f'| {i} | {"✅" if r.passed else "❌"} | {r.case.question} | {search} | {r.seconds:.1f}s |')

    for i, r in enumerate(results, 1):
        lines += ['', f'## {i}. {r.case.question}', '']
        lines.append(f'- 狀態訊息：{" → ".join(r.statuses) or "—"}')
        lines.append(f'- Telegram 分段數：{r.chunks}')
        if r.errors:
            lines.append('- **問題：**')
            lines += [f'  - {e}' for e in r.errors]
        lines += ['', '輸出 (送往 Telegram 的 HTML)：', '', '```html', r.output, '```']

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


async def main() -> int:
    parser = argparse.ArgumentParser(description='Bot 端對端輸出測試')
    parser.add_argument('questions', nargs='*', help='自訂問題 (依序執行並共用對話歷史)')
    parser.add_argument('--model', help='覆寫 OLLAMA_MODEL')
    parser.add_argument('--decision', choices=['router', 'tools'], help='覆寫 SEARCH_DECISION')
    parser.add_argument('--report', default=str(ROOT / 'logs' / 'e2e_report.md'), help='報告輸出路徑')
    parser.add_argument('--full', action='store_true', help='終端機顯示完整回答')
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format='  [%(levelname)s] %(name)s: %(message)s')
    logging.getLogger('ddgs').setLevel(logging.ERROR)
    logging.getLogger('primp').setLevel(logging.WARNING)

    from config.settings import settings

    if args.model:
        settings.OLLAMA_MODEL = args.model
    if args.decision:
        settings.SEARCH_DECISION = args.decision

    from bot import handler as handler_mod
    from llm.ollama_client import init_ollama

    client = await init_ollama()
    client.model = settings.OLLAMA_MODEL

    if args.questions:
        cases = [Case(q, new_session=(i == 0)) for i, q in enumerate(args.questions)]
    else:
        cases = DEFAULT_CASES

    print(f'模型 {settings.OLLAMA_MODEL} | 搜尋判斷 {settings.SEARCH_DECISION} | 搜尋引擎 {settings.SEARCH_ENGINE}\n')

    history = patch_environment(handler_mod)
    bh = handler_mod.BotHandler()
    bh.ollama_client = client

    results: list[Result] = []
    t0 = time.time()
    for i, case in enumerate(cases, 1):
        if case.new_session:
            history.clear()
        print(f'[{i}/{len(cases)}] {case.question}', flush=True)
        r = await run_case(bh, handler_mod, case, i)
        results.append(r)
        search = f'搜尋「{"、".join(r.searches)}」' if r.searches else '未搜尋'
        print(f'  {"✅" if r.passed else "❌"} {r.seconds:.1f}s，{search}，{r.chunks} 段')
        for e in r.errors:
            print(f'     - {e}')
        preview = handler_mod.html_to_plain(r.output)
        preview = preview if args.full else preview[:200].replace('\n', ' ') + ('…' if len(preview) > 200 else '')
        print(f'  ↳ {preview}\n')

    total = time.time() - t0
    report = Path(args.report)
    write_report(report, results, {
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'model': settings.OLLAMA_MODEL,
        'decision': settings.SEARCH_DECISION,
        'engine': settings.SEARCH_ENGINE,
        'total': total,
    })
    await client.close()

    passed = sum(r.passed for r in results)
    print(f'{"🎉" if passed == len(results) else "⚠️"} {passed}/{len(results)} 通過，總耗時 {total:.1f}s')
    print(f'報告：{report}')
    return 0 if passed == len(results) else 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
