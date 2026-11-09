# 第3回 解答

## 演習

- 今回は宿題の「実装」に取り組んだ。演習の素のLLMとの比較と `make_quiz` の追加は未実施。
- 第1回（素のLLM）とエージェントの回答の違い：実APIでの比較は未実施。実行環境に `GEMINI_API_KEY` が設定されていないため、回答の違いは観測していない。
- ツール呼び出しと `requests`：宿題での TestModel による結果を以下に記載した。実LLMの結果とは区別する。

## 宿題

- 取り組んだレベル：**実装**

### やったこと

`app/tools.py` に `save_learning_log(lecture: int, content: str) -> str` を追加した。利用者から学習内容の保存を頼まれたときに使うツールで、講義回・学習内容・保存日時（UTC）を `learning_log/` 内のJSONファイルに保存する。docstring には、使う場面・引数・事前承認が必要なことを書いた。

保存先はプログラム側で固定し、日時とUUIDからファイル名を作る。排他的な新規作成モード（`"x"`）を使って既存ログの上書きを防ぐ。講義回が1未満、または内容が空白だけの場合は保存しない。個人の学習ログは既存の `.gitignore` の対象なので、提出ファイルには含めない。

`app/agent.py` では以下の処理を追加した。

1. `output_type=[str, DeferredToolRequests]` を指定する。
2. `agent.tool_plain(tools.save_learning_log, requires_approval=True)` で登録する。
3. `DeferredToolRequests` が返ったら、CLIでツール名・保存内容・保存先を表示し、`[y/N]` で確認する。
4. `y` / `yes` のときだけ承認する。拒否、空入力、EOF、Ctrl+C はすべて拒否として扱う。
5. ツール呼び出しIDと判断の対応を `DeferredToolResults.approvals` に入れ、`message_history` と一緒に渡して実行を再開する。

保存は利用者から頼まれた場合に限ること、拒否された保存を再試行しないことも `INSTRUCTIONS` に加えた。ただし、保存前に止める処理は指示文だけに任せず、`requires_approval=True` で実現した。承認前後で同じ `RunUsage` を渡し、`--trace` の利用回数を通算する。

### 結果

Python 3.12.16、`uv.lock` の固定依存関係（pydantic-ai-slim 2.57.0）で検証した。テストでは実モデルのリクエストを禁止し、APIキーなしで実行した。

```text
$ .venv/bin/python -m pytest -q
24 passed
```

追加した `tests/test_learning_log.py` の13件と、既存の11件がすべて成功した。確認した主な動作は以下のとおり。

| 条件 | 結果 |
|---|---|
| 保存ツールが要求され、承認待ちになった時点 | `DeferredToolRequests` が返り、保存先ディレクトリも未作成 |
| 承認して履歴とともに再開 | JSONファイルを1件作成し、引数どおりの講義回・内容と保存日時を確認 |
| 拒否して再開 | ファイルを作成せず、モデル側に拒否の結果が返る |
| CLIで `y` / `YES` を入力 | 確認前には保存せず、確認後に1件保存 |
| CLIで `n` / 空入力 / EOF / Ctrl+C | 保存しない |
| 講義回が不正、または内容が空白だけ | 保存しない |
| 日本語の内容を連続して2件保存 | 内容が正しく読み戻せ、2件とも残る |
| `--list-tools` 相当のツール一覧表示 | 保存ツールの説明を表示し、ログを作成しない |

APIキーなしで承認・拒否のトレースを再現できるデモも追加した。

```bash
uv run python -m scripts.demo_learning_log
```

デモは `TestModel(call_tools=["save_learning_log"], seed=3)` を使う。TestModel は質問の意味を解釈せず、引数を生成するため、今回の引数は `lecture=3, content="d"` となった。確認への入力もデモ内で模擬している。ログは一時ディレクトリに作り、デモ終了時に削除する。

承認した場合の実行結果の抜粋（保存パスは省略）：

```text
承認前の保存先の有無: False
この内容を保存しますか？ [y/N]: y
保存を承認しました。
[tool call]   save_learning_log({'lecture': 3, 'content': 'd'})
[tool return] save_learning_log -> 学習ログを保存しました: ...
[usage] RunUsage(input_tokens=105, output_tokens=20, requests=2, tool_calls=1)
保存ファイル数: 1
保存された講義回: 3, 内容: 'd'
```

拒否した場合の実行結果の抜粋：

```text
承認前の保存先の有無: False
この内容を保存しますか？ [y/N]: n
保存を拒否しました。
[tool call]   save_learning_log({'lecture': 3, 'content': 'd'})
[tool return] save_learning_log -> The tool call was denied.…
[usage] RunUsage(input_tokens=108, output_tokens=22, requests=2)
保存ファイル数: 0
```

どちらもモデルへの要求は通算2回だった。拒否した場合も「ツールの呼び出し要求」は履歴に残るが、ツール本体は実行されず、`tool_calls` は0（表示では省略）だった。この `requests` とトークン数は TestModel の模擬値であり、実LLMの呼び出し回数や課金を測ったものではない。

### 気づき・疑問

- 「保存前に確認する」とプロンプトへ書くだけでなく、実行側が承認待ちで止まる仕組みを持つことが大切だと分かった。
- `DeferredToolRequests` が返っても保存はまだ完了していない。承認結果と会話履歴を渡して初めて、承認済みのツールが実行される。
- `[tool call]` の有無だけでは実際に保存されたかを判断できない。拒否時の戻り値と、ファイルが存在しないことも合わせて確認する必要がある。
- TestModel では承認処理とファイル操作を検証できた。一方、Geminiが日本語の保存依頼から適切な内容を抽出するか、拒否後に再要求しないかは実APIでは未検証。

実APIで動かす場合のコマンド（今回は未実行）：

```bash
uv run python -m app.agent --trace "第3回の学習内容として『承認待ちでは保存処理は実行されない』と保存して"
```

参考：[Pydantic AI公式ドキュメント: Human-in-the-Loop Tool Approval](https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools/#human-in-the-loop-tool-approval)
