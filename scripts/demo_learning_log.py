"""APIキー不要の承認・拒否デモ。

実行: uv run python -m scripts.demo_learning_log
TestModel のダミー引数を使う。ログは一時ディレクトリに作り、終了時に削除する。
"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pydantic_ai.models.test import TestModel

from app import tools
from app.agent import agent, print_trace, run_with_approval


def main() -> None:
    for answer in ("y", "n"):
        print(f"\n=== TestModel: {'承認' if answer == 'y' else '拒否'} ===")
        with TemporaryDirectory(prefix="aie03-demo-") as directory:
            log_dir = Path(directory) / "learning_log"

            def respond(prompt):
                print(f"承認前の保存先の有無: {log_dir.exists()}")
                assert not log_dir.exists()
                print(f"{prompt}{answer}")
                return answer

            with (
                patch.object(tools, "LEARNING_LOG_DIR", log_dir),
                patch("builtins.input", respond),
                patch("pydantic_ai.models.ALLOW_MODEL_REQUESTS", False),
            ):
                result = run_with_approval(
                    agent,
                    "第3回の学習内容を保存して",
                    TestModel(call_tools=["save_learning_log"], seed=3),
                )
            print(result.output)
            print_trace(result)
            files = list(log_dir.glob("*.json"))
            print(f"保存ファイル数: {len(files)}")
            assert len(files) == (1 if answer == "y" else 0)
            for path in files:
                record = json.loads(path.read_text(encoding="utf-8"))
                print(f"保存された講義回: {record['lecture']}, 内容: {record['content']!r}")


if __name__ == "__main__":
    main()
