"""Unit tests for EiExcludedSlipsNetIncome, the amount Schedule 13 line 1 leaves out.

Schedule 13 line 1: "Enter the total amount from line 1 1 plus line 27 of your return. If you
received a T4 slip for self-employment income with EI premiums in box 18, do not include any net
income (or net loss) reported on lines 13500, 13700, 13900, 14100, and 14300 of your return for
that slip (Note 1) (if negative, enter "0")."

The capability consumes the record list of those slips and produces the total of the net income
(or net loss) each reports: it adds that field of every slip exactly, with no rounding (it has no
dataset), a net loss being negative, is 0 for no slips, and records one `RecordTotalLine` naming
each slip's amount by position from 1. Its slots: no parameter slot, one consumed slot `slips`
(the record list) and one produced slot `output`.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from types import MappingProxyType
from typing import Any

import pytest

import tax_engine.jurisdictions.ca.capabilities as ca_capabilities
from tax_engine.adapters.inbound.trace_english import EnglishTraceRenderer
from tax_engine.application.services.tax_computation import TaxComputationService
from tax_engine.domain.artifact import Artifact, ArtifactKind, ArtifactRegistry
from tax_engine.domain.capability import CapabilityRegistry
from tax_engine.domain.errors import InvalidCapabilityError, MissingArtifactError, NotFoundError
from tax_engine.domain.jurisdiction import Jurisdiction
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import CapabilitySelection, Form, Manifest
from tax_engine.domain.parameters.datasets import ParameterDataset
from tax_engine.domain.parameters.kind import ParameterKind
from tax_engine.domain.record_list import RecordList
from tax_engine.domain.trace import RecordTotalLine
from tax_engine.jurisdictions.ca.capabilities.ei_excluded_slips_net_income import (
    EiExcludedSlipsNetIncome,
)
from tax_engine.jurisdictions.ca.catalog import (
    EI_EXCLUDED_SLIP_NET_INCOME,
    EI_EXCLUDED_SLIPS,
    EI_EXCLUDED_SLIPS_NET_INCOME,
)
from tests.manifest_support import required_inputs

D = Decimal


def capability() -> EiExcludedSlipsNetIncome:
    return EiExcludedSlipsNetIncome(slips=EI_EXCLUDED_SLIPS, output=EI_EXCLUDED_SLIPS_NET_INCOME)


def slips(*amounts: str) -> Artifact[Any]:
    """A `ca/ei_excluded_slips` artifact of one record per net income, in order."""
    records: list[Mapping[ArtifactKind[Any], object]] = [
        {EI_EXCLUDED_SLIP_NET_INCOME: D(amount)} for amount in amounts
    ]
    return Artifact(EI_EXCLUDED_SLIPS, RecordList(EI_EXCLUDED_SLIPS.fields, records))


def total_of(*amounts: str) -> Decimal:
    (artifact,) = capability().compute((slips(*amounts),)).outputs
    assert artifact.kind == EI_EXCLUDED_SLIPS_NET_INCOME
    assert isinstance(artifact.value, Decimal)
    return artifact.value


def test_is_registered_as_ca_ei_excluded_slips_net_income() -> None:
    assert (
        CapabilityRegistry.shared().get("ca/ei_excluded_slips_net_income")
        is EiExcludedSlipsNetIncome
    )


def test_is_exported_from_the_ca_capabilities_package() -> None:
    assert ca_capabilities.NAMESPACE == "ca"
    assert "ei_excluded_slips_net_income" in ca_capabilities.__all__
    assert (
        ca_capabilities.ei_excluded_slips_net_income.EiExcludedSlipsNetIncome
        is EiExcludedSlipsNetIncome
    )


def test_declares_its_contract() -> None:
    assert capability().consumes == frozenset({EI_EXCLUDED_SLIPS})
    assert capability().produces == frozenset({EI_EXCLUDED_SLIPS_NET_INCOME})


def test_leaves_its_contract_to_the_base() -> None:
    assert "consumes" not in vars(EiExcludedSlipsNetIncome)
    assert "produces" not in vars(EiExcludedSlipsNetIncome)


def test_declares_its_slots() -> None:
    assert EiExcludedSlipsNetIncome.PARAMETERS == {}
    assert EiExcludedSlipsNetIncome.CONSUMES == {"slips": RecordList}
    assert EiExcludedSlipsNetIncome.PRODUCES == {"output": Decimal}
    assert not EiExcludedSlipsNetIncome.is_list_slot("slips")


def test_its_slots_are_read_only() -> None:
    for slots in (
        EiExcludedSlipsNetIncome.PARAMETERS,
        EiExcludedSlipsNetIncome.CONSUMES,
        EiExcludedSlipsNetIncome.PRODUCES,
    ):
        assert isinstance(slots, MappingProxyType)
        assert isinstance(slots, Mapping)


def test_takes_no_parameter_dataset() -> None:
    with pytest.raises(TypeError):
        EiExcludedSlipsNetIncome(  # type: ignore[call-arg]
            EI_EXCLUDED_SLIPS, EI_EXCLUDED_SLIPS_NET_INCOME, object()
        )


def test_rejects_a_money_kind_for_its_slips() -> None:
    other = ArtifactKind("ex/not_a_list", Decimal)

    with pytest.raises(InvalidCapabilityError, match="EiExcludedSlipsNetIncome.*'slips'"):
        EiExcludedSlipsNetIncome(slips=other, output=EI_EXCLUDED_SLIPS_NET_INCOME)  # type: ignore[arg-type]


def test_rejects_a_record_list_kind_for_its_output() -> None:
    with pytest.raises(InvalidCapabilityError, match="EiExcludedSlipsNetIncome.*'output'"):
        EiExcludedSlipsNetIncome(slips=EI_EXCLUDED_SLIPS, output=EI_EXCLUDED_SLIPS)  # type: ignore[arg-type]


# --- computing --------------------------------------------------------------------------------


def test_no_slips_total_zero() -> None:
    assert total_of() == D("0")


def test_one_slip_is_its_own_total() -> None:
    assert total_of("20000") == D("20000")


def test_several_slips_add_up() -> None:
    assert total_of("20000", "5000", "1250.75") == D("26250.75")


def test_a_slip_with_a_net_loss_subtracts() -> None:
    # "do not include any net income (or net loss)": a loss is a negative amount of the total.
    assert total_of("20000", "-5000") == D("15000")


def test_slips_that_are_all_net_losses_total_a_negative_amount() -> None:
    assert total_of("-3000", "-1250.50") == D("-4250.50")


def test_a_net_loss_larger_than_the_net_income_gives_a_negative_total() -> None:
    assert total_of("1000", "-4000") == D("-3000")


def test_a_slip_with_no_net_income_adds_nothing() -> None:
    assert total_of("0", "6000") == D("6000")


def test_equal_slips_are_each_counted() -> None:
    assert total_of("6000", "6000") == D("12000")


def test_the_total_is_exact_and_never_rounded_to_the_cent() -> None:
    # A sum has no dataset, so no rounding: 0.001 + 0.002 = 0.003.
    assert total_of("0.001", "0.002") == D("0.003")
    assert str(total_of("1000.005", "0.001")) == "1000.006"


def test_the_total_is_exact_beyond_a_binary_float() -> None:
    assert total_of("0.1", "0.2") == D("0.3")


def test_the_total_does_not_depend_on_the_order_of_the_slips() -> None:
    assert total_of("6000", "-2000", "24000") == total_of("24000", "6000", "-2000")


# --- trace ------------------------------------------------------------------------------------


def test_produces_one_artifact_of_the_output_kind() -> None:
    result = capability().compute((slips("20000", "5000"),))

    assert result.outputs == (Artifact(EI_EXCLUDED_SLIPS_NET_INCOME, D("25000")),)


def test_records_one_trace_line_naming_each_amount_in_order() -> None:
    result = capability().compute((slips("20000", "-5000"),))

    assert result.trace == (
        RecordTotalLine(
            EI_EXCLUDED_SLIPS_NET_INCOME,
            EI_EXCLUDED_SLIP_NET_INCOME,
            (D("20000"), D("-5000")),
            D("15000"),
        ),
    )


def test_records_one_trace_line_for_no_slips() -> None:
    result = capability().compute((slips(),))

    assert result.trace == (
        RecordTotalLine(EI_EXCLUDED_SLIPS_NET_INCOME, EI_EXCLUDED_SLIP_NET_INCOME, (), D("0")),
    )


def test_records_one_trace_line_whatever_the_number_of_slips() -> None:
    for amounts in ((), ("1",), ("1", "2"), ("1", "2", "3", "4")):
        assert len(capability().compute((slips(*amounts),)).trace) == 1


def test_the_trace_keeps_the_callers_order_not_the_sorted_one() -> None:
    (line,) = capability().compute((slips("6000", "24000"),)).trace

    assert isinstance(line, RecordTotalLine)
    assert line.amounts == (D("6000"), D("24000"))


def test_its_trace_reads_item_by_item_in_english() -> None:
    result = capability().compute((slips("20000", "5000"),))

    assert EnglishTraceRenderer().render_all(result.trace) == (
        "ei_excluded_slips_net_income: item 1 ei_excluded_slip_net_income 20000 "
        "+ item 2 ei_excluded_slip_net_income 5000 = 25000",
    )


def test_its_trace_for_no_slips_says_no_items() -> None:
    result = capability().compute((slips(),))

    assert EnglishTraceRenderer().render_all(result.trace) == (
        "ei_excluded_slips_net_income: no items = 0",
    )


def test_needs_its_slips() -> None:
    with pytest.raises(MissingArtifactError, match="EiExcludedSlipsNetIncome"):
        capability().compute(())


def test_does_not_consume_anything_else() -> None:
    other = Artifact(ArtifactKind("ex/other", Decimal), D("1"))

    result = capability().compute((other, slips("20000")))

    assert result.outputs == (Artifact(EI_EXCLUDED_SLIPS_NET_INCOME, D("20000")),)


def test_compute_is_repeatable() -> None:
    wired = capability()
    given = (slips("20000", "-5000"),)

    assert wired.compute(given) == wired.compute(given)


# --- through TaxComputationService --------------------------------------------------------------


class _Jurisdictions:
    def __init__(self, jurisdiction: Jurisdiction) -> None:
        self._jurisdiction = jurisdiction

    def get_jurisdiction(self, code: JurisdictionCode) -> Jurisdiction:
        return self._jurisdiction


class _NoParameters:
    def get[T](self, family: str, tax_year: int, kind: ParameterKind[T]) -> ParameterDataset[T]:
        raise NotFoundError(f"no {family} dataset for tax year {tax_year}")


def service() -> TaxComputationService:
    code = JurisdictionCode("CA-ON")
    selection = CapabilitySelection(
        name="ca/ei_excluded_slips_net_income",
        params={},
        consumes={"slips": "ca/ei_excluded_slips"},
        produces={"output": "ca/ei_excluded_slips_net_income"},
    )
    manifest = Manifest(
        jurisdiction=code,
        version=1,
        valid_from_tax_year=2025,
        inputs=required_inputs(frozenset({"ca/ei_excluded_slips"})),
        forms=(
            Form(
                required=True,
                name=code.namespace.identifier("return"),
                instances=None,
                exports=("ca/ei_excluded_slips_net_income",),
                capabilities=(selection,),
            ),
        ),
    )
    artifacts = ArtifactRegistry()
    for kind in (EI_EXCLUDED_SLIPS, EI_EXCLUDED_SLIPS_NET_INCOME):
        artifacts.register(kind.identifier, kind)
    return TaxComputationService(
        _Jurisdictions(Jurisdiction(code=code, manifests=(manifest,))),
        _NoParameters(),
        CapabilityRegistry.shared(),
        artifacts,
    )


def test_a_computation_builds_the_capability_from_the_registry() -> None:
    composition = (
        service().compose(JurisdictionCode("CA-ON"), 2025).form("ca-on/return").composition
    )

    (built,) = composition.order
    assert isinstance(built, EiExcludedSlipsNetIncome)
    assert built.consumes == frozenset({EI_EXCLUDED_SLIPS})
    assert built.produces == frozenset({EI_EXCLUDED_SLIPS_NET_INCOME})


def test_a_computation_gives_the_total() -> None:
    worksheet = service().compute(JurisdictionCode("CA-ON"), 2025, slips("20000", "-5000"))[
        "ca-on/return"
    ][0]

    assert worksheet.get(EI_EXCLUDED_SLIPS_NET_INCOME).value == D("15000")
    assert isinstance(worksheet.producer_of(EI_EXCLUDED_SLIPS_NET_INCOME), EiExcludedSlipsNetIncome)
    assert worksheet.trace == (
        RecordTotalLine(
            EI_EXCLUDED_SLIPS_NET_INCOME,
            EI_EXCLUDED_SLIP_NET_INCOME,
            (D("20000"), D("-5000")),
            D("15000"),
        ),
    )


def test_a_computation_with_no_slips_gives_zero() -> None:
    worksheet = service().compute(JurisdictionCode("CA-ON"), 2025, slips())["ca-on/return"][0]

    assert worksheet.get(EI_EXCLUDED_SLIPS_NET_INCOME).value == D("0")
