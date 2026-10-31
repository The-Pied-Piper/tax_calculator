"""Unit tests for YamlNode: a parsed YAML value plus its location, for strict reading."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import assert_type

import pytest
import yaml

from tax_engine.adapters.outbound.yaml_support import YamlNode, YamlShapeError
from tax_engine.domain.errors import InvalidRoundingRuleError
from tax_engine.domain.parameters.rounding import (
    NO_ROUNDING,
    RoundingMode,
    RoundingRule,
    RoundTo,
)


def node(value: object) -> YamlNode:
    return YamlNode.root(value, "document")


# --- loading -------------------------------------------------------------------


def test_load_parses_a_file(tmp_path: Path) -> None:
    path = tmp_path / "x.yaml"
    path.write_text("a: 1\n", encoding="utf-8")

    assert YamlNode.load(path, "document").value == {"a": 1}


def test_load_rejects_duplicate_keys(tmp_path: Path) -> None:
    path = tmp_path / "x.yaml"
    path.write_text("a: 1\na: 2\n", encoding="utf-8")

    with pytest.raises(yaml.YAMLError, match="duplicate key 'a'"):
        YamlNode.load(path, "document")


# --- mappings and locations ------------------------------------------------------


def test_require_mapping_accepts_exact_keys() -> None:
    doc = node({"a": 1, "b": 2}).require_mapping(frozenset({"a", "b"}))

    assert doc.field("a").value == 1


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ([1], "document must be a mapping"),
        (None, "document must be a mapping"),
        ({"a": 1, "x": 2}, r"document: unknown keys \['x'\]"),
        ({}, r"document: missing keys \['a'\]"),
    ],
)
def test_require_mapping_rejects(value: object, message: str) -> None:
    with pytest.raises(YamlShapeError, match=message):
        node(value).require_mapping(frozenset({"a"}))


def test_require_mapping_accepts_optional_keys_present_or_absent() -> None:
    keys, optional = frozenset({"a"}), frozenset({"b"})

    assert node({"a": 1, "b": 2}).require_mapping(keys, optional=optional).field("b").value == 2
    assert node({"a": 1}).require_mapping(keys, optional=optional).optional_field("b") is None


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({"a": 1, "x": 2}, r"document: unknown keys \['x'\]"),
        ({"b": 2}, r"document: missing keys \['a'\]"),
    ],
)
def test_require_mapping_with_optional_keys_rejects(value: object, message: str) -> None:
    with pytest.raises(YamlShapeError, match=message):
        node(value).require_mapping(frozenset({"a"}), optional=frozenset({"b"}))


def test_optional_field_is_the_value_under_a_present_key() -> None:
    found = node({"params": {"a": "x"}}).optional_field("params")

    assert found is not None
    assert found.where == "params"
    assert found.value == {"a": "x"}


def test_optional_field_requires_a_mapping() -> None:
    with pytest.raises(YamlShapeError, match="^document must be a mapping"):
        node([1]).optional_field("a")


def test_string_mapping_reads_strings_to_strings() -> None:
    assert node({"m": {"a": "x", "b": "y"}}).field("m").string_mapping() == {"a": "x", "b": "y"}
    assert node({"m": {}}).field("m").string_mapping() == {}


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({"a": 7}, r"^m\.a must be a string, got int"),
        ({"a": None}, r"^m\.a must be a string, got NoneType"),
        ({7: "x"}, r"^m: key 7 must be a string, got int"),
        ({"": "x"}, r"^m: keys must not be empty"),
        ({"a": ""}, r"^m\.a must not be empty"),
        (["x"], "^m must be a mapping"),
        (None, "^m must be a mapping"),
    ],
)
def test_string_mapping_rejects(value: object, message: str) -> None:
    with pytest.raises(YamlShapeError, match=message):
        node({"m": value}).field("m").string_mapping()


def test_top_level_fields_are_named_without_the_root_label() -> None:
    with pytest.raises(YamlShapeError, match="^version must be an integer"):
        node({"version": "1"}).field("version").require_integer()


def test_locations_follow_fields_and_items() -> None:
    doc = node({"brackets": [{"rate": "ten"}]})
    rate = doc.field("brackets").items()[0].field("rate")

    assert rate.where == "brackets[0].rate"
    with pytest.raises(YamlShapeError, match=r"^brackets\[0\].rate is not a decimal: 'ten'"):
        rate.parse_decimal()


def test_items_rejects_non_list() -> None:
    with pytest.raises(YamlShapeError, match="^sources must be a list"):
        node({"sources": "x"}).field("sources").items()


def test_field_of_a_missing_key_is_a_shape_error() -> None:
    with pytest.raises(YamlShapeError, match="missing key 'a'"):
        node({}).field("a")


# --- scalars ---------------------------------------------------------------------


def test_require_string() -> None:
    assert node({"a": "x"}).field("a").require_string() == "x"
    with pytest.raises(YamlShapeError, match="^a must be a string, got int"):
        node({"a": 1}).field("a").require_string()


@pytest.mark.parametrize(("value", "got"), [(True, "bool"), ("1", "str"), (1.0, "float")])
def test_require_integer_rejects(value: object, got: str) -> None:
    with pytest.raises(YamlShapeError, match=f"^a must be an integer, got {got}"):
        node({"a": value}).field("a").require_integer()


def test_require_integer_accepts_int() -> None:
    assert node({"a": 7}).field("a").require_integer() == 7


@pytest.mark.parametrize(
    ("value", "got"), [(1, "int"), (0, "int"), ("true", "str"), ("yes", "str"), (None, "NoneType")]
)
def test_require_boolean_rejects(value: object, got: str) -> None:
    with pytest.raises(YamlShapeError, match=f"^a must be true or false, got {got}"):
        node({"a": value}).field("a").require_boolean()


def test_require_boolean_accepts_a_boolean() -> None:
    assert node({"a": True}).field("a").require_boolean() is True
    assert node({"a": False}).field("a").require_boolean() is False


def test_parse_decimal_reads_strings_exactly() -> None:
    assert node({"a": "0.145"}).field("a").parse_decimal() == Decimal("0.145")


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (0.145, "a must be a string, got float"),
        ("abc", "a is not a decimal: 'abc'"),
        ("NaN", "a is not a decimal: 'NaN'"),
        ("Infinity", "a is not a decimal: 'Infinity'"),
    ],
)
def test_parse_decimal_rejects(value: object, message: str) -> None:
    with pytest.raises(YamlShapeError, match=f"^{message}"):
        node({"a": value}).field("a").parse_decimal()


@pytest.mark.parametrize(
    ("value", "number"), [("0", 0), ("3", 3), ("10", 10), ("1000000", 1000000)]
)
def test_parse_whole_number_reads_digit_strings_as_ints(value: str, number: int) -> None:
    parsed = node({"a": value}).field("a").parse_whole_number()

    assert parsed == number
    assert type(parsed) is int


def test_parse_whole_number_reads_more_digits_than_a_machine_word() -> None:
    assert node({"a": "1" + "0" * 30}).field("a").parse_whole_number() == 10**30


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("-3", r"a is not a whole number: '-3'"),
        ("+3", r"a is not a whole number: '\+3'"),
        ("03", r"a is not a whole number: '03'"),
        ("00", r"a is not a whole number: '00'"),
        (" 3", r"a is not a whole number: ' 3'"),
        ("3 ", r"a is not a whole number: '3 '"),
        ("1_000", r"a is not a whole number: '1_000'"),
        ("3.0", r"a is not a whole number: '3\.0'"),
        ("٣", r"a is not a whole number: '٣'"),  # ARABIC-INDIC DIGIT THREE
        ("３", r"a is not a whole number: '３'"),  # FULLWIDTH DIGIT THREE
        ("", r"a is not a whole number: ''"),
        ("three", r"a is not a whole number: 'three'"),
        (3, "a must be a string, got int"),
        (3.0, "a must be a string, got float"),
        (True, "a must be a string, got bool"),
    ],
)
def test_parse_whole_number_rejects(value: object, message: str) -> None:
    with pytest.raises(YamlShapeError, match=f"^{message}"):
        node({"a": value}).field("a").parse_whole_number()


def test_parse_whole_number_rejects_more_digits_than_int_converts() -> None:
    # 4,301 digits: one more than `int()` converts from text by default.
    with pytest.raises(YamlShapeError, match="^a is not a whole number: '1000"):
        node({"a": "1" + "0" * 4300}).field("a").parse_whole_number()


def test_parse_whole_number_names_the_nodes_location() -> None:
    part = node({"parts": [{"numerator": "-2"}]}).field("parts").items()[0].field("numerator")

    with pytest.raises(YamlShapeError, match=r"^parts\[0\]\.numerator is not a whole number"):
        part.parse_whole_number()


# --- rounding rules ----------------------------------------------------------------


def test_parse_rounding_rule_reads_none_as_no_rounding() -> None:
    assert node({"a": "none"}).field("a").parse_rounding_rule() == NO_ROUNDING


@pytest.mark.parametrize(
    ("increment", "mode", "rule"),
    [
        ("0.01", "half_up", RoundTo(Decimal("0.01"), RoundingMode.HALF_UP)),
        ("1", "down", RoundTo(Decimal("1"), RoundingMode.DOWN)),
        ("0.05", "half_even", RoundTo(Decimal("0.05"), RoundingMode.HALF_EVEN)),
        ("1", "up", RoundTo(Decimal("1"), RoundingMode.UP)),
        ("0.01", "floor", RoundTo(Decimal("0.01"), RoundingMode.FLOOR)),
        ("0.01", "ceiling", RoundTo(Decimal("0.01"), RoundingMode.CEILING)),
    ],
)
def test_parse_rounding_rule_reads_an_increment_and_a_mode(
    increment: str, mode: str, rule: RoundingRule
) -> None:
    parsed = node({"a": {"increment": increment, "mode": mode}}).field("a").parse_rounding_rule()

    assert parsed == rule
    assert isinstance(parsed, RoundingRule)


def test_parse_rounding_rule_reads_the_increment_exactly() -> None:
    parsed = node({"a": {"increment": "0.01", "mode": "half_up"}}).field("a").parse_rounding_rule()

    assert isinstance(parsed, RoundTo)
    assert str(parsed.increment) == "0.01"


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("always", "a must be 'none' or a mapping of increment and mode"),
        ("None", "a must be 'none' or a mapping of increment and mode"),
        ("", "a must be 'none' or a mapping of increment and mode"),
        (None, "a must be 'none' or a mapping of increment and mode"),
        (False, "a must be 'none' or a mapping of increment and mode"),
        (1, "a must be 'none' or a mapping of increment and mode"),
        (["0.01", "half_up"], "a must be 'none' or a mapping of increment and mode"),
        ({"increment": "0.01"}, r"a: missing keys \['mode'\]"),
        ({"mode": "down"}, r"a: missing keys \['increment'\]"),
        ({}, r"a: missing keys \['increment', 'mode'\]"),
        (
            {"increment": "1", "mode": "up", "step": "1"},
            r"a: unknown keys \['step'\]",
        ),
        ({"increment": "0.01", "mode": "sideways"}, r"a\.mode 'sideways' is not one of"),
        ({"increment": "0.01", "mode": "HALF_UP"}, r"a\.mode 'HALF_UP' is not one of"),
        ({"increment": "0.01", "mode": 1}, r"a\.mode must be a string, got int"),
        ({"increment": "0.01", "mode": None}, r"a\.mode must be a string, got NoneType"),
        ({"increment": 0.01, "mode": "down"}, r"a\.increment must be a string, got float"),
        ({"increment": 1, "mode": "down"}, r"a\.increment must be a string, got int"),
        ({"increment": "cent", "mode": "down"}, r"a\.increment is not a decimal: 'cent'"),
        ({"increment": "NaN", "mode": "down"}, r"a\.increment is not a decimal: 'NaN'"),
    ],
)
def test_parse_rounding_rule_rejects(value: object, message: str) -> None:
    with pytest.raises(YamlShapeError, match=f"^{message}"):
        node({"a": value}).field("a").parse_rounding_rule()


def test_parse_rounding_rule_lists_the_modes_it_accepts() -> None:
    modes = sorted(mode.value for mode in RoundingMode)

    with pytest.raises(YamlShapeError) as raised:
        node({"a": {"increment": "1", "mode": "sideways"}}).field("a").parse_rounding_rule()

    assert str(raised.value) == f"a.mode 'sideways' is not one of {modes}"


@pytest.mark.parametrize("increment", ["0", "-0.01"])
def test_parse_rounding_rule_refuses_an_increment_that_is_not_positive(increment: str) -> None:
    with pytest.raises(InvalidRoundingRuleError, match="^increment must be a positive"):
        node({"a": {"increment": increment, "mode": "down"}}).field("a").parse_rounding_rule()


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("always", r"^dataset\.rounding must be 'none' or a mapping of increment and mode"),
        ({"increment": "1"}, r"^dataset\.rounding: missing keys \['mode'\]"),
        ({"increment": "1", "mode": "x"}, r"^dataset\.rounding\.mode 'x' is not one of"),
        ({"increment": "x", "mode": "up"}, r"^dataset\.rounding\.increment is not a decimal"),
    ],
)
def test_parse_rounding_rule_names_the_nodes_location(value: object, message: str) -> None:
    rule = node({"dataset": {"rounding": value}}).field("dataset").field("rounding")

    assert rule.where == "dataset.rounding"
    with pytest.raises(YamlShapeError, match=message):
        rule.parse_rounding_rule()


# --- choices from an enum ----------------------------------------------------------------------


class Shade(Enum):
    """A made-up choice, read by its values."""

    LIGHT = "light"
    DARK = "dark"


@pytest.mark.parametrize(("text", "member"), [("light", Shade.LIGHT), ("dark", Shade.DARK)])
def test_parse_choice_reads_the_member_of_that_value(text: str, member: Shade) -> None:
    parsed = node({"a": text}).field("a").parse_choice(Shade)

    assert_type(parsed, Shade)
    assert parsed is member


def test_parse_choice_lists_the_values_it_accepts_sorted() -> None:
    with pytest.raises(YamlShapeError) as raised:
        node({"a": "dim"}).field("a").parse_choice(Shade)

    assert str(raised.value) == "a 'dim' is not one of ['dark', 'light']"


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("LIGHT", r"^a 'LIGHT' is not one of \['dark', 'light'\]$"),
        ("", r"^a '' is not one of"),
        (True, r"^a must be a string, got bool$"),
        (1, r"^a must be a string, got int$"),
        (None, r"^a must be a string, got NoneType$"),
        (["light"], r"^a must be a string, got list$"),
    ],
)
def test_parse_choice_rejects(value: object, message: str) -> None:
    with pytest.raises(YamlShapeError, match=message):
        node({"a": value}).field("a").parse_choice(Shade)


def test_parse_choice_names_the_nodes_location() -> None:
    choice = node({"dataset": {"shade": "dim"}}).field("dataset").field("shade")

    with pytest.raises(YamlShapeError, match=r"^dataset\.shade 'dim' is not one of"):
        choice.parse_choice(Shade)


def test_parse_choice_reads_a_rounding_mode_as_parse_rounding_rule_does() -> None:
    # One reading of an enum choice: the rounding rule's mode gives the same member and the same
    # refusal as `parse_choice(RoundingMode)`.
    rule = node({"a": {"increment": "1", "mode": "half_even"}}).field("a").parse_rounding_rule()

    assert rule == RoundTo(
        Decimal("1"), node({"m": "half_even"}).field("m").parse_choice(RoundingMode)
    )
    with pytest.raises(YamlShapeError) as by_choice:
        node({"a": {"mode": "sideways"}}).field("a").field("mode").parse_choice(RoundingMode)
    with pytest.raises(YamlShapeError) as by_rule:
        node({"a": {"increment": "1", "mode": "sideways"}}).field("a").parse_rounding_rule()
    assert str(by_rule.value) == str(by_choice.value)
