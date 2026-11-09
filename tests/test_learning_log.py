"""第3回宿題: TestModel で承認前・承認後・拒否時のファイルを確認する。"""

import json
import sys

import pytest
from pydantic_ai import DeferredToolRequests, DeferredToolResults
from pydantic_ai.messages import ToolReturnPart
from pydantic_ai.models.test import TestModel

from app import agent as agent_module, tools


@pytest.fixture(autouse=True)
def log_dir(tmp_path, monkeypatch):
    path = tmp_path / "learning_log"
    monkeypatch.setattr(tools, "LEARNING_LOG_DIR", path)
    monkeypatch.setattr("pydantic_ai.models.ALLOW_MODEL_REQUESTS", False)
    return path


def log_model():
    # seed=3 で正の講義回と空ではない内容を生成する。質問の意味は解釈しない。
    return TestModel(call_tools=["save_learning_log"], seed=3)


@pytest.mark.parametrize("approved", [True, False])
def test_save_waits_for_approval_and_resumes(log_dir, approved):
    model = log_model()
    paused = agent_module.agent.run_sync("学習内容を保存して", model=model)
    assert isinstance(paused.output, DeferredToolRequests)
    assert not log_dir.exists()  # 承認待ちではディレクトリも作らない
    calls = paused.output.approvals
    assert len(calls) == 1
    call = calls[0]
    assert call.tool_name == "save_learning_log"
    args = call.args_as_dict()

    result = agent_module.agent.run_sync(
        message_history=paused.all_messages(),
        deferred_tool_results=DeferredToolResults(approvals={call.tool_call_id: approved}),
        model=model,
    )
    assert isinstance(result.output, str)
    returned = [
        part for message in result.all_messages() for part in message.parts
        if isinstance(part, ToolReturnPart) and part.tool_name == "save_learning_log"
    ]
    assert len(returned) == 1
    if approved:
        files = list(log_dir.glob("*.json"))
        assert len(files) == 1
        record = json.loads(files[0].read_text(encoding="utf-8"))
        assert record["lecture"] == args["lecture"]
        assert record["content"] == args["content"]
        assert record["created_at"]
        assert "保存しました" in str(returned[0].content)
    else:
        assert not log_dir.exists()
        assert "denied" in str(returned[0].content).lower()


@pytest.mark.parametrize("answer,approved", [("y", True), (" YES ", True), ("n", False), ("", False)])
def test_cli_confirms_before_writing(log_dir, monkeypatch, capsys, answer, approved):
    def respond(prompt):
        assert not log_dir.exists()
        display = capsys.readouterr().out
        assert "save_learning_log" in display
        assert '"content"' in display and '"lecture"' in display
        assert str(log_dir) in display
        return answer

    monkeypatch.setattr("builtins.input", respond)
    monkeypatch.setattr(agent_module, "build_model", log_model)
    monkeypatch.setattr(sys, "argv", ["app.agent", "--trace", "学習内容を保存して"])
    agent_module.main()
    output = capsys.readouterr().out
    assert "[tool call]" in output and "[usage]" in output
    assert len(list(log_dir.glob("*.json"))) == int(approved)


@pytest.mark.parametrize("error", [EOFError, KeyboardInterrupt])
def test_interrupted_confirmation_denies_save(log_dir, monkeypatch, error):
    def interrupt(prompt):
        raise error

    monkeypatch.setattr("builtins.input", interrupt)
    result = agent_module.run_with_approval(agent_module.agent, "保存して", log_model())
    assert isinstance(result.output, str)
    assert not log_dir.exists()


@pytest.mark.parametrize("lecture,content", [(0, "内容"), (-1, "内容"), (3, " \n ")])
def test_invalid_log_is_not_written(log_dir, lecture, content):
    assert "保存できません" in tools.save_learning_log(lecture, content)
    assert not log_dir.exists()


def test_logs_preserve_japanese_and_do_not_overwrite(log_dir):
    contents = ["LoRAとQLoRAの違いを学んだ。", "承認前にはツールが実行されない。"]
    for content in contents:
        tools.save_learning_log(3, content)
    records = [json.loads(p.read_text(encoding="utf-8")) for p in log_dir.glob("*.json")]
    assert len(records) == 2
    assert {r["content"] for r in records} == set(contents)


def test_listing_tools_does_not_write_logs(log_dir, capsys):
    agent_module.print_tools(agent_module.agent)
    assert "[save_learning_log]" in capsys.readouterr().out
    assert not log_dir.exists()
