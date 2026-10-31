"""Unit tests for the Chart A row C total of Form T2222 (`ca/chart_a_row_c_total`).

Form T2222, Step 3, Chart A: "Row B: Enter the name of everyone (including yourself) who is
claiming a deduction for trips taken by the individual in row A and the total portion of the
$1,200 standard amount allocated by each claimant for all trips taken by that individual." and
"Row C: Enter the total of all amounts in row B. This total cannot be more than $1,200." The
capability has one parameter slot `maximum` (an `amount` dataset, the $1,200), one consumed slot
`individuals` (a record list with a record for each individual: the individual and the three row B
amounts) and one produced slot `total`. For each individual, row C is the sum of the three
amounts; a row C above the maximum is not capped but an input error, `InputAboveBoundError`,
reading "This total cannot be more than $1,200." and naming the item by its position from 1. The
output is the sum of every individual's row C, exact: it never rounds. It records one
`ItemSumLine` for each individual, named by its position, and then one `ItemsTotalLine`.

The figures are CRA's own, from the form's example 4.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from types import MappingProxyType
from typing import Any, assert_type, cast

import pytest

import tax_engine.jurisdictions.ca
import tax_engine.jurisdictions.ca.capabilities as canada
from tax_engine.adapters.outbound.yaml_parameters import YamlParameterSource
from tax_engine.application.services.tax_computation import TaxComputationService
from tax_engine.domain.artifact import Artifact, ArtifactKind, ArtifactRegistry
from tax_engine.domain.capability import CapabilityRegistry
from tax_engine.domain.errors import (
    InputAboveBoundError,
    InvalidCapabilityError,
    MissingArtifactError,
    NotFoundError,
)
from tax_engine.domain.jurisdiction import Jurisdiction
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import CapabilitySelection, Form, Manifest
from tax_engine.domain.parameters.amount import AMOUNT, Amount
from tax_engine.domain.parameters.datasets import ParameterDataset
from tax_engine.domain.parameters.kind import ParameterKind
from tax_engine.domain.parameters.rate import RATE, Rate
from tax_engine.domain.parameters.rounding import NO_ROUNDING, RoundingMode, RoundTo
from tax_engine.domain.record_list import RecordList
from tax_engine.domain.trace import ItemsTotalLine, ItemSumLine
from tax_engine.jurisdictions.ca.capabilities.chart_a_row_c_total import ChartARowCTotal
from tax_engine.jurisdictions.ca.catalog import (
    STANDARD_AMOUNT_ALLOCATED_1,
    STANDARD_AMOUNT_ALLOCATED_2,
    STANDARD_AMOUNT_ALLOCATED_3,
    TRAVEL_INDIVIDUAL,
    TRAVEL_INDIVIDUALS,
)
from tests.manifest_support import required_inputs

D = Decimal
CENT = RoundTo(D("0.01"), RoundingMode.HALF_UP)
MESSAGE = r"This total cannot be more than \$1,200\."

# Made up for this test and not registered: the total the capability produces.
TOTAL = ArtifactKind("ex/allocated_total", Decimal)


def maximum(value: str = "1200") -> ParameterDataset[Amount]:
    """By default the form's $1,200, as an amount dataset."""
    return ParameterDataset(
        "ex/some_standard_amount", 2025, AMOUNT, Amount(D(value)), CENT, ("https://example.org/p",)
    )


def individual(
    number: int, first: str = "0", second: str = "0", third: str = "0"
) -> dict[Any, Any]:
    return {
        TRAVEL_INDIVIDUAL: number,
        STANDARD_AMOUNT_ALLOCATED_1: D(first),
        STANDARD_AMOUNT_ALLOCATED_2: D(second),
        STANDARD_AMOUNT_ALLOCATED_3: D(third),
    }


def individuals(*rows: dict[Any, Any]) -> Artifact[Any]:
    return Artifact(TRAVEL_INDIVIDUALS, RecordList(TRAVEL_INDIVIDUALS.fields, rows))


def capability(dataset: ParameterDataset[Amount] | None = None) -> ChartARowCTotal:
    return ChartARowCTotal(dataset or maximum(), TRAVEL_INDIVIDUALS, TOTAL)


