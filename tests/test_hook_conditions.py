import pytest

from dragon_code.hooks.conditions import condition_matches, parse_condition_group
from dragon_code.hooks.models import HookContext, HookEvent


def context(**data):
    return HookContext(
        HookEvent.PRE_TOOL_USE, "s1", __import__("pathlib").Path.cwd(), "default", data
    )


def test_single_condition_reads_nested_field():
    group = parse_condition_group('args.path glob "src/**/*.py"')
    assert condition_matches(group, context(args={"path": "src/pkg/main.py"}))
    assert not condition_matches(group, context(args={}))


def test_all_of_and_any_of():
    all_group = parse_condition_group(
        {"all_of": ['tool.name == "Write"', 'args.path != "vendor/a.py"']}
    )
    any_group = parse_condition_group({"any_of": ['tool.name == "Read"', 'tool.name == "Write"']})
    value = context(tool={"name": "Write"}, args={"path": "src/a.py"})
    assert condition_matches(all_group, value)
    assert condition_matches(any_group, value)


@pytest.mark.parametrize(
    "raw", [{"all_of": [], "any_of": []}, {"all_of": [{"any_of": []}]}, {"bad": []}]
)
def test_condition_group_rejects_mixed_nested_or_unknown(raw):
    with pytest.raises(ValueError):
        parse_condition_group(raw)
