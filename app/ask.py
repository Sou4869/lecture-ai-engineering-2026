"""第1回: LLMへの単発質問と、履歴を保つ会話を試すスクリプト。

使い方:
    uv run python -m app.ask "LoRAとは何ですか？"
    uv run python -m app.ask            # 質問を省略すると、講座に固有の質問をする
    uv run python -m app.ask --chat     # /exit まで会話を続ける

単発質問はツールも会話履歴も持たない「素の」呼び出し。
講座に固有のことを聞くと、「分からない」と答えるか、一般論でもっともらしく答える
（講座の実際とは違う）ことを確かめよう。
（第3回で、用語集を検索できるエージェントにして改善する）
"""

import argparse
import time

from google import genai
from google.genai import errors, types

from app.config import MODEL, api_error_message, get_api_key

# 講座に固有の質問。正しい答えは data/glossary.json の homework-levels にある
DEFAULT_QUESTION = "AIE2026の講座の宿題にある「3レベル」とは何ですか？"


def ask(question: str) -> str:
    client = genai.Client(api_key=get_api_key())
    start = time.perf_counter()
    response = client.models.generate_content(model=MODEL, contents=question)
    elapsed = time.perf_counter() - start
    show_metrics(response, elapsed)
    return response.text or ""


def show_metrics(response: types.GenerateContentResponse, elapsed: float) -> None:
    """API応答の経過時間と入力・出力トークン数を表示する。"""
    print(f"[応答時間] {elapsed:.2f}秒")
    usage = response.usage_metadata
    if usage is not None:
        print(
            f"[トークン] 入力: {usage.prompt_token_count} / "
            f"出力: {usage.candidates_token_count}"
        )


def chat_loop() -> None:
    """同じチャットセッションに質問を送り、会話履歴を保持する。"""
    client = genai.Client(api_key=get_api_key())
    chat = client.chats.create(model=MODEL)
    print("質問を入力してください。終了は /exit")

    while True:
        try:
            question = input("質問> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if question == "/exit":
            break
        if not question:
            continue

        start = time.perf_counter()
        try:
            response = chat.send_message(question)
        except errors.APIError as e:
            print(api_error_message(e.code, e.message))
            continue
        elapsed = time.perf_counter() - start
        print(response.text or "")
        show_metrics(response, elapsed)


def main() -> None:
    parser = argparse.ArgumentParser(description="素のLLMに質問する")
    parser.add_argument("question", nargs="?", default=DEFAULT_QUESTION)
    parser.add_argument("--chat", action="store_true", help="会話履歴を保って連続質問する")
    args = parser.parse_args()

    print(f"[model] {MODEL}")
    if args.chat:
        chat_loop()
        return

    print(f"[質問] {args.question}\n")
    try:
        print(ask(args.question))
    except errors.APIError as e:
        print(api_error_message(e.code, e.message))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