def total(*rows: dict[Any, Any], dataset: ParameterDataset[Amount] | None = None) -> Decimal:
    (output,) = capability(dataset).compute((individuals(*rows),)).outputs
    assert output.kind == TOTAL
    value: Decimal = output.value
    return value


def test_is_registered_as_ca_chart_a_row_c_total() -> None:
    assert tax_engine.jurisdictions.ca.capabilities is canada
    assert CapabilityRegistry.shared().get("ca/chart_a_row_c_total") is ChartARowCTotal


def test_is_exported_from_the_canada_capabilities_package() -> None:
    assert canada.NAMESPACE == "ca"
    assert "chart_a_row_c_total" in canada.__all__
    assert canada.chart_a_row_c_total.ChartARowCTotal is ChartARowCTotal


def test_declares_its_contract() -> None:
    assert capability().consumes == frozenset({TRAVEL_INDIVIDUALS})
    assert capability().produces == frozenset({TOTAL})
    assert "consumes" not in vars(ChartARowCTotal)
    assert "produces" not in vars(ChartARowCTotal)


def test_declares_its_slots() -> None:
    assert ChartARowCTotal.PARAMETERS == {"maximum": AMOUNT}
    assert ChartARowCTotal.CONSUMES == {"individuals": RecordList}
    assert ChartARowCTotal.PRODUCES == {"total": Decimal}
    assert not ChartARowCTotal.is_list_slot("individuals")
    for slots in (ChartARowCTotal.PARAMETERS, ChartARowCTotal.CONSUMES, ChartARowCTotal.PRODUCES):
        assert isinstance(slots, MappingProxyType)
        with pytest.raises(TypeError):
            cast(Any, slots)["extra"] = Decimal


def test_its_slots_are_typed_as_read_only_mappings() -> None:
    assert_type(ChartARowCTotal.PARAMETERS, Mapping[str, ParameterKind[Amount]])
    assert_type(ChartARowCTotal.CONSUMES, Mapping[str, type])
    assert_type(ChartARowCTotal.PRODUCES, Mapping[str, type])


def test_leaves_its_contract_to_the_base() -> None:
    assert "consumes" not in vars(ChartARowCTotal)
    assert "produces" not in vars(ChartARowCTotal)


def test_is_built_from_its_slot_names_as_keywords() -> None:
    wired = ChartARowCTotal(maximum=maximum(), individuals=TRAVEL_INDIVIDUALS, total=TOTAL)

    (output,) = wired.compute((individuals(individual(1, "100")),)).outputs

    assert output == Artifact(TOTAL, D("100"))


def test_takes_no_separate_rounding_argument() -> None:
    with pytest.raises(TypeError):
        ChartARowCTotal(  # type: ignore[call-arg]
            maximum(), TRAVEL_INDIVIDUALS, TOTAL, CENT
        )


def test_mypy_rejects_a_dataset_of_another_parameter_kind() -> None:
    def wire() -> None:  # type-checked, never run
        # A rate dataset is not a ParameterDataset[Amount]; the ignore fails under mypy
        # (warn_unused_ignores) if it is ever accepted.
        rate = ParameterDataset(
            "ex/some_rate", 2025, RATE, Rate(D("0.5")), NO_ROUNDING, ("https://example.org/r",)
        )
        ChartARowCTotal(
            rate,  # type: ignore[arg-type]
            TRAVEL_INDIVIDUALS,
            TOTAL,
        )

    assert callable(wire)


def test_is_not_generic_over_artifacts() -> None:
    assert not getattr(ChartARowCTotal, "__type_params__", ())
    assert not getattr(ChartARowCTotal, "__parameters__", ())


# --- computing ----------------------------------------------------------------------------------


def test_a_row_c_is_the_sum_of_the_three_row_b_amounts() -> None:
    assert total(individual(1, "400", "500", "300")) == D("1200")
    assert total(individual(1, "100.10", "200.20", "300.30")) == D("600.60")


def test_totals_the_row_c_of_each_individual_of_example_4() -> None:
    # Chart A as the example completes it: Individual 1 (yourself) $0, Individual 2 (your spouse)
    # $1,200 and Individual 3 (your child) $1,200, row C $0, $1,200 and $1,200.
    rows = (individual(1, "0"), individual(2, "1200"), individual(3, "1200"))

    assert total(*rows) == D("2400")


