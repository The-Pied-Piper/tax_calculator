"""Unit tests for ShortTermRentalNonCompliantCcaByClass, the column 22 totals of Form T776.

Form T776, Chart B: "Column 1: Class number"; "Column 7 ***: Non-compliant amount (column 4
multiplied by column 5 divided by column 6)"; "*** For each class, add the amounts from column 7
of Chart B and enter each total in column 22 of Area A, in the respective row."; Area A, "Column
22: Non-compliant amount of CCA (see Chart B below)".

Its slots: one parameter slot, `rounding` (a `rounding_only` dataset: the rule for column 7), one
consumed slot `units` (the same record list as line C's capability) and one produced slot `output`,
a record list kind of exactly the class number and the non-compliant CCA (column 22). Column 7 is
worked as in `ShortTermRentalNonCompliantCca`, each row rounded once; the output has one record for
each distinct class, in the order the classes first appear, holding the total of that class's
rounded amounts. It records one `ShortTermRentalNonCompliantCcaByClassLine` per class, by position
from 1, and no total.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from types import MappingProxyType
from typing import Any, assert_type, cast

import pytest

import tax_engine.jurisdictions.ca.capabilities as ca_capabilities
from tax_engine.application.services.tax_computation import TaxComputationService
from tax_engine.domain.artifact import Artifact, ArtifactRegistry
from tax_engine.domain.capability import CapabilityRegistry
from tax_engine.domain.errors import (
    InvalidCapabilityError,
    MissingArtifactError,
    NotFoundError,
    ValidationError,
)
from tax_engine.domain.jurisdiction import Jurisdiction
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import CapabilitySelection, Form, Manifest
from tax_engine.domain.parameters.datasets import ParameterDataset
from tax_engine.domain.parameters.kind import ParameterKind
from tax_engine.domain.parameters.rounding import NO_ROUNDING, RoundingMode, RoundTo
from tax_engine.domain.parameters.rounding_only import ROUNDING_ONLY, RoundingOnly
from tax_engine.domain.record_list import RecordList, RecordListKind
from tax_engine.jurisdictions.ca.capabilities import (
    short_term_rental_non_compliant_cca_by_class as rental_cca,
)
from tax_engine.jurisdictions.ca.capabilities.short_term_rental_non_compliant_cca import (
    ShortTermRentalNonCompliantCca,
)
from tax_engine.jurisdictions.ca.catalog import (
    CCA_CLASS_NUMBER,
    CCA_UCC_AT_END,
    NON_COMPLIANT_CCA,
    SHORT_TERM_RENTAL_CCA_UNITS,
)
from tax_engine.jurisdictions.ca.trace import ShortTermRentalNonCompliantCcaByClassLine
from tests.jurisdictions.ca.capabilities.short_term_rental_cca import (
    BY_CLASS,
    CENT,
    CLASS_8_ROW,
    LINE_9367,
    THIRD_ROW,
    TICKET_ROW,
    D,
    Row,
    rounding,
    units,
)
from tests.manifest_support import required_inputs


def capability(
    dataset: ParameterDataset[RoundingOnly] | None = None,
) -> rental_cca.ShortTermRentalNonCompliantCcaByClass:
    return rental_cca.ShortTermRentalNonCompliantCcaByClass(
        dataset or rounding(), SHORT_TERM_RENTAL_CCA_UNITS, BY_CLASS
    )


def by_class(
    *rows: Row, dataset: ParameterDataset[RoundingOnly] | None = None
) -> list[tuple[Any, Any]]:
    """(class number, column 22) of each output record, in order."""
    (output,) = capability(dataset).compute((units(*rows),)).outputs
    assert output.kind is BY_CLASS
    value = output.value
    assert isinstance(value, RecordList)
    return [(record[CCA_CLASS_NUMBER], record[NON_COMPLIANT_CCA]) for record in value.records]


def test_is_registered_as_ca_short_term_rental_non_compliant_cca_by_class() -> None:
    assert (
        CapabilityRegistry.shared().get("ca/short_term_rental_non_compliant_cca_by_class")
        is rental_cca.ShortTermRentalNonCompliantCcaByClass
    )


def test_is_exported_from_the_ca_capabilities_package() -> None:
    assert "short_term_rental_non_compliant_cca_by_class" in ca_capabilities.__all__
    assert (
        ca_capabilities.short_term_rental_non_compliant_cca_by_class.ShortTermRentalNonCompliantCcaByClass
        is rental_cca.ShortTermRentalNonCompliantCcaByClass
    )


def test_declares_its_contract() -> None:
    assert capability().consumes == frozenset({SHORT_TERM_RENTAL_CCA_UNITS})
    assert capability().produces == frozenset({BY_CLASS})


def test_leaves_its_contract_to_the_base() -> None:
    assert "consumes" not in vars(rental_cca.ShortTermRentalNonCompliantCcaByClass)
    assert "produces" not in vars(rental_cca.ShortTermRentalNonCompliantCcaByClass)


def test_declares_its_slots() -> None:
    assert rental_cca.ShortTermRentalNonCompliantCcaByClass.PARAMETERS == {
        "rounding": ROUNDING_ONLY,
    }
    assert rental_cca.ShortTermRentalNonCompliantCcaByClass.CONSUMES == {"units": RecordList}
    assert rental_cca.ShortTermRentalNonCompliantCcaByClass.PRODUCES == {"output": RecordList}


def test_its_slots_are_read_only() -> None:
    for each in (
        rental_cca.ShortTermRentalNonCompliantCcaByClass.PARAMETERS,
        rental_cca.ShortTermRentalNonCompliantCcaByClass.CONSUMES,
        rental_cca.ShortTermRentalNonCompliantCcaByClass.PRODUCES,
    ):
        assert isinstance(each, MappingProxyType)
        with pytest.raises(TypeError):
            cast(Any, each)["extra"] = Decimal


def test_its_slots_are_typed_as_read_only_mappings() -> None:
    assert_type(
        rental_cca.ShortTermRentalNonCompliantCcaByClass.PARAMETERS,
        Mapping[str, ParameterKind[Any]],
    )
    assert_type(rental_cca.ShortTermRentalNonCompliantCcaByClass.CONSUMES, Mapping[str, type])
    assert_type(rental_cca.ShortTermRentalNonCompliantCcaByClass.PRODUCES, Mapping[str, type])


def test_is_built_from_its_slot_names_as_keywords() -> None:
    wired = rental_cca.ShortTermRentalNonCompliantCcaByClass(
        rounding=rounding(),
        units=SHORT_TERM_RENTAL_CCA_UNITS,
        output=BY_CLASS,
    )

    (output,) = wired.compute((units(TICKET_ROW),)).outputs
    assert output == Artifact(
        BY_CLASS,
        RecordList(BY_CLASS.fields, [{CCA_CLASS_NUMBER: D("1"), NON_COMPLIANT_CCA: D("300.00")}]),
    )


def test_takes_no_separate_rounding_argument() -> None:
    with pytest.raises(TypeError):
        rental_cca.ShortTermRentalNonCompliantCcaByClass(  # type: ignore[call-arg]
            rounding(), SHORT_TERM_RENTAL_CCA_UNITS, BY_CLASS, CENT
        )


def test_rejects_a_money_kind_for_its_output() -> None:
    with pytest.raises(
        InvalidCapabilityError, match="ShortTermRentalNonCompliantCcaByClass.*'output'"
    ):
        rental_cca.ShortTermRentalNonCompliantCcaByClass(
            rounding(),
            SHORT_TERM_RENTAL_CCA_UNITS,
            LINE_9367,  # type: ignore[arg-type]
        )


def test_an_output_list_of_other_fields_fails_when_its_artifact_is_built() -> None:
    other = RecordListKind("ex/other_by_class", fields=(CCA_CLASS_NUMBER, CCA_UCC_AT_END))
    wired = rental_cca.ShortTermRentalNonCompliantCcaByClass(
        rounding(), SHORT_TERM_RENTAL_CCA_UNITS, other
    )

    with pytest.raises(TypeError, match="ex/other_by_class must be a record list of fields"):
        wired.compute((units(TICKET_ROW),))


def test_its_output_holds_the_class_number_and_the_non_compliant_cca() -> None:
    (output,) = capability().compute((units(TICKET_ROW),)).outputs

    assert output.value.fields == (CCA_CLASS_NUMBER, NON_COMPLIANT_CCA)


# --- computing ----------------------------------------------------------------------------------


def test_no_rows_give_an_empty_list() -> None:
    (output,) = capability().compute((units(),)).outputs

    assert output.value.records == ()
    assert output.value.fields == BY_CLASS.fields


def test_one_row_gives_its_class_and_column_7() -> None:
    assert by_class(TICKET_ROW) == [(D("1"), D("300.00"))]


def test_the_rows_of_one_class_are_added_into_one_record() -> None:
    # Return AV: class 1 is 300.00 + 33.33 = 333.33, class 8 is 250.00.
    assert by_class(TICKET_ROW, THIRD_ROW, CLASS_8_ROW) == [
        (D("1"), D("333.33")),
        (D("8"), D("250.00")),
    ]


def test_a_class_whose_rows_are_apart_is_still_one_record() -> None:
    assert by_class(TICKET_ROW, CLASS_8_ROW, THIRD_ROW) == [
        (D("1"), D("333.33")),
        (D("8"), D("250.00")),
    ]


def test_the_classes_come_in_the_order_they_first_appear() -> None:
    assert by_class(CLASS_8_ROW, TICKET_ROW, THIRD_ROW) == [
        (D("8"), D("250.00")),
        (D("1"), D("333.33")),
    ]


def test_each_row_is_rounded_once_before_it_is_added_to_its_class() -> None:
    # Three rows of 33.333... are 33.33 each: 99.99, not the rounded exact sum 100.00.
    assert by_class(THIRD_ROW, THIRD_ROW, THIRD_ROW) == [(D("1"), D("99.99"))]


def test_a_decimal_class_number_is_its_own_class() -> None:
    assert by_class(("10", "100", 1, 2), ("10.1", "100", 1, 2), ("10", "100", 1, 2)) == [
        (D("10"), D("100.00")),
        (D("10.1"), D("50.00")),
    ]


def test_the_class_number_is_kept_as_given() -> None:
    ((number, _),) = by_class(("10.1", "100", 1, 2))

    assert str(number) == "10.1"


def test_a_class_with_no_non_compliant_days_gives_a_plain_zero() -> None:
    ((_, amount),) = by_class(("1", "900", 0, 90))

    assert amount == D("0")
    assert not amount.is_signed()


def test_the_rounding_rule_comes_from_the_dataset() -> None:
    whole = rounding(RoundTo(D("1"), RoundingMode.FLOOR))

    assert by_class(("1", "100", 2, 3), ("1", "100", 1, 3), dataset=whole) == [(D("1"), D("99"))]


def test_the_totals_of_the_classes_add_up_to_line_9367() -> None:
    rows = (TICKET_ROW, THIRD_ROW, CLASS_8_ROW)
    line_c = ShortTermRentalNonCompliantCca(rounding(), SHORT_TERM_RENTAL_CCA_UNITS, LINE_9367)

    (output,) = line_c.compute((units(*rows),)).outputs
    assert sum((amount for _, amount in by_class(*rows)), D("0")) == output.value


def test_a_row_whose_column_6_is_zero_is_refused_naming_the_row() -> None:
    with pytest.raises(ValidationError, match="row 2.*short_term_rental_days"):
        by_class(TICKET_ROW, ("8", "900", 0, 0))


def test_a_row_whose_column_5_is_above_column_6_is_refused_naming_the_row() -> None:
    with pytest.raises(ValidationError, match="row 1.*short_term_rental_non_compliant_days"):
        by_class(("1", "900", 91, 90))


def test_a_column_6_of_500_is_used_as_typed() -> None:
    # The form prints no maximum: 900 x 30 / 500 = 54.00 exactly.
    assert by_class(("1", "900", 30, 500)) == [(D("1"), D("54.00"))]


def test_a_column_6_of_366_is_used_as_typed() -> None:
    # 3660 x 100 / 366 = 1000.00 exactly.
    assert by_class(("1", "3660", 100, 366)) == [(D("1"), D("1000.00"))]


def test_a_column_6_of_500_with_500_non_compliant_days_is_used_as_typed() -> None:
    assert by_class(("1", "900", 500, 500)) == [(D("1"), D("900.00"))]


def test_a_column_6_of_365_is_not_refused() -> None:
    # 900 x 30 / 365 = 73.9726..., half-up to 73.97.
    assert by_class(("1", "900", 30, 365)) == [(D("1"), D("73.97"))]


def test_a_column_6_of_365_with_365_non_compliant_days_is_not_refused() -> None:
    assert by_class(("1", "900", 365, 365)) == [(D("1"), D("900.00"))]


def test_a_second_row_of_500_days_is_used_as_typed() -> None:
    # 300.00 for the ticket row, 900 x 10 / 500 = 18.00 for the second.
    assert by_class(TICKET_ROW, ("1", "900", 10, 500)) == [(D("1"), D("318.00"))]


def test_ignores_artifacts_it_does_not_consume() -> None:
    other = Artifact(LINE_9367, D("9"))

    (output,) = capability().compute((other, units(TICKET_ROW))).outputs

    assert output.kind is BY_CLASS


def test_missing_units_is_a_missing_artifact() -> None:
    with pytest.raises(MissingArtifactError, match="short_term_rental_cca_units"):
        capability().compute(())


# --- trace --------------------------------------------------------------------------------------


def class_line(position: int, class_number: str, amounts: tuple[str, ...], result: str) -> Any:
    return ShortTermRentalNonCompliantCcaByClassLine(
        output=BY_CLASS,
        position=position,
        class_number=D(class_number),
        amounts=tuple(D(each) for each in amounts),
        result=D(result),
    )


def test_traces_one_line_per_class_and_no_total() -> None:
    trace = capability().compute((units(TICKET_ROW, CLASS_8_ROW, THIRD_ROW),)).trace

    assert trace == (
        class_line(1, "1", ("300.00", "33.33"), "333.33"),
        class_line(2, "8", ("250.00",), "250.00"),
    )


def test_traces_no_lines_for_no_rows() -> None:
    assert capability().compute((units(),)).trace == ()


def test_a_class_lines_amount_is_its_total() -> None:
    (line,) = capability().compute((units(TICKET_ROW, THIRD_ROW),)).trace

    assert line.amount == D("333.33")
    assert isinstance(line, ShortTermRentalNonCompliantCcaByClassLine)
    assert sum(line.amounts, D("0")) == line.result


def test_traces_the_exact_amounts_without_rounding() -> None:
    (line,) = capability(rounding(NO_ROUNDING)).compute((units(("1", "0.015", 1, 2)),)).trace

    assert isinstance(line, ShortTermRentalNonCompliantCcaByClassLine)
    assert line.amounts == (D("0.0075"),)


def test_compute_is_repeatable() -> None:
    wired = capability()
    given = (units(TICKET_ROW, CLASS_8_ROW),)

    assert wired.compute(given) == wired.compute(given)


# --- through TaxComputationService --------------------------------------------------------------


class _Jurisdictions:
    def __init__(self, jurisdiction: Jurisdiction) -> None:
        self._jurisdiction = jurisdiction

    def get_jurisdiction(self, code: JurisdictionCode) -> Jurisdiction:
        return self._jurisdiction


class _Parameters:
    def __init__(self, *datasets: ParameterDataset[Any]) -> None:
        self._datasets = datasets

    def get[T](self, family: str, tax_year: int, kind: ParameterKind[T]) -> ParameterDataset[T]:
        for dataset in self._datasets:
            if (dataset.family, tax_year, dataset.kind) == (family, 2025, kind):
                return cast(ParameterDataset[T], dataset)
        raise NotFoundError(f"no {family} dataset for tax year {tax_year}")


def service() -> TaxComputationService:
    dataset = rounding()
    code = JurisdictionCode("CA-ON")
    selection = CapabilitySelection(
        name="ca/short_term_rental_non_compliant_cca_by_class",
        params={"rounding": dataset.family},
        consumes={"units": "ca/short_term_rental_cca_units"},
        produces={"output": "ex/non_compliant_cca_by_class"},
    )
    manifest = Manifest(
        jurisdiction=code,
        version=1,
        valid_from_tax_year=2025,
        inputs=required_inputs(frozenset({"ca/short_term_rental_cca_units"})),
        forms=(
            Form(
                required=True,
                name=code.namespace.identifier("return"),
                instances=None,
                exports=("ex/non_compliant_cca_by_class",),
                capabilities=(selection,),
            ),
        ),
    )
    artifacts = ArtifactRegistry()
    for kind in (SHORT_TERM_RENTAL_CCA_UNITS, BY_CLASS):
        artifacts.register(kind.identifier, kind)
    return TaxComputationService(
        _Jurisdictions(Jurisdiction(code=code, manifests=(manifest,))),
        _Parameters(dataset),
        CapabilityRegistry.shared(),
        artifacts,
    )


def test_a_computation_builds_the_capability_from_the_registry_and_its_dataset() -> None:
    (built,) = (
        service().compose(JurisdictionCode("CA-ON"), 2025).form("ca-on/return").composition.order
    )

    assert isinstance(built, rental_cca.ShortTermRentalNonCompliantCcaByClass)
    assert built.produces == frozenset({BY_CLASS})


def test_a_computation_uses_a_row_with_more_days_than_a_year_as_typed() -> None:
    worksheet = service().compute(JurisdictionCode("CA-ON"), 2025, units(("1", "900", 30, 500)))[
        "ca-on/return"
    ][0]

    # 900 x 30 / 500 = 54.00
    records = worksheet.get(BY_CLASS).value.records
    assert [(r[CCA_CLASS_NUMBER], r[NON_COMPLIANT_CCA]) for r in records] == [(D("1"), D("54.00"))]


def test_a_computation_gives_the_column_22_of_each_class() -> None:
    worksheet = service().compute(
        JurisdictionCode("CA-ON"), 2025, units(TICKET_ROW, THIRD_ROW, CLASS_8_ROW)
    )["ca-on/return"][0]

    records = worksheet.get(BY_CLASS).value.records
    assert [(r[CCA_CLASS_NUMBER], r[NON_COMPLIANT_CCA]) for r in records] == [
        (D("1"), D("333.33")),
        (D("8"), D("250.00")),
    ]
    assert isinstance(
        worksheet.producer_of(BY_CLASS), rental_cca.ShortTermRentalNonCompliantCcaByClass
    )
