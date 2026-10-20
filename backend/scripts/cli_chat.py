"""可选的命令行入口（终端调试用）。

设计意图：把 input()/print() 这类终端交互**只**放在这里。
网页端通过 FastAPI 调用同一个 chat_service，两条入口共用一套业务逻辑，
避免“网页能跑但终端逻辑不一样”的分叉。

用法（在 backend 目录下）：
    .venv\\Scripts\\python.exe -m scripts.cli_chat
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import get_session_factory, init_db  # noqa: E402
from app.services import chat_service  # noqa: E402
from app.services.knowledge_service import seed_from_directory  # noqa: E402


async def main() -> None:
    init_db()
    db = get_session_factory()()
    try:
        seed_from_directory(db)
        print("电商智能客服 · 命令行模式")
        print("输入问题后回车；输入 exit 退出；输入 new 开始新会话。\n")

        session_id: str | None = None
        while True:
            try:
                text = input("你 > ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n已退出。")
                return

            if not text:
                continue
            if text.lower() in ("exit", "quit", "q"):
                print("已退出。")
                return
            if text.lower() == "new":
                session_id = None
                print("已开启新会话。\n")
                continue

            try:
                result = await chat_service.handle_chat(db, text, session_id=session_id)
            except Exception as exc:  # noqa: BLE001
                print(f"[错误] {type(exc).__name__}: {exc}\n")
                continue

            session_id = result["session_id"]
            print(f"\n客服 > {result['answer']}")
            print(f"[意图] {result['intent']}（{result['intent_method']}）")
            if result["degraded"]:
                print(f"[降级] {result['degraded']}")
            if result["sources"]:
                print("[来源] " + "；".join(
                    f"{s['file_name']} 第{s['chunk_index'] + 1}段（{s['score']:.2f}）"
                    for s in result["sources"]
                ))
            print()
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
