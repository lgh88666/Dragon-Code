"""项目指令加载测试。"""

from pathlib import Path

from dragon_code.instructions import InstructionLoader


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_loads_three_sources_in_priority_order(tmp_path: Path):
    project = tmp_path / "project"
    home = tmp_path / "home"
    write_text(project / "DRAGON.md", "project-root")
    write_text(project / ".dragon-code" / "DRAGON.md", "project-local")
    write_text(home / ".dragon-code" / "DRAGON.md", "user-global")

    result = InstructionLoader(project, home).load()

    assert result == "project-root\n\nproject-local\n\nuser-global"


def test_missing_and_empty_sources_are_skipped(tmp_path: Path):
    project = tmp_path / "project"
    home = tmp_path / "home"
    write_text(project / "DRAGON.md", "only-source")
    write_text(project / ".dragon-code" / "DRAGON.md", "  \n")

    loader = InstructionLoader(project, home)

    assert loader.load() == "only-source"
    assert loader.warnings() == []


def test_include_is_expanded_only_on_its_own_line(tmp_path: Path):
    project = tmp_path / "project"
    write_text(project / "rules" / "style.md", "use simple python")
    write_text(
        project / "DRAGON.md",
        "before\n@include rules/style.md\ntext @include rules/style.md\nafter",
    )

    result = InstructionLoader(project, tmp_path / "home").load()

    assert result == ("before\nuse simple python\ntext @include rules/style.md\nafter")


def test_same_file_can_be_used_by_two_non_cyclic_branches(tmp_path: Path):
    project = tmp_path / "project"
    write_text(project / "shared.md", "shared")
    write_text(project / "a.md", "A\n@include shared.md")
    write_text(project / "b.md", "B\n@include shared.md")
    write_text(project / "DRAGON.md", "@include a.md\n@include b.md")

    loader = InstructionLoader(project, tmp_path / "home")

    assert loader.load() == "A\nshared\nB\nshared"
    assert loader.warnings() == []


def test_cycle_is_skipped_with_warning(tmp_path: Path):
    project = tmp_path / "project"
    write_text(project / "DRAGON.md", "root\n@include a.md")
    write_text(project / "a.md", "A\n@include DRAGON.md")

    loader = InstructionLoader(project, tmp_path / "home")
    result = loader.load()

    assert result == "root\nA"
    assert any("循环引用" in warning for warning in loader.warnings())


def test_sixth_nested_include_is_skipped(tmp_path: Path):
    project = tmp_path / "project"
    write_text(project / "DRAGON.md", "root\n@include level1.md")
    for level in range(1, 7):
        next_line = f"\n@include level{level + 1}.md" if level < 6 else ""
        write_text(project / f"level{level}.md", f"level{level}{next_line}")

    loader = InstructionLoader(project, tmp_path / "home")
    result = loader.load()

    assert "level5" in result
    assert "level6" not in result
    assert any("最大嵌套深度" in warning for warning in loader.warnings())


def test_project_include_cannot_escape_project(tmp_path: Path):
    project = tmp_path / "project"
    write_text(tmp_path / "secret.md", "secret-value")
    write_text(project / "DRAGON.md", "safe\n@include ../secret.md")

    loader = InstructionLoader(project, tmp_path / "home")
    result = loader.load()

    assert result == "safe"
    assert "secret-value" not in "\n".join(loader.warnings())
    assert any("允许范围" in warning for warning in loader.warnings())


def test_user_include_cannot_escape_user_config(tmp_path: Path):
    project = tmp_path / "project"
    home = tmp_path / "home"
    write_text(home / "secret.md", "user-secret")
    write_text(home / ".dragon-code" / "DRAGON.md", "user\n@include ../secret.md")

    loader = InstructionLoader(project, home)

    assert loader.load() == "user"
    assert any("允许范围" in warning for warning in loader.warnings())


def test_binary_and_invalid_utf8_includes_are_skipped(tmp_path: Path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "binary.md").write_bytes(b"abc\x00def")
    (project / "invalid.md").write_bytes(b"\xff\xfe")
    write_text(
        project / "DRAGON.md",
        "safe\n@include binary.md\n@include invalid.md",
    )

    loader = InstructionLoader(project, tmp_path / "home")

    assert loader.load() == "safe"
    assert any("二进制" in warning for warning in loader.warnings())
    assert any("UTF-8" in warning for warning in loader.warnings())
