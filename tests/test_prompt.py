"""启动 Banner 的资源与渲染测试。"""

from dragon_code.prompt import DRAGON_BANNER, render_banner


def test_dragon_banner_size_and_ascii():
    """龙头像应紧凑，并且只使用终端宽度稳定的 ASCII 字符。"""

    lines = DRAGON_BANNER.splitlines()

    assert len(lines) == 5
    assert max(len(line) for line in lines) <= 24
    assert all(ord(character) < 128 for character in DRAGON_BANNER)


def test_dragon_banner_has_approved_features():
    """徽章应包含朝向三个方向的龙头和向下收拢的轮廓。"""

    lines = DRAGON_BANNER.splitlines()

    assert lines[0].strip() == "/^\\"
    assert DRAGON_BANNER.count("o") == 2
    assert lines[1].startswith("  <<==<")
    assert lines[1].endswith(">==>>")
    assert lines[-1].strip().startswith(r"\____")
    assert lines[-1].strip().endswith("____/")


def test_old_dragon_features_are_removed():
    assert "===" not in DRAGON_BANNER
    assert "\\___/  \\___/" not in DRAGON_BANNER


def test_render_banner_keeps_existing_text():
    rendered = render_banner("0.1.0", "/tmp/demo")

    assert rendered.startswith(DRAGON_BANNER)
    assert "Dragon Code v0.1.0" in rendered
    assert "工作目录：/tmp/demo" in rendered
    assert "准备就绪，可以开始对话。" in rendered
