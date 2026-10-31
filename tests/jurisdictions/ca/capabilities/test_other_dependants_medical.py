"""Unit tests for the OtherDependantsMedical capability (`ca/other_dependants_medical`), line 33199.

Federal Worksheet, line 33199, "Complete one column for each dependant": "Line 1: Medical
expenses for other dependant"; "Line 2: For provinces and territories other than Quebec: amount
from line 109 of the dependant's return" (the lesser of $2,834 and 3% of the dependant's line
23600); "Line 3: Line 1 minus line 2 (if negative, enter "0")"; "Line 4: Add the amounts from line
3 of columns 1, 2, and 3 (and others, if any). Enter this amount on line 33199 of your return."
Ontario's Worksheet ON428 adds "(maximum $15,551 per dependant)" to line 3.

Its slots: one parameter slot `reduction` (a `claim_reduction` dataset: the rate, the ceiling and,
optionally, the maximum), one consumed slot `dependants` (a record list whose records hold each
dependant's medical expenses and net income) and one produced slot `output`. Each dependant is
worked on its own, never pooled: the reduction is the lesser of the ceiling and the rate times
that dependant's net income, the allowable amount is their expenses less it, at least 0 and, when
the dataset has a maximum, at most the maximum, rounded once with the dataset's rule, and the
output is their total. It records one `OtherDependantMedicalLine` per dependant, then an
`ItemsTotalLine`.
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
from tax_engine.domain.errors import InvalidCapabilityError, MissingArtifactError, NotFoundError
from tax_engine.domain.jurisdiction import Jurisdiction
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import CapabilitySelection, Form, Manifest
from tax_engine.domain.parameters.claim_reduction import CLAIM_REDUCTION, ClaimReduction
from tax_engine.domain.parameters.datasets import ParameterDataset
from tax_engine.domain.parameters.kind import ParameterKind
from tax_engine.domain.parameters.rate import Rate
from tax_engine.domain.parameters.rounding import (
    NO_ROUNDING,
    RoundingMode,
    RoundingRule,
    RoundTo,
)
from tax_engine.domain.record_list import RecordList
from tax_engine.domain.trace import ItemsTotalLine
from tax_engine.jurisdictions.ca.capabilities.other_dependants_medical import (
    OtherDependantsMedical,
)
from tax_engine.jurisdictions.ca.catalog import (
    DEPENDANT_NET_INCOME,
    OTHER_DEPENDANT_MEDICAL_EXPENSES,
    OTHER_DEPENDANTS,
    OTHER_DEPENDANTS_MEDICAL,
)
from tax_engine.jurisdictions.ca.trace import OtherDependantMedicalLine
from tests.manifest_support import required_inputs

D = Decimal
CENT = RoundTo(D("0.01"), RoundingMode.HALF_UP)
RATE = Rate(D("0.03"))


def reduction(
    maximum: str | None = None,
    rounding: RoundingRule = CENT,
    rate: str = "0.03",
    ceiling: str = "2834",
) -> ParameterDataset[ClaimReduction]:
    """By default the federal figures: 3% and 2,834, no maximum, to the cent."""
    return ParameterDataset(
        "ca/other_dependants_medical_reduction",
        2025,
        CLAIM_REDUCTION,
        ClaimReduction(Rate(D(rate)), D(ceiling), None if maximum is None else D(maximum)),
        rounding,
        ("https://example.org/federal-worksheet",),
    )


def capability(dataset: ParameterDataset[ClaimReduction] | None = None) -> OtherDependantsMedical:
    return OtherDependantsMedical(
        dataset or reduction(), OTHER_DEPENDANTS, OTHER_DEPENDANTS_MEDICAL
    )


def dependants(*claims: tuple[str, str]) -> Artifact[Any]:
    """An `ca/other_dependants` artifact of one record per (expenses, net income), in order."""
    records = [
        {OTHER_DEPENDANT_MEDICAL_EXPENSES: D(expenses), DEPENDANT_NET_INCOME: D(net_income)}
        for expenses, net_income in claims
    ]
    return Artifact(OTHER_DEPENDANTS, RecordList(OTHER_DEPENDANTS.fields, records))


def compute(wired: OtherDependantsMedical, *claims: tuple[str, str]) -> Artifact[Any]:
    (output,) = wired.compute((dependants(*claims),)).outputs
    return output


def total(
    *claims: tuple[str, str], dataset: ParameterDataset[ClaimReduction] | None = None
) -> Decimal:
    value = compute(capability(dataset), *claims).value
    assert isinstance(value, Decimal)
    return value


# The ticket's example: 3,000 with net income 10,000 and 1,000 with net income 40,000.
FIRST = ("3000", "10000")
SECOND = ("1000", "40000")


def test_is_registered_as_ca_other_dependants_medical() -> None:
    assert CapabilityRegistry.shared().get("ca/other_dependants_medical") is OtherDependantsMedical


def test_is_exported_from_the_ca_capabilities_package() -> None:
    assert ca_capabilities.NAMESPACE == "ca"
    assert "other_dependants_medical" in ca_capabilities.__all__
    assert ca_capabilities.other_dependants_medical.OtherDependantsMedical is OtherDependantsMedical


def test_declares_its_contract() -> None:
    assert capability().consumes == frozenset({OTHER_DEPENDANTS})
    assert capability().produces == frozenset({OTHER_DEPENDANTS_MEDICAL})


def test_leaves_its_contract_to_the_base() -> None:
    assert "consumes" not in vars(OtherDependantsMedical)
    assert "produces" not in vars(OtherDependantsMedical)


def test_declares_its_slots() -> None:
    assert OtherDependantsMedical.PARAMETERS == {"reduction": CLAIM_REDUCTION}
    assert OtherDependantsMedical.CONSUMES == {"dependants": RecordList}
    assert OtherDependantsMedical.PRODUCES == {"output": Decimal}
    assert not OtherDependantsMedical.is_list_slot("dependants")


def test_its_slots_are_read_only() -> None:
    slots = (
        OtherDependantsMedical.PARAMETERS,
        OtherDependantsMedical.CONSUMES,
        OtherDependantsMedical.PRODUCES,
    )
    for each in slots:
        assert isinstance(each, MappingProxyType)
        with pytest.raises(TypeError):
            cast(Any, each)["extra"] = Decimal


def test_its_slots_are_typed_as_read_only_mappings() -> None:
    assert_type(OtherDependantsMedical.PARAMETERS, Mapping[str, ParameterKind[ClaimReduction]])
    assert_type(OtherDependantsMedical.CONSUMES, Mapping[str, type])
    assert_type(OtherDependantsMedical.PRODUCES, Mapping[str, type])


def test_is_built_from_its_slot_names_as_keywords() -> None:
    wired = OtherDependantsMedical(
        reduction=reduction(),
        dependants=OTHER_DEPENDANTS,
        output=OTHER_DEPENDANTS_MEDICAL,
    )

    assert compute(wired, FIRST) == Artifact(OTHER_DEPENDANTS_MEDICAL, D("2700.00"))


def test_takes_no_separate_rounding_argument() -> None:
    with pytest.raises(TypeError):
        OtherDependantsMedical(  # type: ignore[call-arg]
            reduction(), OTHER_DEPENDANTS, OTHER_DEPENDANTS_MEDICAL, CENT
        )


def test_rejects_a_money_kind_for_its_dependants() -> None:
    with pytest.raises(InvalidCapabilityError, match="OtherDependantsMedical.*'dependants'"):
        OtherDependantsMedical(
            reduction(),
            OTHER_DEPENDANTS_MEDICAL,  # type: ignore[arg-type]
            OTHER_DEPENDANTS_MEDICAL,
        )


def test_is_not_generic_over_artifacts() -> None:
    assert not getattr(OtherDependantsMedical, "__type_params__", ())
    assert not getattr(OtherDependantsMedical, "__parameters__", ())


# --- computing: how many dependants -------------------------------------------------------------


def test_no_dependants_give_zero() -> None:
    output = compute(capability())

    assert output == Artifact(OTHER_DEPENDANTS_MEDICAL, D("0"))
    assert type(output.value) is Decimal
    assert not output.value.is_signed()


def test_one_dependant_gives_the_per_item_figure() -> None:
    # Line 2: lesser(300, 2,834) = 300; line 3: 3,000 - 300 = 2,700.
    assert total(FIRST) == D("2700.00")


def test_the_tickets_example_gives_2700_not_the_pooled_2500() -> None:
    # 3,000 - lesser(300, 2,834) = 2,700; 1,000 - lesser(1,200, 2,834) = 0 (not below zero).
    # Pooled: 4,000 - lesser(1,500, 2,834) = 2,500, which is wrong.
    assert total(FIRST, SECOND) == D("2700.00")
    assert total(FIRST, SECOND) != D("2500")
    assert total(FIRST, SECOND) != total(("4000", "50000"))


def test_two_dependants_give_the_sum_of_their_own_amounts() -> None:
    # 3,000 - 300 = 2,700 and 2,000 - lesser(600, 2,834) = 1,400.
    assert total(FIRST, ("2000", "20000")) == D("4100.00")


def test_three_dependants_are_summed_one_by_one() -> None:
    assert total(FIRST, ("2000", "20000"), ("500", "100")) == D("4597.00")


def test_a_dependant_with_no_allowable_amount_adds_nothing_to_the_others() -> None:
    assert total(SECOND, FIRST) == D("2700.00")


def test_the_total_does_not_depend_on_the_order() -> None:
    assert total(SECOND, FIRST) == total(FIRST, SECOND)


# --- computing: the reduction and the floor -----------------------------------------------------


def test_the_reduction_is_the_rate_times_net_income_while_that_is_under_the_ceiling() -> None:
    # 3% of 50,000 = 1,500, under 2,834.
    assert total(("5000", "50000")) == D("3500.00")


def test_the_reduction_is_the_ceiling_once_the_rate_times_net_income_exceeds_it() -> None:
    # 3% of 200,000 = 6,000, over 2,834: 5,000 - 2,834.
    assert total(("5000", "200000")) == D("2166.00")


def test_the_reduction_reaches_the_ceiling_exactly_where_the_rate_times_income_equals_it() -> None:
    # 3% of 94,466.66... is 2,834; at 94,000 it is 2,820 and at 95,000 the ceiling applies.
    assert total(("5000", "94000")) == D("2180.00")
    assert total(("5000", "95000")) == D("2166.00")


def test_a_net_income_of_zero_takes_nothing_off() -> None:
    assert total(("3000", "0")) == D("3000.00")


def test_expenses_equal_to_the_reduction_give_plain_zero() -> None:
    value = total(("300", "10000"))

    assert value == D("0")
    assert not value.is_signed()


@pytest.mark.parametrize(
    ("expenses", "net_income"),
    [("299.99", "10000"), ("0", "10000"), ("1000", "40000"), ("100", "200000"), ("0", "0")],
)
def test_expenses_under_the_reduction_give_plain_zero_never_negative(
    expenses: str, net_income: str
) -> None:
    value = total((expenses, net_income))

    assert value == D("0")
    assert not value.is_signed()


def test_every_dependant_under_the_reduction_gives_plain_zero() -> None:
    value = total(SECOND, ("10", "100000"), ("0", "0"))

    assert value == D("0")
    assert not value.is_signed()


def test_a_dependant_under_the_reduction_does_not_reduce_another_dependants_amount() -> None:
    # The floor is per dependant: 0 + 2,700, not 2,700 - 200 (1,200 - 1,000).
    assert total(SECOND, FIRST) == D("2700.00")


def test_a_cent_over_the_reduction_gives_a_cent() -> None:
    assert total(("300.01", "10000")) == D("0.01")


# --- computing: the dataset ---------------------------------------------------------------------


def test_the_dataset_supplies_the_rate_and_the_ceiling() -> None:
    dataset = reduction(rate="0.10", ceiling="500")

    assert total(("1000", "2000"), dataset=dataset) == D("800.00")  # 10% of 2,000 = 200
    assert total(("1000", "9000"), dataset=dataset) == D("500.00")  # ceiling 500 applies


def test_a_zero_ceiling_takes_nothing_off() -> None:
    assert total(("3000", "10000"), dataset=reduction(ceiling="0")) == D("3000.00")


def test_a_zero_rate_takes_nothing_off() -> None:
    assert total(("3000", "10000"), dataset=reduction(rate="0")) == D("3000.00")


def test_a_different_year_figure_changes_the_result() -> None:
    assert total(FIRST, dataset=reduction(ceiling="200")) == D("2800.00")


# --- computing: the maximum ---------------------------------------------------------------------


def test_a_dataset_with_a_maximum_caps_a_large_claim_at_it() -> None:
    # 20,000 - 300 = 19,700, at most 15,551.
    assert total(("20000", "10000"), dataset=reduction(maximum="15551")) == D("15551.00")


def test_the_same_inputs_without_a_maximum_are_not_capped() -> None:
    assert total(("20000", "10000"), dataset=reduction(maximum=None)) == D("19700.00")


def test_a_claim_under_the_maximum_is_unchanged() -> None:
    assert total(FIRST, dataset=reduction(maximum="15551")) == D("2700.00")


def test_a_claim_exactly_at_the_maximum_is_unchanged() -> None:
    # 15,851 - 300 = 15,551.
    assert total(("15851", "10000"), dataset=reduction(maximum="15551")) == D("15551.00")
    assert total(("15852", "10000"), dataset=reduction(maximum="15551")) == D("15551.00")


def test_the_maximum_applies_to_each_dependant_not_to_the_total() -> None:
    # 15,551 + 15,551 = 31,102, though the total is over the maximum.
    dataset = reduction(maximum="15551")

    assert total(("20000", "10000"), ("30000", "10000"), dataset=dataset) == D("31102.00")


def test_the_maximum_is_applied_after_the_reduction_and_the_floor() -> None:
    # The first is floored at 0 (not negative) before the second is capped.
    dataset = reduction(maximum="15551")

    assert total(SECOND, ("20000", "10000"), dataset=dataset) == D("15551.00")


def test_a_maximum_of_zero_allows_nothing() -> None:
    assert total(FIRST, dataset=reduction(maximum="0")) == D("0")


# --- computing: rounding ------------------------------------------------------------------------


def test_each_allowable_amount_is_rounded_half_up_to_the_cent() -> None:
    # 3% of 10,000.50 = 300.015, half-up to the cent: 300.02; 1,000 - 300.02 = 699.98.
    assert total(("1000", "10000.50")) == D("699.98")
    # 3% of 10,000.60 = 300.018 -> 300.02 -> 699.98.
    assert total(("1000", "10000.60")) == D("699.98")
    # 3% of 10,000.40 = 300.012 -> 300.01 -> 699.99.
    assert total(("1000", "10000.40")) == D("699.99")


def test_the_reduction_is_rounded_before_it_is_taken_off() -> None:
    # The dependant's line 109 is a cent figure: 300.015 is 300.02, not left exact (699.985).
    assert total(("1000", "10000.50")) != D("699.99")


def test_the_rounding_is_done_once_per_dependant_before_they_are_summed() -> None:
    # Per dependant 699.98, twice: 1,399.96.
    assert total(("1000", "10000.50"), ("1000", "10000.50")) == D("1399.96")


def test_the_rounding_rule_comes_from_the_dataset() -> None:
    dataset = reduction(rounding=RoundTo(D("1"), RoundingMode.FLOOR))

    # The reduction floors to 300, so the claim is 700.
    assert total(("1000", "10000.50"), dataset=dataset) == D("700")


def test_no_rounding_keeps_the_exact_amount() -> None:
    assert total(("1000", "10000.50"), dataset=reduction(rounding=NO_ROUNDING)) == D("699.985")


def test_a_rounded_allowable_amount_carries_the_increments_scale() -> None:
    assert str(total(FIRST)) == "2700.00"
    assert str(total(FIRST, ("2000", "20000"))) == "4100.00"


def test_a_capped_amount_is_rounded_too() -> None:
    dataset = reduction(maximum="15551.005")

    assert total(("20000", "10000"), dataset=dataset) == D("15551.01")


# --- computing: inputs --------------------------------------------------------------------------


def test_ignores_artifacts_it_does_not_consume() -> None:
    other = Artifact(DEPENDANT_NET_INCOME, D("9"))

    result = capability().compute((other, dependants(FIRST)))

    assert result.outputs == (Artifact(OTHER_DEPENDANTS_MEDICAL, D("2700.00")),)


def test_missing_dependants_is_a_missing_artifact() -> None:
    with pytest.raises(MissingArtifactError, match="other_dependants"):
        capability().compute(())


def test_has_one_output() -> None:
    assert len(capability().compute((dependants(FIRST, SECOND),)).outputs) == 1


# --- trace --------------------------------------------------------------------------------------


def claim(
    position: int,
    expenses: str,
    net_income: str,
    result: str,
    maximum: str | None = None,
    rounding: RoundingRule = CENT,
) -> Any:
    return OtherDependantMedicalLine(
        output=OTHER_DEPENDANTS_MEDICAL,
        position=position,
        expenses=D(expenses),
        net_income=D(net_income),
        reduction=ClaimReduction(RATE, D("2834"), None if maximum is None else D(maximum)),
        rounding=rounding,
        result=D(result),
    )


def test_traces_one_claim_line_per_dependant_then_the_total() -> None:
    trace = capability().compute((dependants(FIRST, SECOND),)).trace

    assert trace == (
        claim(1, "3000", "10000", "2700.00"),
        claim(2, "1000", "40000", "0.00"),
        ItemsTotalLine(OTHER_DEPENDANTS_MEDICAL, ((1, D("2700.00")), (2, D("0.00"))), D("2700.00")),
    )


def test_traces_the_callers_order_with_positions_from_one() -> None:
    trace = capability().compute((dependants(SECOND, FIRST, ("5000", "200000")),)).trace

    assert trace == (
        claim(1, "1000", "40000", "0.00"),
        claim(2, "3000", "10000", "2700.00"),
        claim(3, "5000", "200000", "2166.00"),
        ItemsTotalLine(
            OTHER_DEPENDANTS_MEDICAL,
            ((1, D("0.00")), (2, D("2700.00")), (3, D("2166.00"))),
            D("4866.00"),
        ),
    )


def test_traces_no_dependants_as_only_an_empty_total() -> None:
    trace = capability().compute((dependants(),)).trace

    assert trace == (ItemsTotalLine(OTHER_DEPENDANTS_MEDICAL, (), D("0")),)


def test_traces_a_dependant_under_the_reduction_as_a_plain_zero_claim() -> None:
    claim_line, total_line = capability().compute((dependants(SECOND),)).trace

    assert isinstance(claim_line, OtherDependantMedicalLine)
    assert claim_line.result == D("0")
    assert not claim_line.result.is_signed()
    assert isinstance(total_line, ItemsTotalLine)
    assert not total_line.total.is_signed()


def test_traces_the_datasets_reduction_with_its_maximum() -> None:
    wired = capability(reduction(maximum="15551"))

    claim_line, _ = wired.compute((dependants(("20000", "10000")),)).trace

    assert claim_line == claim(1, "20000", "10000", "15551.00", maximum="15551")
    assert isinstance(claim_line, OtherDependantMedicalLine)
    assert claim_line.reduction.maximum == D("15551")


def test_traces_no_maximum_when_the_dataset_has_none() -> None:
    claim_line, _ = capability().compute((dependants(FIRST),)).trace

    assert isinstance(claim_line, OtherDependantMedicalLine)
    assert claim_line.reduction.maximum is None


def test_traces_the_datasets_rounding_rule_and_the_rounded_amounts() -> None:
    claim_line, total_line = capability().compute((dependants(("1000", "10000.50")),)).trace

    assert claim_line == claim(1, "1000", "10000.50", "699.98")
    assert total_line == ItemsTotalLine(OTHER_DEPENDANTS_MEDICAL, ((1, D("699.98")),), D("699.98"))


def test_traces_the_exact_amount_without_rounding() -> None:
    wired = capability(reduction(rounding=NO_ROUNDING))

    claim_line, _ = wired.compute((dependants(("1000", "10000.50")),)).trace

    assert isinstance(claim_line, OtherDependantMedicalLine)
    assert claim_line.rounding == NO_ROUNDING
    assert claim_line.result == D("699.985")


def test_the_last_trace_line_amount_is_the_output() -> None:
    result = capability().compute((dependants(FIRST, ("2000", "20000")),))

    (output,) = result.outputs
    assert result.trace[-1].amount == output.value
    assert [line.amount for line in result.trace[:-1]] == [D("2700.00"), D("1400.00")]


def test_the_total_is_the_sum_of_its_items() -> None:
    *_, total_line = capability().compute((dependants(FIRST, ("2000", "20000"), SECOND),)).trace

    assert isinstance(total_line, ItemsTotalLine)
    assert total_line.total == sum((amount for _, amount in total_line.items), D("0"))


def test_compute_is_repeatable() -> None:
    wired = capability()
    given = (dependants(FIRST, SECOND),)

    assert wired.compute(given) == wired.compute(given)


# --- through TaxComputationService --------------------------------------------------------------


class _Jurisdictions:
    def __init__(self, jurisdiction: Jurisdiction) -> None:
        self._jurisdiction = jurisdiction

    def get_jurisdiction(self, code: JurisdictionCode) -> Jurisdiction:
        return self._jurisdiction


class _Parameters:
    def __init__(self, dataset: ParameterDataset[ClaimReduction]) -> None:
        self._dataset = dataset

    def get[T](self, family: str, tax_year: int, kind: ParameterKind[T]) -> ParameterDataset[T]:
        if (family, tax_year, kind) != (self._dataset.family, 2025, CLAIM_REDUCTION):
            raise NotFoundError(f"no {family} dataset for tax year {tax_year}")
        return cast(ParameterDataset[T], self._dataset)


def service(dataset: ParameterDataset[ClaimReduction] | None = None) -> TaxComputationService:
    dataset = dataset or reduction()
    code = JurisdictionCode("CA-ON")
    selection = CapabilitySelection(
        name="ca/other_dependants_medical",
        params={"reduction": dataset.family},
        consumes={"dependants": "ca/other_dependants"},
        produces={"output": "ca/other_dependants_medical"},
    )
    manifest = Manifest(
        jurisdiction=code,
        version=1,
        valid_from_tax_year=2025,
        inputs=required_inputs(frozenset({"ca/other_dependants"})),
        forms=(
            Form(
                required=True,
                name=code.namespace.identifier("return"),
                instances=None,
                exports=("ca/other_dependants_medical",),
                capabilities=(selection,),
            ),
        ),
    )
    artifacts = ArtifactRegistry()
    for kind in (OTHER_DEPENDANTS, OTHER_DEPENDANTS_MEDICAL):
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
    assert isinstance(built, OtherDependantsMedical)
    assert built.consumes == frozenset({OTHER_DEPENDANTS})
    assert built.produces == frozenset({OTHER_DEPENDANTS_MEDICAL})


def test_a_computation_gives_the_per_item_total_not_the_pooled_figure() -> None:
    worksheet = service().compute(JurisdictionCode("CA-ON"), 2025, dependants(FIRST, SECOND))[
        "ca-on/return"
    ][0]

    assert worksheet.get(OTHER_DEPENDANTS_MEDICAL).value == D("2700.00")
    assert isinstance(worksheet.producer_of(OTHER_DEPENDANTS_MEDICAL), OtherDependantsMedical)
    assert worksheet.trace == (
        claim(1, "3000", "10000", "2700.00"),
        claim(2, "1000", "40000", "0.00"),
        ItemsTotalLine(OTHER_DEPENDANTS_MEDICAL, ((1, D("2700.00")), (2, D("0.00"))), D("2700.00")),
    )


def test_a_computation_with_no_dependants_gives_zero() -> None:
    worksheet = service().compute(JurisdictionCode("CA-ON"), 2025, dependants())["ca-on/return"][0]

    assert worksheet.get(OTHER_DEPENDANTS_MEDICAL).value == D("0")


def test_a_computation_applies_the_datasets_maximum() -> None:
    worksheet = service(reduction(maximum="15551")).compute(
        JurisdictionCode("CA-ON"), 2025, dependants(("20000", "10000"))
    )["ca-on/return"][0]

    assert worksheet.get(OTHER_DEPENDANTS_MEDICAL).value == D("15551.00")
