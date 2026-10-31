"""Unit tests for the YesOrNoCount capability (`ca/yes_or_no_count`), with made-up kinds.

A form line that asks a yes or no question takes its answer as a count of 0 or 1. Its slots: one
consumed single slot, `count` (an `int` kind), one produced slot `output` (an `int` kind), no
parameter slots and no dataset. The output is the count, unchanged, when it is 0 or 1; a count
above 1 is an input error, `InputAboveBoundError`, naming the kind and its value. It records one
`YesOrNoCountLine`. A negative count is refused by the kind's `non_negative` declaration, not here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields
from decimal import Decimal
from types import MappingProxyType
from typing import Any, assert_type, cast

import pytest

import tax_engine.jurisdictions.ca.capabilities as ca_capabilities
from tax_engine.adapters.inbound.trace_english import EnglishTraceRenderer
from tax_engine.domain.artifact import Artifact, ArtifactKind
from tax_engine.domain.blank import BLANK, PASS_ON
from tax_engine.domain.capability import CapabilityRegistry
from tax_engine.domain.errors import (
    BlankNotAllowedError,
    DomainError,
    InputAboveBoundError,
    InputBelowBoundError,
    InvalidCapabilityError,
    MissingArtifactError,
)
from tax_engine.domain.trace import BlankPassedOnLine, YesOrNoCountLine
from tax_engine.jurisdictions.ca.capabilities.yes_or_no_count import YesOrNoCount

COUNT = ArtifactKind("ex/yes_or_no", int)
OUTPUT = ArtifactKind("ex/yes_or_no_checked", int)


def capability() -> YesOrNoCount:
    return YesOrNoCount(COUNT, OUTPUT)


def inputs(count: int) -> tuple[Artifact[Any], ...]:
    return (Artifact(COUNT, count),)


def compute(count: int) -> Artifact[Any]:
    (output,) = capability().compute(inputs(count)).outputs
    return output


def test_is_registered_as_ca_yes_or_no_count() -> None:
    assert CapabilityRegistry.shared().get("ca/yes_or_no_count") is YesOrNoCount


def test_is_exported_from_the_federal_capabilities_package() -> None:
    assert "yes_or_no_count" in ca_capabilities.__all__
    assert ca_capabilities.yes_or_no_count.YesOrNoCount is YesOrNoCount


def test_declares_its_contract() -> None:
    assert capability().consumes == frozenset({COUNT})
    assert capability().produces == frozenset({OUTPUT})


def test_leaves_its_contract_to_the_base() -> None:
    assert "consumes" not in vars(YesOrNoCount)
    assert "produces" not in vars(YesOrNoCount)


def test_declares_its_slots() -> None:
    assert YesOrNoCount.PARAMETERS == {}
    assert YesOrNoCount.CONSUMES == {"count": int}
    assert YesOrNoCount.PRODUCES == {"output": int}
    assert not YesOrNoCount.is_list_slot("count")


def test_its_slots_are_read_only() -> None:
    for slots in (YesOrNoCount.PARAMETERS, YesOrNoCount.CONSUMES, YesOrNoCount.PRODUCES):
        assert isinstance(slots, MappingProxyType)


def test_its_slots_are_typed_as_read_only_mappings() -> None:
    assert_type(YesOrNoCount.CONSUMES, Mapping[str, type])
    assert_type(YesOrNoCount.PRODUCES, Mapping[str, type])


def test_its_slots_cannot_be_changed() -> None:
    for slots in (YesOrNoCount.CONSUMES, YesOrNoCount.PRODUCES):
        with pytest.raises(TypeError):
            cast(Any, slots)["extra"] = int


def test_is_built_from_its_slot_names_as_keywords() -> None:
    wired = YesOrNoCount(count=COUNT, output=OUTPUT)

    assert wired.compute(inputs(1)).outputs == (Artifact(OUTPUT, 1),)


def test_takes_no_parameter_dataset() -> None:
    with pytest.raises(TypeError):
        YesOrNoCount(COUNT, OUTPUT, object())  # type: ignore[call-arg]


def test_rejects_one_kind_in_two_slots() -> None:
    with pytest.raises(InvalidCapabilityError, match="YesOrNoCount") as raised:
        YesOrNoCount(COUNT, COUNT)

    assert "'count'" in str(raised.value)
    assert "'output'" in str(raised.value)


def test_rejects_a_list_of_kinds_for_its_count() -> None:
    with pytest.raises(InvalidCapabilityError, match="YesOrNoCount.*'count'"):
        YesOrNoCount((COUNT,), OUTPUT)  # type: ignore[arg-type]


def test_mypy_rejects_wiring_a_money_kind_for_a_count() -> None:
    money = ArtifactKind("ex/money", Decimal)
    # An ArtifactKind[Decimal] is not an ArtifactKind[int]; the ignore fails under mypy
    # (warn_unused_ignores) if it is ever accepted. At run time, building it fails too.
    with pytest.raises(InvalidCapabilityError, match="YesOrNoCount.*'count'"):
        YesOrNoCount(money, OUTPUT)  # type: ignore[arg-type]


def test_is_not_generic_over_artifacts() -> None:
    assert not getattr(YesOrNoCount, "__type_params__", ())
    assert not getattr(YesOrNoCount, "__parameters__", ())


# --- computing: 0 or 1 ----------------------------------------------------------------------------


def test_a_count_of_0_is_produced_unchanged() -> None:
    output = compute(0)

    assert output == Artifact(OUTPUT, 0)
    assert type(output.value) is int


def test_a_count_of_1_is_produced_unchanged() -> None:
    output = compute(1)

    assert output == Artifact(OUTPUT, 1)
    assert type(output.value) is int


def test_ignores_artifacts_it_does_not_consume() -> None:
    other = Artifact(ArtifactKind("ex/other", int), 9)

    assert capability().compute((other, *inputs(1))).outputs == (Artifact(OUTPUT, 1),)


def test_a_missing_count_is_a_missing_artifact() -> None:
    with pytest.raises(MissingArtifactError, match="yes_or_no"):
        capability().compute(())


def test_has_one_output() -> None:
    assert len(capability().compute(inputs(1)).outputs) == 1


def test_compute_is_repeatable() -> None:
    wired = capability()

    assert wired.compute(inputs(1)) == wired.compute(inputs(1))


# --- a count above 1 ------------------------------------------------------------------------------


def test_a_count_of_2_is_an_input_above_bound_error() -> None:
    with pytest.raises(InputAboveBoundError):
        compute(2)


def test_the_error_names_the_kind_and_its_value() -> None:
    with pytest.raises(InputAboveBoundError, match=r"ex/yes_or_no 2\b"):
        compute(2)


def test_a_count_of_5_is_refused_too() -> None:
    with pytest.raises(InputAboveBoundError, match=r"ex/yes_or_no 5\b"):
        compute(5)


def test_an_input_above_bound_error_is_not_an_input_below_bound_error() -> None:
    with pytest.raises(InputAboveBoundError) as raised:
        compute(2)

    assert not isinstance(raised.value, InputBelowBoundError)
    assert issubclass(InputAboveBoundError, DomainError)


def test_an_input_above_bound_error_is_not_a_wiring_error() -> None:
    assert not issubclass(InputAboveBoundError, InvalidCapabilityError)


# --- trace ----------------------------------------------------------------------------------------


def test_traces_one_yes_or_no_count_line() -> None:
    assert capability().compute(inputs(1)).trace == (
        YesOrNoCountLine(output=OUTPUT, count_kind=COUNT, count=1),
    )


def test_trace_amount_is_the_count() -> None:
    trace = capability().compute(inputs(0)).trace

    assert [line.amount for line in trace] == [Decimal(0)]


def test_trace_holds_no_text() -> None:
    for line in capability().compute(inputs(1)).trace:
        assert not any(isinstance(getattr(line, f.name), str) for f in fields(line))


# --- a blank answer ---------------------------------------------------------------------------


def test_declares_that_only_the_count_may_be_blank() -> None:
    assert YesOrNoCount.BLANK_ALLOWED == frozenset({"count"})


def test_a_blank_count_is_refused_without_a_blank_rule() -> None:
    with pytest.raises(BlankNotAllowedError, match="may not be blank"):
        capability().run((Artifact(COUNT, BLANK),))


def test_a_blank_count_passes_on_as_a_blank_output() -> None:
    result = capability().with_blank_rules({"count": PASS_ON}).run((Artifact(COUNT, BLANK),))

    assert result.outputs == (Artifact(OUTPUT, BLANK),)
    assert result.trace == (BlankPassedOnLine(OUTPUT, (COUNT,)),)


def test_the_blank_trace_says_which_line_was_left_blank() -> None:
    result = capability().with_blank_rules({"count": PASS_ON}).run((Artifact(COUNT, BLANK),))

    assert EnglishTraceRenderer().render_all(result.trace) == (
        "yes_or_no_checked: blank because yes_or_no was blank",
    )


@pytest.mark.parametrize("count", [0, 1])
def test_a_filled_count_is_unchanged_when_blank_is_passed_on(count: int) -> None:
    result = capability().with_blank_rules({"count": PASS_ON}).run(inputs(count))

    assert result.outputs == (Artifact(OUTPUT, count),)
    assert result.trace == (YesOrNoCountLine(output=OUTPUT, count_kind=COUNT, count=count),)


def test_a_filled_count_above_one_is_still_refused_when_blank_is_passed_on() -> None:
    with pytest.raises(InputAboveBoundError, match="above a yes or no answer of 1"):
        capability().with_blank_rules({"count": PASS_ON}).run(inputs(2))


def test_a_fallback_for_the_count_is_accepted_by_the_base() -> None:
    result = capability().with_blank_rules({"count": 0}).run((Artifact(COUNT, BLANK),))

    assert result.outputs == (Artifact(OUTPUT, 0),)
