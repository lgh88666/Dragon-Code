"""启动 Banner 的资源与渲染测试。"""

from dragon_code.prompt import DRAGON_BANNER, render_banner


def test_dragon_banner_size_and_ascii():
    """龙头像应紧凑，并且只使用终端宽度稳定的 ASCII 字符。"""

    lines = DRAGON_BANNER.splitlines()

    assert len(lines) == 5
    assert max(len(line) for line in lines) <= 24
    assert all(ord(character) < 128 for character in DRAGON_BANNER)


def test_dragon_banner_has_approved_features():
    """龙头像应包含短角、双眼、脸部尖角和下颌。"""

    lines = DRAGON_BANNER.splitlines()

    assert lines[0].count("/\\") == 2
    assert DRAGON_BANNER.count("o") == 2
    assert "<" in DRAGON_BANNER
    assert ">" in DRAGON_BANNER
    assert "===" in DRAGON_BANNER


def test_cat_features_are_removed():
    assert "/\\_/\\" not in DRAGON_BANNER
    assert "o.o" not in DRAGON_BANNER


def test_render_banner_keeps_existing_text():
    rendered = render_banner("0.1.0", "/tmp/demo")

    assert rendered.startswith(DRAGON_BANNER)
    assert "Dragon Code v0.1.0" in rendered
    assert "工作目录：/tmp/demo" in rendered
    assert "准备就绪，可以开始对话。" in rendered