def test_the_limit_is_for_each_individual_not_all_of_them() -> None:
    # Two individuals at $1,200 each: 2,400 in all, which a pooled limit of 1,200 would refuse.
    assert total(individual(1, "1200"), individual(2, "600", "600")) == D("2400")


def test_a_row_c_of_exactly_1200_is_allowed() -> None:
    assert total(individual(1, "400", "400", "400")) == D("1200")
    assert total(individual(1, "1200.00")) == D("1200")


def test_refuses_a_row_c_above_1200_as_an_input_error_naming_the_item() -> None:
    with pytest.raises(InputAboveBoundError, match=rf"item 1.*{MESSAGE}"):
        total(individual(1, "700", "600", "0"))


def test_refuses_the_second_individuals_row_c_naming_its_position() -> None:
    with pytest.raises(InputAboveBoundError, match=rf"item 2.*{MESSAGE}"):
        total(individual(1, "1200"), individual(2, "400", "400", "400.01"))


def test_refuses_a_row_c_one_cent_above_1200() -> None:
    with pytest.raises(InputAboveBoundError, match=MESSAGE):
        total(individual(1, "1200.01"))


def test_the_form_text_is_the_real_datasets_message() -> None:
    from tax_engine.registrations import JURISDICTIONS

    dataset = YamlParameterSource(JURISDICTIONS.roots()).get(
        "ca/northern_travel_standard_amount", 2025, AMOUNT
    )

    with pytest.raises(InputAboveBoundError, match=MESSAGE):
        total(individual(1, "700", "600"), dataset=dataset)


def test_reads_its_maximum_from_the_dataset() -> None:
    assert total(individual(1, "600", "400"), dataset=maximum("1000")) == D("1000")
    with pytest.raises(InputAboveBoundError, match="item 1"):
        total(individual(1, "600", "400.01"), dataset=maximum("1000"))
    assert total(individual(1, "1300"), dataset=maximum("1500")) == D("1300")


def test_has_one_output() -> None:
    (output,) = capability().compute((individuals(individual(1, "5")),)).outputs

    assert output == Artifact(TOTAL, D("5"))


def test_compute_is_repeatable() -> None:
    inputs = (individuals(individual(1, "400", "500", "300")),)

    assert capability().compute(inputs) == capability().compute(inputs)


def test_no_individuals_total_nothing() -> None:
    result = capability().compute((individuals(),))

    assert result.outputs == (Artifact(TOTAL, D("0")),)
    assert result.trace == (ItemsTotalLine(output=TOTAL, items=(), total=D("0")),)


# --- trace --------------------------------------------------------------------------------------


def test_the_last_trace_line_amount_is_the_output() -> None:
    result = capability().compute((individuals(individual(1, "400"), individual(2, "500")),))

    assert result.trace[-1].amount == D("900")


def test_records_each_individuals_row_c_by_its_position_then_the_total() -> None:
    rows = (individual(1, "0"), individual(2, "400", "500", "300"), individual(3, "1200"))

    result = capability().compute((individuals(*rows),))

    assert result.trace == (
        ItemSumLine(
            output=TOTAL,
            position=1,
            parts=(
                (STANDARD_AMOUNT_ALLOCATED_1, D("0")),
                (STANDARD_AMOUNT_ALLOCATED_2, D("0")),
                (STANDARD_AMOUNT_ALLOCATED_3, D("0")),
            ),
            total=D("0"),
        ),
        ItemSumLine(
            output=TOTAL,
            position=2,
            parts=(
                (STANDARD_AMOUNT_ALLOCATED_1, D("400")),
                (STANDARD_AMOUNT_ALLOCATED_2, D("500")),
                (STANDARD_AMOUNT_ALLOCATED_3, D("300")),
            ),
            total=D("1200"),
        ),
        ItemSumLine(
            output=TOTAL,
            position=3,
            parts=(
                (STANDARD_AMOUNT_ALLOCATED_1, D("1200")),
                (STANDARD_AMOUNT_ALLOCATED_2, D("0")),
                (STANDARD_AMOUNT_ALLOCATED_3, D("0")),
            ),
            total=D("1200"),
        ),
        ItemsTotalLine(
            output=TOTAL,
            items=((1, D("0")), (2, D("1200")), (3, D("1200"))),
            total=D("2400"),
        ),
    )


