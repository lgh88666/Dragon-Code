from pathlib import Path

from dragon_code.hooks import HookLoader


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_loads_project_before_user_and_project_wins_duplicate(tmp_path):
    project = tmp_path / "project"
    home = tmp_path / "home"
    write(
        project / ".dragon-code/hooks.yaml",
        "hooks:\n  - name: same\n    event: Stop\n    action: {type: prompt, prompt: project}\n",
    )
    write(
        home / ".dragon-code/hooks.yaml",
        """hooks:
  - name: same
    event: Stop
    action: {type: prompt, prompt: user}
  - name: user-only
    event: SessionStart
    action: {type: prompt, prompt: hello}
""",
    )

    snapshot = HookLoader(project, user_home=home).load()
    assert [hook.name for hook in snapshot.hooks] == ["same", "user-only"]
    assert snapshot.hooks[0].source == "project"
    assert len(snapshot.issues) == 1


def test_invalid_entries_are_skipped_without_losing_valid_hook(tmp_path):
    project = tmp_path / "project"
    write(
        project / ".dragon-code/hooks.yaml",
        """hooks:
  - name: bad-event
    event: Unknown
    action: {type: prompt, prompt: x}
  - name: bad-regex
    event: Stop
    if: 'text =~ /[/'
    action: {type: prompt, prompt: x}
  - name: good
    event: Stop
    action: {type: prompt, prompt: ok}
""",
    )
    snapshot = HookLoader(project, user_home=tmp_path / "home").load()
    assert [hook.name for hook in snapshot.hooks] == ["good"]
    assert len(snapshot.issues) == 2


def test_blocking_event_cannot_be_async(tmp_path):
    project = tmp_path / "project"
    write(
        project / ".dragon-code/hooks.yaml",
        """hooks:
  - name: invalid
    event: PreToolUse
    async: true
    action: {type: shell, command: echo ok}
""",
    )
    snapshot = HookLoader(project, user_home=tmp_path / "home").load()
    assert not snapshot.hooks
    assert "不允许" in snapshot.issues[0].message


def test_empty_config_is_valid(tmp_path):
    snapshot = HookLoader(tmp_path / "project", user_home=tmp_path / "home").load()
    assert snapshot.hooks == ()
    assert snapshot.issues == ()


def test_repository_example_is_valid(tmp_path):
    example = Path(".dragon-code/hooks.yaml.example").read_text(encoding="utf-8")
    project = tmp_path / "project"
    write(project / ".dragon-code/hooks.yaml", example)
    snapshot = HookLoader(project, user_home=tmp_path / "home").load()
    assert len(snapshot.hooks) == 3
    assert snapshot.issues == ()
