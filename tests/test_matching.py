import pytest

from dragon_code.matching import MatcherKind, compile_matcher, match_value


def test_exact_and_not_matchers():
    assert match_value(compile_matcher(MatcherKind.EXACT, "Write"), "Write")
    assert not match_value(compile_matcher(MatcherKind.EXACT, "Write"), "Read")
    assert match_value(compile_matcher(MatcherKind.NOT, "Write"), "Read")


def test_glob_keeps_old_command_semantics():
    matcher = compile_matcher(MatcherKind.GLOB, "git *")
    assert matcher.matches("git status --short")
    assert not matcher.matches("uv run pytest")


def test_path_glob_distinguishes_star_and_double_star():
    assert compile_matcher("glob", "src/*.py").matches("src/main.py", path_mode=True)
    assert not compile_matcher("glob", "src/*.py").matches("src/pkg/main.py", path_mode=True)
    assert compile_matcher("glob", "src/**").matches("src/pkg/main.py", path_mode=True)


def test_regex_uses_search_and_rejects_invalid_pattern():
    assert compile_matcher("regex", r"rm\s+-rf").matches("sudo rm  -rf demo")
    with pytest.raises(ValueError):
        compile_matcher("regex", "[")


def test_missing_value_never_matches_even_for_not():
    assert not match_value(compile_matcher("not", "x"), None)