def test_refuses_a_money_kind_for_its_record_list() -> None:
    with pytest.raises(InvalidCapabilityError, match="ChartARowCTotal") as raised:
        ChartARowCTotal(maximum(), ArtifactKind("ex/not_a_list", Decimal), TOTAL)  # type: ignore[arg-type]

    assert "'individuals'" in str(raised.value)


def test_refuses_a_count_kind_for_its_total() -> None:
    with pytest.raises(InvalidCapabilityError, match="ChartARowCTotal") as raised:
        ChartARowCTotal(maximum(), TRAVEL_INDIVIDUALS, ArtifactKind("ex/a_count", int))  # type: ignore[arg-type]

    assert "'total'" in str(raised.value)


def test_needs_its_record_list() -> None:
    with pytest.raises(MissingArtifactError):
        capability().compute(())


# --- through TaxComputationService --------------------------------------------------------------


class _Jurisdictions:
    def __init__(self, jurisdiction: Jurisdiction) -> None:
        self._jurisdiction = jurisdiction

    def get_jurisdiction(self, code: JurisdictionCode) -> Jurisdiction:
        return self._jurisdiction


class _Parameters:
    def __init__(self, dataset: ParameterDataset[Amount]) -> None:
        self._dataset = dataset

    def get[T](self, family: str, tax_year: int, kind: ParameterKind[T]) -> ParameterDataset[T]:
        if (family, tax_year, kind) != (self._dataset.family, 2025, AMOUNT):
            raise NotFoundError(f"no {family} dataset for tax year {tax_year}")
        return cast(ParameterDataset[T], self._dataset)


def service(dataset: ParameterDataset[Amount] | None = None) -> TaxComputationService:
    dataset = dataset or maximum()
    code = JurisdictionCode("CA-ON")
    selection = CapabilitySelection(
        name="ca/chart_a_row_c_total",
        params={"maximum": dataset.family},
        consumes={"individuals": "ca/travel_individuals"},
        produces={"total": "ex/allocated_total"},
    )
    manifest = Manifest(
        jurisdiction=code,
        version=1,
        valid_from_tax_year=2025,
        inputs=required_inputs(frozenset({"ca/travel_individuals"})),
        forms=(
            Form(
                required=True,
                name=code.namespace.identifier("return"),
                instances=None,
                exports=("ex/allocated_total",),
                capabilities=(selection,),
            ),
        ),
    )
    artifacts = ArtifactRegistry()
    for kind in (TRAVEL_INDIVIDUALS, TOTAL):
        artifacts.register(kind.identifier, kind)
    return TaxComputationService(
        _Jurisdictions(Jurisdiction(code=code, manifests=(manifest,))),
        _Parameters(dataset),
        CapabilityRegistry.shared(),
        artifacts,
    )


def test_a_computation_builds_the_capability_from_the_registry_and_its_dataset() -> None:
    composition = (
        service().compose(JurisdictionCode("CA-ON"), 2025).form("ca-on/return").composition
    )

    (built,) = composition.order
    assert isinstance(built, ChartARowCTotal)
    assert built.consumes == frozenset({TRAVEL_INDIVIDUALS})
    assert built.produces == frozenset({TOTAL})


def test_a_computation_gives_the_total_of_the_row_cs() -> None:
    rows = (individual(1, "0"), individual(2, "400", "500", "300"))

    worksheet = service().compute(JurisdictionCode("CA-ON"), 2025, individuals(*rows))[
        "ca-on/return"
    ][0]

    assert worksheet.get(TOTAL).value == D("1200")
    assert isinstance(worksheet.producer_of(TOTAL), ChartARowCTotal)


def test_a_computation_with_no_individuals_gives_zero() -> None:
    worksheet = service().compute(JurisdictionCode("CA-ON"), 2025, individuals())["ca-on/return"][0]

    assert worksheet.get(TOTAL).value == D("0")


def test_a_computation_refuses_a_row_c_above_the_datasets_maximum() -> None:
    with pytest.raises(InputAboveBoundError, match="item 1"):
        service(maximum("1000")).compute(
            JurisdictionCode("CA-ON"), 2025, individuals(individual(1, "600", "400.01"))
        )
