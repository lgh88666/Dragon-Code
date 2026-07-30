"""启动 Banner 的资源与渲染测试。"""

from rich.text import Text

from dragon_code.prompt import DRAGON_BANNER, build_system_prompt, render_banner


def test_dragon_banner_matches_approved_icon():
    """图标的字符、行数和位置必须与批准版本完全相同。"""

    lines = DRAGON_BANNER.splitlines()

    assert lines == [
        " ▗▄   ▄▖",
        "▐██▙▄▟██▌",
        "▝██▀█▀██▘",
        "  ▘   ▝",
    ]
    assert len(lines) == 4
    assert max(len(line) for line in lines) == 9


def test_old_dragon_features_are_removed():
    assert "<<==<" not in DRAGON_BANNER
    assert ">==>>" not in DRAGON_BANNER
    assert "o o" not in DRAGON_BANNER
    assert "#d13b3b" not in DRAGON_BANNER


def test_render_banner_has_approved_layout():
    rendered = render_banner("0.1.0", r"D:\project")

    assert isinstance(rendered, Text)
    assert rendered.plain.splitlines() == [
        " ▗▄   ▄▖   Dragon Code  v0.1.0",
        "▐██▙▄▟██▌  Multi-provider coding agent",
        r"▝██▀█▀██▘  D:\project",
        "  ▘   ▝",
    ]


def test_render_banner_keeps_special_directory_characters():
    rendered = render_banner("1.2.3", r"D:\My [Demo] Project")

    assert r"D:\My [Demo] Project" in rendered.plain
    assert "v1.2.3" in rendered.plain


def test_render_banner_uses_approved_styles():
    rendered = render_banner("0.1.0", r"D:\project")
    styles = {str(span.style) for span in rendered.spans}

    assert "white" in styles
    assert "bold white" in styles
    assert "grey70" in styles


def test_system_prompt_contains_agent_rules(tmp_path):
    prompt = build_system_prompt(tmp_path)
    assert "Dragon Code" in prompt
    assert str(tmp_path.resolve()) in prompt
    assert "Read、Write、Edit、Bash、Glob、Grep" in prompt
    assert "只执行一轮工具" in prompt
    assert "仅支持文本对话" not in prompt
