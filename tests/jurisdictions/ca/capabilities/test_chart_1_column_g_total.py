"""Unit tests for the Chart 1 column G total of Form T657 (`ca/chart_1_column_g_total`).

Form T657, Chart 1 "Calculate your net capital losses of other years (line 14 of Step 2)": for
each printed year row, "Column A: Enter the total amount of net capital losses of other years
claimed for each year indicated from line 253 or 25300 of each return.", column B (a share of the
reserves included in capital gains for capital property disposed of before 1985), column C and
column D (amounts of Form T936), then "Column E (C – D) (If negative, enter "0")", "Column F (B +
E)" and "Column G (A – F) (If negative, enter "0")", and "Add the amounts in column G and enter
the result on line 14 of Step 2." The capability has one consumed slot `rows` (a record list with
a record for each printed year row: columns A, B, C and D, a cell the form prints N/A being left
0), one produced slot `total` and no parameter slot. For each row, column E is C less D, not below
0, column F is B plus E and column G is A less F, not below 0; the output is the sum of every
row's column G, exact: it has no dataset, so it never rounds. A row is worked alone: a row whose
column G is 0 does not lower another row's. It records one `NetCapitalLossesRowLine` for each row,
named by its position from 1, and then one `ItemsTotalLine`.

The figures are made up and worked by hand from the form's columns.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from decimal import Decimal
from types import MappingProxyType
from typing import Any, assert_type, cast

import pytest

import tax_engine.jurisdictions.ca
import tax_engine.jurisdictions.ca.capabilities as canada
from tax_engine.application.services.tax_computation import TaxComputationService
from tax_engine.domain.artifact import Artifact, ArtifactKind, ArtifactRegistry
from tax_engine.domain.capability import CapabilityRegistry
from tax_engine.domain.errors import InvalidCapabilityError, MissingArtifactError, NotFoundError
from tax_engine.domain.jurisdiction import Jurisdiction
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import CapabilitySelection, Form, Manifest
from tax_engine.domain.parameters.datasets import ParameterDataset
from tax_engine.domain.parameters.kind import ParameterKind
from tax_engine.domain.parameters.rate import RATE, Rate
from tax_engine.domain.parameters.rounding import NO_ROUNDING
from tax_engine.domain.record_list import RecordList
from tax_engine.domain.trace import ItemsTotalLine
from tax_engine.jurisdictions.ca.capabilities.chart_1_column_g_total import Chart1ColumnGTotal
from tax_engine.jurisdictions.ca.catalog import (
    T657_CHART_1_COLUMN_A,
    T657_CHART_1_COLUMN_B,
    T657_CHART_1_COLUMN_C,
    T657_CHART_1_COLUMN_D,
    T657_CHART_1_ROWS,
)
from tax_engine.jurisdictions.ca.trace import NetCapitalLossesRowLine
from tests.manifest_support import required_inputs

D = Decimal

# Made up for this test and not registered: the total the capability produces.
TOTAL = ArtifactKind("ex/column_g_total", Decimal)


def year_row(a: str = "0", b: str = "0", c: str = "0", d: str = "0") -> dict[Any, Any]:
    return {
        T657_CHART_1_COLUMN_A: D(a),
        T657_CHART_1_COLUMN_B: D(b),
        T657_CHART_1_COLUMN_C: D(c),
        T657_CHART_1_COLUMN_D: D(d),
    }


def rows(*records: dict[Any, Any]) -> Artifact[Any]:
    return Artifact(T657_CHART_1_ROWS, RecordList(T657_CHART_1_ROWS.fields, records))


def capability() -> Chart1ColumnGTotal:
    return Chart1ColumnGTotal(T657_CHART_1_ROWS, TOTAL)


def total(*records: dict[Any, Any]) -> Decimal:
    (output,) = capability().compute((rows(*records),)).outputs
    assert output.kind == TOTAL
    value: Decimal = output.value
    return value


def test_is_registered_as_ca_chart_1_column_g_total() -> None:
    assert tax_engine.jurisdictions.ca.capabilities is canada
    assert CapabilityRegistry.shared().get("ca/chart_1_column_g_total") is Chart1ColumnGTotal


def test_is_exported_from_the_canada_capabilities_package() -> None:
    assert canada.NAMESPACE == "ca"
    assert "chart_1_column_g_total" in canada.__all__
    assert canada.chart_1_column_g_total.Chart1ColumnGTotal is Chart1ColumnGTotal


def test_declares_its_contract() -> None:
    assert capability().consumes == frozenset({T657_CHART_1_ROWS})
    assert capability().produces == frozenset({TOTAL})
    assert "consumes" not in vars(Chart1ColumnGTotal)
    assert "produces" not in vars(Chart1ColumnGTotal)


def test_declares_its_slots() -> None:
    assert Chart1ColumnGTotal.PARAMETERS == {}
    assert Chart1ColumnGTotal.CONSUMES == {"rows": RecordList}
    assert Chart1ColumnGTotal.PRODUCES == {"total": Decimal}
    assert not Chart1ColumnGTotal.is_list_slot("rows")
    for slots in (
        Chart1ColumnGTotal.PARAMETERS,
        Chart1ColumnGTotal.CONSUMES,
        Chart1ColumnGTotal.PRODUCES,
    ):
        assert isinstance(slots, MappingProxyType)
        with pytest.raises(TypeError):
            cast(Any, slots)["extra"] = Decimal


def test_its_slots_are_typed_as_read_only_mappings() -> None:
    assert_type(Chart1ColumnGTotal.CONSUMES, Mapping[str, type])
    assert_type(Chart1ColumnGTotal.PRODUCES, Mapping[str, type])


def test_is_built_from_its_slot_names_as_keywords() -> None:
    wired = Chart1ColumnGTotal(rows=T657_CHART_1_ROWS, total=TOTAL)

    (output,) = wired.compute((rows(year_row(a="100")),)).outputs

    assert output == Artifact(TOTAL, D("100"))


def test_takes_no_parameter_dataset() -> None:
    with pytest.raises(TypeError):
        Chart1ColumnGTotal(T657_CHART_1_ROWS, TOTAL, object())  # type: ignore[call-arg]


def test_mypy_rejects_a_dataset_it_has_no_slot_for() -> None:
    def wire() -> None:  # type-checked, never run
        # It has no parameter slot, so a dataset is one argument too many; the ignore fails
        # under mypy (warn_unused_ignores) if it is ever accepted.
        rate = ParameterDataset(
            "ex/some_rate", 2025, RATE, Rate(D("0.5")), NO_ROUNDING, ("https://example.org/r",)
        )
        Chart1ColumnGTotal(T657_CHART_1_ROWS, TOTAL, rate)  # type: ignore[call-arg]

    assert callable(wire)


def test_is_not_generic_over_artifacts() -> None:
    assert not getattr(Chart1ColumnGTotal, "__type_params__", ())
    assert not getattr(Chart1ColumnGTotal, "__parameters__", ())


def test_refuses_a_money_kind_for_its_record_list() -> None:
    with pytest.raises(InvalidCapabilityError, match="Chart1ColumnGTotal") as raised:
        Chart1ColumnGTotal(ArtifactKind("ex/not_a_list", Decimal), TOTAL)  # type: ignore[arg-type]

    assert "'rows'" in str(raised.value)


def test_refuses_a_count_kind_for_its_total() -> None:
    with pytest.raises(InvalidCapabilityError, match="Chart1ColumnGTotal") as raised:
        Chart1ColumnGTotal(T657_CHART_1_ROWS, ArtifactKind("ex/a_count", int))  # type: ignore[arg-type]

    assert "'total'" in str(raised.value)


def test_needs_its_record_list() -> None:
    with pytest.raises(MissingArtifactError):
        capability().compute(())


# --- computing ----------------------------------------------------------------------------------


def test_a_row_of_a_1985_to_1987_year_is_column_a_less_column_b() -> None:
    # Columns C and D are N/A for 1985 to 1987, so 0: E is 0, F is B (1000) and G is 3000 - 1000.
    assert total(year_row(a="3000", b="1000")) == D("2000")


def test_a_1992_row_is_a_less_c_less_d() -> None:
    # Column B is N/A for 1992, so 0: E is 4000 - 1500 = 2500, F is 0 + 2500 and G is 5000 - 2500.
    assert total(year_row(a="5000", c="4000", d="1500")) == D("2500")


def test_column_e_is_not_below_0_when_column_d_is_above_column_c() -> None:
    # E is 0 (300 - 500, floored), F is 0 and G is the whole of column A, 1000.
    assert total(year_row(a="1000", c="300", d="500")) == D("1000")


def test_column_g_is_not_below_0_when_column_f_is_above_column_a() -> None:
    # E is 3000 - 500 = 2500, F is 2500 and A (1000) - 2500 is floored at 0.
    assert total(year_row(a="1000", c="3000", d="500")) == D("0")


def test_column_g_is_0_when_column_f_equals_column_a() -> None:
    assert total(year_row(a="2500", b="500", c="2500", d="500")) == D("0")


def test_columns_b_and_e_are_both_taken_off_column_a() -> None:
    # E is 2000 - 500 = 1500, F is 1000 + 1500 = 2500 and G is 6000 - 2500 = 3500.
    assert total(year_row(a="6000", b="1000", c="2000", d="500")) == D("3500")


def test_an_empty_row_is_0() -> None:
    assert total(year_row()) == D("0")


def test_keeps_the_cents_and_never_rounds() -> None:
    # E is 30.20 - 10.10 = 20.10, F is 0.05 + 20.10 = 20.15 and G is 100.10 - 20.15 = 79.95.
    assert total(year_row(a="100.10", b="0.05", c="30.20", d="10.10")) == D("79.95")
    assert total(year_row(a="0.015", b="0.005")) == D("0.010")


def test_totals_the_column_g_of_each_row() -> None:
    # 1985 to 1987: 3000 - 1000 = 2000. 1992: 5000 - (0 + 2500) = 2500. 2001 to 2024: E is
    # 18000 - 0, G is 20000 - 18000 = 2000. A row whose column F is above A: 0.
    records = (
        year_row(a="3000", b="1000"),
        year_row(a="5000", c="4000", d="1500"),
        year_row(a="20000", c="18000"),
        year_row(a="1000", c="3000", d="500"),
    )

    assert total(*records) == D("6500")


def test_a_row_is_worked_alone_a_row_at_0_does_not_lower_another() -> None:
    records = (
        year_row(a="1000", c="3000", d="500"),
        year_row(a="2000", b="1500"),
    )

    assert total(*records) == D("500")


def test_has_one_output() -> None:
    (output,) = capability().compute((rows(year_row(a="5")),)).outputs

    assert output == Artifact(TOTAL, D("5"))


def test_compute_is_repeatable() -> None:
    inputs = (rows(year_row(a="3000", b="1000"), year_row(a="5000", c="4000", d="1500")),)

    assert capability().compute(inputs) == capability().compute(inputs)


def test_no_rows_total_nothing() -> None:
    result = capability().compute((rows(),))

    assert result.outputs == (Artifact(TOTAL, D("0")),)
    assert result.trace == (ItemsTotalLine(output=TOTAL, items=(), total=D("0")),)


# --- trace --------------------------------------------------------------------------------------


def test_the_last_trace_line_amount_is_the_output() -> None:
    result = capability().compute((rows(year_row(a="400"), year_row(a="500")),))

    assert result.trace[-1].amount == D("900")


def test_records_each_rows_columns_by_its_position_then_the_total() -> None:
    records = (
        year_row(a="3000", b="1000"),
        year_row(a="5000", c="4000", d="1500"),
        year_row(a="1000", c="3000", d="500"),
    )

    result = capability().compute((rows(*records),))

    assert result.trace == (
        NetCapitalLossesRowLine(
            output=TOTAL,
            position=1,
            column_a=D("3000"),
            column_b=D("1000"),
            column_c=D("0"),
            column_d=D("0"),
            column_e=D("0"),
            column_f=D("1000"),
            column_g=D("2000"),
        ),
        NetCapitalLossesRowLine(
            output=TOTAL,
            position=2,
            column_a=D("5000"),
            column_b=D("0"),
            column_c=D("4000"),
            column_d=D("1500"),
            column_e=D("2500"),
            column_f=D("2500"),
            column_g=D("2500"),
        ),
        NetCapitalLossesRowLine(
            output=TOTAL,
            position=3,
            column_a=D("1000"),
            column_b=D("0"),
            column_c=D("3000"),
            column_d=D("500"),
            column_e=D("2500"),
            column_f=D("2500"),
            column_g=D("0"),
        ),
        ItemsTotalLine(
            output=TOTAL,
            items=((1, D("2000")), (2, D("2500")), (3, D("0"))),
            total=D("4500"),
        ),
    )


def test_a_row_line_amount_is_column_g() -> None:
    line = NetCapitalLossesRowLine(
        TOTAL, 1, D("5000"), D("0"), D("4000"), D("1500"), D("2500"), D("2500"), D("2500")
    )

    assert line.amount == D("2500")


def test_a_row_line_is_immutable_and_compares_by_its_fields() -> None:
    line = NetCapitalLossesRowLine(
        TOTAL, 1, D("5000"), D("0"), D("4000"), D("1500"), D("2500"), D("2500"), D("2500")
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        line.column_g = D("0")  # type: ignore[misc]
    assert line == dataclasses.replace(line)
    assert line != dataclasses.replace(line, position=2)
    assert line != dataclasses.replace(line, column_g=D("0"))


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
        name="ca/chart_1_column_g_total",
        params={},
        consumes={"rows": "ca/t657_chart_1_rows"},
        produces={"total": "ex/column_g_total"},
    )
    manifest = Manifest(
        jurisdiction=code,
        version=1,
        valid_from_tax_year=2025,
        inputs=required_inputs(frozenset({"ca/t657_chart_1_rows"})),
        forms=(
            Form(
                required=True,
                name=code.namespace.identifier("return"),
                instances=None,
                exports=("ex/column_g_total",),
                capabilities=(selection,),
            ),
        ),
    )
    artifacts = ArtifactRegistry()
    for kind in (T657_CHART_1_ROWS, TOTAL):
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
    assert isinstance(built, Chart1ColumnGTotal)
    assert built.consumes == frozenset({T657_CHART_1_ROWS})
    assert built.produces == frozenset({TOTAL})


def test_a_computation_gives_the_total_of_the_column_gs() -> None:
    records = (year_row(a="3000", b="1000"), year_row(a="5000", c="4000", d="1500"))

    worksheet = service().compute(JurisdictionCode("CA-ON"), 2025, rows(*records))["ca-on/return"][
        0
    ]

    assert worksheet.get(TOTAL).value == D("4500")
    assert isinstance(worksheet.producer_of(TOTAL), Chart1ColumnGTotal)


def test_a_computation_with_no_rows_gives_zero() -> None:
    worksheet = service().compute(JurisdictionCode("CA-ON"), 2025, rows())["ca-on/return"][0]

    assert worksheet.get(TOTAL).value == D("0")
