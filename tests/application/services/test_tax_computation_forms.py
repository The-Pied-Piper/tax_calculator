"""Unit tests for TaxComputationService with forms: flat peers, each run once per instance.

A manifest is a flat set of `forms`, none special: each is a group of selections with `exports`
and, optionally, an instances kind (a record list, one record per instance); a form without
instances has one instance. The default form, named `ex-on/return` by the loader's convention
only, is one of them. The service builds every form with the same `CapabilityBuilder`, datasets and
registries into one `FormSet` (domain/form.py), which runs each form once per instance on its own
`Worksheet` and keeps, for each export `X` of form `B`, the derived artifact `B.X`: a record list
of ONE field (X's kind) with a record per instance, in instance order (one record for a form
without instances). Every form reads any `B.X` by its identifier; the `B.X` kinds are registered
into the artifact registry before any selection is built, idempotently. With no instances, each
`B.X` is an empty record list. `compute` returns each form's worksheets by form name, one per
instance in instance order; `compose` the wired `FormSet`. Everything here is made up (`ex/`
names).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from decimal import Decimal
from typing import Any, ClassVar

import pytest

from tax_engine.application.services.tax_computation import TaxComputationService
from tax_engine.domain.artifact import Artifact, ArtifactKind, ArtifactRegistry
from tax_engine.domain.capabilities.record_total import RecordTotal
from tax_engine.domain.capabilities.subtract import Subtract
from tax_engine.domain.capability import Capability, CapabilityRegistry, CapabilityResult
from tax_engine.domain.errors import (
    CapabilityContractError,
    DuplicateRegistrationError,
    InvalidCompositionError,
    InvalidManifestError,
    MissingArtifactError,
    NotFoundError,
    UnknownRegistrationError,
    ValidationError,
)
from tax_engine.domain.form import FormSet
from tax_engine.domain.jurisdiction import Jurisdiction
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import (
    CapabilitySelection,
    Default,
    Form,
    InputDeclaration,
    Manifest,
)
from tax_engine.domain.record_list import RecordList, RecordListKind
from tax_engine.domain.trace import FormInstanceLine, RecordTotalLine, SubtractedLine
from tests.application.services.test_tax_computation import (
    BASE,
    FACTOR,
    FakeJurisdictions,
    FakeParameters,
    Scale,
    StepLine,
    factor_data,
)
from tests.manifest_support import required_fields, required_inputs

D = Decimal
EX_ON = JurisdictionCode("EX-ON")

# --- the made-up rental form: two amounts and a nested list of unit rents per instance ---------

GROSS_RENT = ArtifactKind("ex/gross_rent", Decimal)
EXPENSES = ArtifactKind("ex/expenses", Decimal)
NET_INCOME = ArtifactKind("ex/net_income", Decimal, non_negative=True)
UNIT_AMOUNT = ArtifactKind("ex/unit_amount", Decimal)
UNITS = RecordListKind("ex/units", fields=(UNIT_AMOUNT,))
UNITS_DOUBLED = RecordListKind("ex/units_doubled", fields=(UNIT_AMOUNT,))
RENTALS = RecordListKind("ex/rentals", fields=(GROSS_RENT, EXPENSES, UNITS))
TOTAL_NET_INCOME = ArtifactKind("ex/total_net_income", Decimal)
OTHER_AMOUNT = ArtifactKind("ex/other_amount", Decimal)
SPARE = ArtifactKind("ex/spare", Decimal)
DOUBLED_COUNT = ArtifactKind("ex/doubled_count", int)
NOTES = ArtifactKind("ex/notes", Decimal)
NOTE = ArtifactKind("ex/note", str)

# The kinds the engine derives for the rental form's two exports: one field, a record per instance.
NET_INCOME_PER_RENTAL = RecordListKind("ex/rental.net_income", fields=(NET_INCOME,))
UNITS_DOUBLED_PER_RENTAL = RecordListKind("ex/rental.units_doubled", fields=(UNITS_DOUBLED,))

# The made-up scaling form: `ex/bases` instances, each scaled by the `ex/factor` dataset.
BASES = RecordListKind("ex/bases", fields=(BASE,))
SCALED = ArtifactKind("ex/scaled", Decimal)
SCALED_TOTAL = ArtifactKind("ex/scaled_total", Decimal)
SCALED_PER_BASE = RecordListKind("ex/scaling.scaled", fields=(SCALED,))

# The made-up summary form: reads the rental form's net incomes (an import), one record per summary.
SUMMARIES = RecordListKind("ex/summaries", fields=(OTHER_AMOUNT,))
RENTAL_TOTAL = ArtifactKind("ex/rental_total", Decimal)
CYCLE_TOTAL = ArtifactKind("ex/cycle_total", Decimal)
SPARE_TOTAL = ArtifactKind("ex/spare_total", Decimal)
SUMMARY_SPARE = RecordListKind("ex/summary.spare", fields=(SPARE,))


class DoubleUnits(Capability):
    """Produces `doubled`: the consumed `units` list with every amount doubled, same order."""

    CONSUMES: ClassVar[Mapping[str, type]] = {"units": RecordList}
    PRODUCES: ClassVar[Mapping[str, type]] = {"doubled": RecordList}

    def __init__(self, units: RecordListKind, doubled: RecordListKind) -> None:
        super().__init__(units=units, doubled=doubled)
        self._units, self._doubled = units, doubled

    def compute(self, inputs: tuple[Artifact[Any], ...]) -> CapabilityResult:
        records = self._input(inputs, self._units).value.records
        value = RecordList(
            self._doubled.fields, [{UNIT_AMOUNT: record[UNIT_AMOUNT] * 2} for record in records]
        )
        return CapabilityResult(
            outputs=(Artifact(self._doubled, value),), trace=(StepLine("doubled", D(len(records))),)
        )


class CountRecords(Capability):
    """Produces `count`: the number of records of the consumed `records` list."""

    CONSUMES: ClassVar[Mapping[str, type]] = {"records": RecordList}
    PRODUCES: ClassVar[Mapping[str, type]] = {"count": int}

    def __init__(self, records: RecordListKind, count: ArtifactKind[int]) -> None:
        super().__init__(records=records, count=count)
        self._records, self._count = records, count

    def compute(self, inputs: tuple[Artifact[Any], ...]) -> CapabilityResult:
        found = self._input(inputs, self._records).value.records
        return CapabilityResult(outputs=(Artifact(self._count, len(found)),), trace=())


class Describe(Capability):
    """Produces `note`, a text: not a kind a form may export."""

    CONSUMES: ClassVar[Mapping[str, type]] = {"source": Decimal}
    PRODUCES: ClassVar[Mapping[str, type]] = {"note": str}

    def __init__(self, source: ArtifactKind[Decimal], note: ArtifactKind[str]) -> None:
        super().__init__(source=source, note=note)
        self._note = note

    def compute(self, inputs: tuple[Artifact[Any], ...]) -> CapabilityResult:
        return CapabilityResult(outputs=(Artifact(self._note, "x"),), trace=())


NET = CapabilitySelection(
    name="core/subtract",
    params={},
    consumes={"amount": "ex/gross_rent", "less": "ex/expenses"},
    produces={"output": "ex/net_income"},
)
DOUBLE = CapabilitySelection(
    name="ex/double_units",
    params={},
    consumes={"units": "ex/units"},
    produces={"doubled": "ex/units_doubled"},
)
RENTAL = Form(
    required=True,
    name="ex/rental",
    instances="ex/rentals",
    fields=required_fields(RENTALS),
    exports=("ex/net_income", "ex/units_doubled"),
    capabilities=(NET, DOUBLE),
)
TOTAL = CapabilitySelection(
    name="core/record_total",
    params={},
    consumes={"records": "ex/rental.net_income"},
    produces={"output": "ex/total_net_income"},
)
# Reads the rental form's list-valued export, so that it reaches the default form's worksheet.
COUNT_DOUBLED = CapabilitySelection(
    name="ex/count_records",
    params={},
    consumes={"records": "ex/rental.units_doubled"},
    produces={"count": "ex/doubled_count"},
)
SCALE = CapabilitySelection(
    name="ex/scale",
    params={"factor": "ex/factor"},
    consumes={"source": "ex/base"},
    produces={"target": "ex/scaled"},
)
SCALING = Form(
    required=True,
    name="ex/scaling",
    instances="ex/bases",
    fields=required_fields(BASES),
    exports=("ex/scaled",),
    capabilities=(SCALE,),
)
SCALED_SUM = CapabilitySelection(
    name="core/record_total",
    params={},
    consumes={"records": "ex/scaling.scaled"},
    produces={"output": "ex/scaled_total"},
)


SUMMARY_TOTAL = CapabilitySelection(
    name="core/record_total",
    params={},
    consumes={"records": "ex/rental.net_income"},
    produces={"output": "ex/rental_total"},
)
SUMMARY_LESS = CapabilitySelection(
    name="core/subtract",
    params={},
    consumes={"amount": "ex/rental_total", "less": "ex/other_amount"},
    produces={"output": "ex/spare"},
)
SUMMARY = Form(
    required=True,
    name="ex/summary",
    instances="ex/summaries",
    fields=required_fields(SUMMARIES),
    exports=("ex/spare",),
    capabilities=(SUMMARY_TOTAL, SUMMARY_LESS),
)
SPARE_SUM = CapabilitySelection(
    name="core/record_total",
    params={},
    consumes={"records": "ex/summary.spare"},
    produces={"output": "ex/spare_total"},
)
# The rental form also totals the summaries' spare: with the summary form reading its net incomes,
# the two import each other.
CYCLE_TOTAL_SELECTION = CapabilitySelection(
    name="core/record_total",
    params={},
    consumes={"records": "ex/summary.spare"},
    produces={"output": "ex/cycle_total"},
)
CYCLE_RENTAL = Form(
    required=True,
    name="ex/rental",
    instances="ex/rentals",
    fields=required_fields(RENTALS),
    exports=("ex/net_income", "ex/units_doubled", "ex/cycle_total"),
    capabilities=(NET, DOUBLE, CYCLE_TOTAL_SELECTION),
)


RETURN = "ex-on/return"


def manifest_of(
    capabilities: tuple[CapabilitySelection, ...],
    *,
    inputs: frozenset[str],
    outputs: frozenset[str],
    forms: tuple[Form, ...] = (),
) -> Manifest:
    """A manifest whose default form `ex-on/return` runs `capabilities` and exports `outputs`."""
    default = Form(
        required=True,
        name=RETURN,
        instances=None,
        exports=tuple(sorted(outputs)),
        capabilities=capabilities,
    )
    return Manifest(
        jurisdiction=EX_ON,
        version=1,
        valid_from_tax_year=2025,
        inputs=required_inputs(inputs),
        forms=(default, *forms),
    )


def edited(
    manifest: Manifest,
    *,
    capabilities: tuple[CapabilitySelection, ...] | None = None,
    inputs: frozenset[str] | None = None,
    outputs: frozenset[str] | None = None,
    forms: tuple[Form, ...] | None = None,
) -> Manifest:
    """`manifest` with the default form's selections or exports, the inputs or the rest changed."""
    default, *others = manifest.forms
    return manifest_of(
        default.capabilities if capabilities is None else capabilities,
        inputs=frozenset(manifest.inputs) if inputs is None else inputs,
        outputs=frozenset(default.exports) if outputs is None else outputs,
        forms=tuple(others) if forms is None else forms,
    )


def rental_manifest(
    form: Form = RENTAL,
    inputs: frozenset[str] = frozenset({"ex/rentals"}),
) -> Manifest:
    return manifest_of(
        (TOTAL, COUNT_DOUBLED),
        inputs=inputs,
        outputs=frozenset({"ex/total_net_income", "ex/doubled_count"}),
        forms=(form,),
    )


def summary_manifest() -> Manifest:
    return manifest_of(
        (SPARE_SUM,),
        inputs=frozenset({"ex/rentals", "ex/summaries"}),
        outputs=frozenset({"ex/spare_total"}),
        forms=(RENTAL, SUMMARY),
    )


def scaling_manifest() -> Manifest:
    return manifest_of(
        (SCALED_SUM,),
        inputs=frozenset({"ex/bases"}),
        outputs=frozenset({"ex/scaled_total"}),
        forms=(SCALING,),
    )


def both_manifest() -> Manifest:
    return manifest_of(
        (TOTAL, COUNT_DOUBLED, SCALED_SUM),
        inputs=frozenset({"ex/rentals", "ex/bases"}),
        outputs=frozenset({"ex/total_net_income", "ex/doubled_count", "ex/scaled_total"}),
        forms=(RENTAL, SCALING),
    )


def artifact_registry(
    *extra: ArtifactKind[Any], rentals_kind: RecordListKind = RENTALS
) -> ArtifactRegistry:
    registry = ArtifactRegistry()
    kinds: tuple[ArtifactKind[Any], ...] = (
        GROSS_RENT,
        EXPENSES,
        NET_INCOME,
        UNIT_AMOUNT,
        UNITS,
        UNITS_DOUBLED,
        rentals_kind,
        TOTAL_NET_INCOME,
        OTHER_AMOUNT,
        SPARE,
        NOTES,
        NOTE,
        BASE,
        SCALED,
        BASES,
        SCALED_TOTAL,
        SUMMARIES,
        RENTAL_TOTAL,
        CYCLE_TOTAL,
        SPARE_TOTAL,
        DOUBLED_COUNT,
    )
    for kind in (*kinds, *extra):
        registry.register(kind.identifier, kind)
    return registry


def capability_registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    registry.register("core/subtract", Subtract)
    registry.register("core/record_total", RecordTotal)
    registry.register("ex/double_units", DoubleUnits)
    registry.register("ex/count_records", CountRecords)
    registry.register("ex/describe", Describe)
    registry.register("ex/scale", Scale)
    return registry


def service(
    manifest: Manifest,
    artifacts: ArtifactRegistry | None = None,
    parameters: FakeParameters | None = None,
) -> TaxComputationService:
    return TaxComputationService(
        FakeJurisdictions(Jurisdiction(code=EX_ON, manifests=(manifest,))),
        parameters if parameters is not None else FakeParameters(factor_data()),
        capability_registry(),
        artifacts if artifacts is not None else artifact_registry(),
    )


def units(*amounts: str) -> RecordList:
    return RecordList(UNITS.fields, [{UNIT_AMOUNT: D(amount)} for amount in amounts])


def rentals(*instances: tuple[str, str, RecordList]) -> Artifact[Any]:
    records: list[dict[ArtifactKind[Any], object]] = [
        {GROSS_RENT: D(gross), EXPENSES: D(expenses), UNITS: listed}
        for gross, expenses, listed in instances
    ]
    return Artifact(RENTALS, RecordList(RENTALS.fields, records))


TWO_RENTALS = rentals(
    ("12000", "2000", units("100", "250.50")),
    ("5000", "1000", units()),
)


# --- two instances, end to end ---------------------------------------------------------------


def test_two_instances_are_run_each_on_its_own_and_totalled_by_the_return() -> None:
    worksheet = service(rental_manifest()).compute(EX_ON, 2025, TWO_RENTALS)["ex-on/return"][0]

    assert worksheet.get(TOTAL_NET_INCOME).value == D("14000")


def test_an_export_is_a_record_list_of_one_field_with_a_record_per_instance() -> None:
    artifacts = artifact_registry()
    worksheet = service(rental_manifest(), artifacts).compute(EX_ON, 2025, TWO_RENTALS)[
        "ex-on/return"
    ][0]

    net = artifacts.kind("ex/rental.net_income")
    assert net == NET_INCOME_PER_RENTAL
    assert worksheet.get(net).value == RecordList(
        (NET_INCOME,), [{NET_INCOME: D("10000")}, {NET_INCOME: D("4000")}]
    )


def test_instance_order_is_the_order_of_the_records_given() -> None:
    swapped = rentals(
        ("5000", "1000", units()),
        ("12000", "2000", units("100")),
    )
    artifacts = artifact_registry()

    worksheet = service(rental_manifest(), artifacts).compute(EX_ON, 2025, swapped)["ex-on/return"][
        0
    ]

    net = worksheet.get(artifacts.kind("ex/rental.net_income")).value
    assert [record[NET_INCOME] for record in net.records] == [D("4000"), D("10000")]


def test_a_list_valued_export_is_a_record_list_of_nested_record_lists() -> None:
    artifacts = artifact_registry()
    worksheet = service(rental_manifest(), artifacts).compute(EX_ON, 2025, TWO_RENTALS)[
        "ex-on/return"
    ][0]

    doubled = artifacts.kind("ex/rental.units_doubled")

    assert doubled == UNITS_DOUBLED_PER_RENTAL
    assert worksheet.get(doubled).value == RecordList(
        (UNITS_DOUBLED,),
        [
            {
                UNITS_DOUBLED: RecordList(
                    UNITS_DOUBLED.fields,
                    [{UNIT_AMOUNT: D("200")}, {UNIT_AMOUNT: D("501.00")}],
                )
            },
            {UNITS_DOUBLED: RecordList(UNITS_DOUBLED.fields, [])},
        ],
    )


def test_an_instance_holds_a_nested_record_list_the_form_reads() -> None:
    # The first instance's class table (`ex/units`) reaches the form's capability whole.
    artifacts = artifact_registry()
    one = rentals(("100", "0", units("1", "2", "3")))

    worksheet = service(rental_manifest(), artifacts).compute(EX_ON, 2025, one)["ex-on/return"][0]

    (record,) = worksheet.get(artifacts.kind("ex/rental.units_doubled")).value.records
    assert [each[UNIT_AMOUNT] for each in record[UNITS_DOUBLED].records] == [D(2), D(4), D(6)]


def test_the_exports_reach_the_return_as_starting_artifacts_no_capability_produced() -> None:
    artifacts = artifact_registry()
    worksheet = service(rental_manifest(), artifacts).compute(EX_ON, 2025, TWO_RENTALS)[
        "ex-on/return"
    ][0]

    for identifier in ("ex/rental.net_income", "ex/rental.units_doubled"):
        assert worksheet.producer_of(artifacts.kind(identifier)) is None
    assert isinstance(worksheet.producer_of(TOTAL_NET_INCOME), RecordTotal)


def test_the_instances_are_not_on_the_returns_worksheet() -> None:
    worksheet = service(rental_manifest()).compute(EX_ON, 2025, TWO_RENTALS)["ex-on/return"][0]

    with pytest.raises(MissingArtifactError, match="no value for 'rentals'"):
        worksheet.get(RENTALS)


def test_compute_runs_the_set_that_compose_wires() -> None:
    computation = service(rental_manifest())

    computed = computation.compute(EX_ON, 2025, TWO_RENTALS)
    ran = computation.compose(EX_ON, 2025).compute(TWO_RENTALS)

    assert list(computed) == list(ran)
    assert computed[RETURN][0].get(TOTAL_NET_INCOME) == ran[RETURN][0].get(TOTAL_NET_INCOME)
    assert computed[RETURN][0].trace == ran[RETURN][0].trace


def test_an_inner_artifact_that_is_not_an_export_never_reaches_the_returns_worksheet() -> None:
    worksheet = service(rental_manifest()).compute(EX_ON, 2025, TWO_RENTALS)["ex-on/return"][0]

    inner: tuple[ArtifactKind[Any], ...] = (GROSS_RENT, EXPENSES, NET_INCOME, UNITS, UNITS_DOUBLED)
    for kind in inner:
        with pytest.raises(MissingArtifactError, match="no value"):
            worksheet.get(kind)


# --- zero instances --------------------------------------------------------------------------


def test_no_instances_still_produces_every_export_as_an_empty_record_list() -> None:
    artifacts = artifact_registry()

    worksheet = service(rental_manifest(), artifacts).compute(EX_ON, 2025, rentals())[
        "ex-on/return"
    ][0]

    assert worksheet.get(artifacts.kind("ex/rental.net_income")).value == RecordList(
        (NET_INCOME,), []
    )
    assert worksheet.get(artifacts.kind("ex/rental.units_doubled")).value == RecordList(
        (UNITS_DOUBLED,), []
    )
    assert worksheet.get(TOTAL_NET_INCOME).value == D(0)


def test_no_instances_leaves_every_form_without_worksheets_but_the_default_form() -> None:
    computation = service(rental_manifest())

    result = computation.compute(EX_ON, 2025, rentals())

    assert result["ex/rental"] == ()
    (returned,) = result[RETURN]
    assert returned.trace == (RecordTotalLine(TOTAL_NET_INCOME, NET_INCOME, (), D(0)),)


# --- the trace: one line per worksheet, in run order ------------------------------------------


def test_each_worksheets_trace_is_grouped_in_one_line_named_by_form_and_position() -> None:
    computation = service(rental_manifest())

    lines = computation.compose(EX_ON, 2025).trace(computation.compute(EX_ON, 2025, TWO_RENTALS))

    first, second, returned = lines
    assert isinstance(first, FormInstanceLine) and isinstance(second, FormInstanceLine)
    assert isinstance(returned, FormInstanceLine)
    assert (first.form, first.position) == ("ex/rental", 1)
    assert (second.form, second.position) == ("ex/rental", 2)
    assert (returned.form, returned.position) == (RETURN, 1)
    assert returned.lines == (
        RecordTotalLine(TOTAL_NET_INCOME, NET_INCOME, (D("10000"), D("4000")), D("14000")),
    )


def test_an_instances_lines_are_those_of_its_own_run() -> None:
    computation = service(rental_manifest())

    first, second, _returned = computation.compose(EX_ON, 2025).trace(
        computation.compute(EX_ON, 2025, TWO_RENTALS)
    )
    assert isinstance(first, FormInstanceLine) and isinstance(second, FormInstanceLine)

    def results(line: FormInstanceLine) -> list[Decimal]:
        return [inner.result for inner in line.lines if isinstance(inner, SubtractedLine)]

    assert results(first) == [D("10000")]
    assert results(second) == [D("4000")]
    assert StepLine("doubled", D(2)) in first.lines
    assert StepLine("doubled", D(0)) in second.lines
    assert len(first.lines) == len(second.lines) == 2


# --- per-instance worksheets, by form name -----------------------------------------------------


def test_compute_keeps_every_instances_worksheet_by_form_and_instance_order() -> None:
    result = service(rental_manifest()).compute(EX_ON, 2025, TWO_RENTALS)

    assert type(result) is dict
    first, second = result["ex/rental"]
    assert first.get(NET_INCOME).value == D("10000")
    assert second.get(NET_INCOME).value == D("4000")
    assert first.get(GROSS_RENT).value == D("12000")
    assert [each[UNIT_AMOUNT] for each in first.get(UNITS).value.records] == [D(100), D("250.50")]
    assert result[RETURN][0].get(TOTAL_NET_INCOME).value == D("14000")
    assert list(result) == ["ex/rental", RETURN]
    assert len(result[RETURN]) == 1


def test_the_default_forms_worksheet_holds_its_inputs_imports_and_intermediates() -> None:
    reads_other = CapabilitySelection(
        name="core/subtract",
        params={},
        consumes={"amount": "ex/total_net_income", "less": "ex/other_amount"},
        produces={"output": "ex/spare"},
    )
    manifest = edited(
        rental_manifest(),
        capabilities=(TOTAL, COUNT_DOUBLED, reads_other),
        inputs=frozenset({"ex/rentals", "ex/other_amount"}),
        outputs=frozenset({"ex/spare", "ex/doubled_count"}),
    )

    result = service(manifest).compute(EX_ON, 2025, TWO_RENTALS, Artifact(OTHER_AMOUNT, D(4000)))

    (returns,) = result[RETURN]
    assert returns.get(OTHER_AMOUNT).value == D(4000)
    assert returns.get(NET_INCOME_PER_RENTAL).value.records[0][NET_INCOME] == D(10000)
    assert returns.get(TOTAL_NET_INCOME).value == D(14000)
    assert returns.get(SPARE).value == D(10000)


# --- compose ----------------------------------------------------------------------------------


def test_compose_holds_the_default_forms_composition_with_its_imports_as_inputs() -> None:
    composition = service(rental_manifest()).compose(EX_ON, 2025).form(RETURN).composition

    assert {type(c) for c in composition.order} == {RecordTotal, CountRecords}
    with pytest.raises(InvalidCompositionError, match="'rentals' is not an input"):
        composition.compute(TWO_RENTALS)


def test_compose_holds_the_forms_in_run_order_the_default_form_among_them() -> None:
    forms = service(both_manifest(), artifact_registry()).compose(EX_ON, 2025)

    assert isinstance(forms, FormSet)
    assert [found.name for found in forms.forms] == ["ex/rental", "ex/scaling", RETURN]
    assert forms.form(RETURN).name == RETURN
    assert forms.form(RETURN).instances is None
    assert forms.form(RETURN).imports == frozenset(
        {NET_INCOME_PER_RENTAL, UNITS_DOUBLED_PER_RENTAL, SCALED_PER_BASE}
    )


def test_a_manifest_of_the_default_form_alone_composes_and_computes_as_before() -> None:
    plain = manifest_of(
        (
            CapabilitySelection(
                name="core/subtract",
                params={},
                consumes={"amount": "ex/gross_rent", "less": "ex/expenses"},
                produces={"output": "ex/net_income"},
            ),
        ),
        inputs=frozenset({"ex/gross_rent", "ex/expenses"}),
        outputs=frozenset({"ex/net_income"}),
    )
    computation = service(plain)
    given = (Artifact(GROSS_RENT, D(5)), Artifact(EXPENSES, D(2)))

    result = computation.compute(EX_ON, 2025, *given)

    (worksheet,) = result[RETURN]
    assert list(result) == [RETURN]
    assert worksheet.get(NET_INCOME).value == D(3)
    forms = computation.compose(EX_ON, 2025)
    assert [type(c) for c in forms.form(RETURN).composition.order] == [Subtract]
    assert [found.name for found in forms.forms] == [RETURN]
    assert len(forms.trace(result)) == 1


def test_the_manifest_of_the_default_form_alone_refuses_what_the_composition_refused() -> None:
    plain = manifest_of(
        (NET,),
        inputs=frozenset({"ex/gross_rent", "ex/expenses"}),
        outputs=frozenset({"ex/net_income"}),
    )

    with pytest.raises(InvalidCompositionError, match="missing input 'expenses'"):
        service(plain).compute(EX_ON, 2025, Artifact(GROSS_RENT, D(5)))


def test_two_forms_are_peers_each_with_its_own_worksheets_and_exports() -> None:
    artifacts = artifact_registry()
    manifest = both_manifest()
    bases = Artifact(BASES, RecordList(BASES.fields, [{BASE: D("2")}, {BASE: D("5")}]))

    result = service(manifest, artifacts).compute(EX_ON, 2025, TWO_RENTALS, bases)

    (worksheet,) = result[RETURN]
    assert worksheet.get(TOTAL_NET_INCOME).value == D("14000")
    assert worksheet.get(SCALED_TOTAL).value == D("21")
    assert worksheet.get(artifacts.kind("ex/scaling.scaled")).value.records[1][SCALED] == D("15")
    assert result["ex/scaling"][1].get(SCALED).value == D("15")


def test_a_form_reads_another_forms_export_whichever_is_listed_first() -> None:
    artifacts = artifact_registry()
    for listed in ((SUMMARY, RENTAL), (RENTAL, SUMMARY)):
        manifest = edited(summary_manifest(), forms=listed)
        summaries = Artifact(
            SUMMARIES, RecordList(SUMMARIES.fields, [{OTHER_AMOUNT: D(100)}, {OTHER_AMOUNT: D(1)}])
        )

        result = service(manifest, artifacts).compute(EX_ON, 2025, TWO_RENTALS, summaries)

        assert list(result) == ["ex/rental", "ex/summary", RETURN]
        assert result["ex/summary"][0].get(SPARE).value == D(13900)
        assert result["ex/summary"][1].get(SPARE).value == D(13999)
        assert result[RETURN][0].get(SPARE_TOTAL).value == D(27899)


def test_the_instances_kind_must_be_one_of_the_manifests_inputs() -> None:
    # The return reads two other amounts, so its inputs are used; the form's `ex/rentals` is not
    # among them and nothing produces it.
    reads_others = CapabilitySelection(
        name="core/subtract",
        params={},
        consumes={"amount": "ex/other_amount", "less": "ex/notes"},
        produces={"output": "ex/spare"},
    )
    manifest = edited(
        rental_manifest(),
        capabilities=(TOTAL, COUNT_DOUBLED, reads_others),
        inputs=frozenset({"ex/other_amount", "ex/notes"}),
        outputs=frozenset({"ex/total_net_income", "ex/doubled_count", "ex/spare"}),
    )

    with pytest.raises(
        InvalidCompositionError, match="form 'ex/rental': instances 'ex/rentals' is not an input"
    ):
        service(manifest).compose(EX_ON, 2025)


def test_the_computation_takes_the_instances_and_nothing_else_of_the_form() -> None:
    computation = service(rental_manifest())

    with pytest.raises(InvalidCompositionError, match="missing input 'rentals'"):
        computation.compute(EX_ON, 2025)
    with pytest.raises(InvalidCompositionError, match="'gross_rent' is not an input"):
        computation.compute(EX_ON, 2025, TWO_RENTALS, Artifact(GROSS_RENT, D(1)))


def test_an_import_nothing_exports_is_refused_naming_the_form_and_the_kind() -> None:
    ghost = RecordListKind("ex/ghost.profit", fields=(NET_INCOME,))
    artifacts = artifact_registry(ghost)
    reads_ghost = CapabilitySelection(
        name="core/record_total",
        params={},
        consumes={"records": "ex/ghost.profit"},
        produces={"output": "ex/spare"},
    )
    manifest = edited(
        rental_manifest(),
        capabilities=(TOTAL, COUNT_DOUBLED, reads_ghost),
        outputs=frozenset({"ex/total_net_income", "ex/doubled_count", "ex/spare"}),
    )

    with pytest.raises(InvalidCompositionError, match=r"ex-on/return.*'ghost.profit'"):
        service(manifest, artifacts).compose(EX_ON, 2025)


def test_a_cycle_of_forms_is_refused_naming_them() -> None:
    manifest = edited(summary_manifest(), forms=(CYCLE_RENTAL, SUMMARY))

    with pytest.raises(InvalidCompositionError, match="cycle") as caught:
        service(manifest).compose(EX_ON, 2025)

    assert "ex/rental" in str(caught.value) and "ex/summary" in str(caught.value)


# --- the derived kinds are registered at compose time, idempotently ---------------------------


def test_compose_registers_the_derived_kinds_by_their_dotted_identifiers() -> None:
    artifacts = artifact_registry()
    assert "ex/rental.net_income" not in artifacts.identifiers()

    service(rental_manifest(), artifacts).compose(EX_ON, 2025)

    assert artifacts.kind("ex/rental.net_income") == NET_INCOME_PER_RENTAL
    assert artifacts.kind("ex/rental.units_doubled") == UNITS_DOUBLED_PER_RENTAL


def test_composing_twice_registers_the_derived_kinds_once_and_keeps_the_first() -> None:
    artifacts = artifact_registry()
    computation = service(rental_manifest(), artifacts)

    first = computation.compose(EX_ON, 2025)
    registered = artifacts.kind("ex/rental.net_income")
    second = computation.compose(EX_ON, 2025)

    assert artifacts.kind("ex/rental.net_income") is registered
    assert second.forms[0].derived == (NET_INCOME_PER_RENTAL, UNITS_DOUBLED_PER_RENTAL)
    assert [f.name for f in first.forms] == [f.name for f in second.forms]


def test_each_compose_computes_the_same_figures() -> None:
    computation = service(rental_manifest())

    totals = [
        computation.compute(EX_ON, 2025, TWO_RENTALS)[RETURN][0].get(TOTAL_NET_INCOME).value
        for _ in range(3)
    ]

    assert totals == [D("14000")] * 3


def test_two_services_on_one_registry_agree_on_the_derived_kinds() -> None:
    artifacts = artifact_registry()

    service(rental_manifest(), artifacts).compose(EX_ON, 2025)
    service(rental_manifest(), artifacts).compose(EX_ON, 2025)

    assert artifacts.kind("ex/rental.net_income") == NET_INCOME_PER_RENTAL


@pytest.mark.parametrize(
    "other",
    [
        ArtifactKind("ex/rental.net_income", Decimal),
        RecordListKind("ex/rental.net_income", fields=(GROSS_RENT,)),
    ],
    ids=["a-plain-amount", "a-list-of-another-field"],
)
def test_another_kind_under_a_derived_identifier_is_an_error(other: ArtifactKind[Any]) -> None:
    artifacts = artifact_registry(other)

    with pytest.raises(DuplicateRegistrationError, match=r"ex/rental\.net_income"):
        service(rental_manifest(), artifacts).compose(EX_ON, 2025)


# --- the form's selections are built like the returns: datasets, once per form ---------------


def test_the_forms_datasets_are_fetched_once_for_the_tax_year_not_once_per_instance() -> None:
    parameters = FakeParameters(factor_data())
    bases = Artifact(
        BASES, RecordList(BASES.fields, [{BASE: D("2")}, {BASE: D("5")}, {BASE: D("7")}])
    )

    worksheet = service(scaling_manifest(), parameters=parameters).compute(EX_ON, 2025, bases)[
        "ex-on/return"
    ][0]

    assert worksheet.get(SCALED_TOTAL).value == D("42")
    assert parameters.requests.count(("ex/factor", 2025, FACTOR)) == 1


def test_a_forms_dataset_of_another_tax_year_is_not_used() -> None:
    parameters = FakeParameters(factor_data(2024))

    with pytest.raises(NotFoundError, match="ex/factor"):
        service(scaling_manifest(), parameters=parameters).compose(EX_ON, 2025)


def test_the_scaling_forms_trace_has_one_line_per_instance() -> None:
    bases = Artifact(BASES, RecordList(BASES.fields, [{BASE: D("2")}, {BASE: D("5")}]))
    computation = service(scaling_manifest())

    lines = computation.compose(EX_ON, 2025).trace(computation.compute(EX_ON, 2025, bases))

    assert lines[:2] == (
        FormInstanceLine("ex/scaling", 1, (StepLine("scaled", D("6")),)),
        FormInstanceLine("ex/scaling", 2, (StepLine("scaled", D("15")),)),
    )


# --- errors name the form and the instance position -------------------------------------------


@pytest.mark.parametrize("position", [1, 2])
def test_a_failure_inside_an_instance_names_the_form_and_the_instance(position: int) -> None:
    # `ex/net_income` is non-negative, so a loss in one instance breaks the Subtract contract.
    instances = [("1000", "100", units()), ("1000", "100", units())]
    instances[position - 1] = ("100", "500", units())

    with pytest.raises(
        CapabilityContractError, match=rf"ex/rental, instance {position}\b"
    ) as caught:
        service(rental_manifest()).compute(EX_ON, 2025, rentals(*instances))

    assert "net_income" in str(caught.value)


def test_an_inner_input_nothing_reads_is_refused_naming_the_form() -> None:
    wider = RecordListKind("ex/rentals", fields=(GROSS_RENT, EXPENSES, UNITS, NOTES))
    artifacts = artifact_registry(rentals_kind=wider)

    with pytest.raises(InvalidCompositionError, match="ex/rental") as caught:
        service(rental_manifest(replace(RENTAL, fields=required_fields(wider))), artifacts).compose(
            EX_ON, 2025
        )

    assert "'notes' is consumed by nothing" in str(caught.value)


def test_an_inner_selection_with_no_producer_is_refused_naming_the_form() -> None:
    lost = CapabilitySelection(
        name="core/subtract",
        params={},
        consumes={"amount": "ex/net_income", "less": "ex/other_amount"},
        produces={"output": "ex/spare"},
    )
    form = replace(RENTAL, capabilities=(NET, DOUBLE, lost))

    with pytest.raises(InvalidCompositionError, match="ex/rental") as caught:
        service(rental_manifest(form)).compose(EX_ON, 2025)

    assert "no producer for 'other_amount', consumed by Subtract" in str(caught.value)


def test_an_inner_output_nothing_reads_or_exports_is_refused_naming_the_form() -> None:
    stray = CapabilitySelection(
        name="core/subtract",
        params={},
        consumes={"amount": "ex/net_income", "less": "ex/expenses"},
        produces={"output": "ex/spare"},
    )
    form = replace(RENTAL, capabilities=(NET, DOUBLE, stray))

    with pytest.raises(InvalidCompositionError, match="ex/rental") as caught:
        service(rental_manifest(form)).compose(EX_ON, 2025)

    assert "orphan output 'spare'" in str(caught.value)


def test_an_export_nothing_in_the_form_produces_is_refused_naming_the_form() -> None:
    form = replace(RENTAL, exports=("ex/net_income", "ex/units_doubled", "ex/spare"))

    with pytest.raises(InvalidCompositionError, match="ex/rental") as caught:
        service(rental_manifest(form)).compose(EX_ON, 2025)

    assert "declared output 'spare' is produced by nothing" in str(caught.value)


def test_an_export_that_is_neither_an_amount_a_count_nor_a_record_list_is_not_importable() -> None:
    describe = CapabilitySelection(
        name="ex/describe",
        params={},
        consumes={"source": "ex/base"},
        produces={"note": "ex/note"},
    )
    form = Form(
        required=True,
        name="ex/labelled",
        instances="ex/bases",
        fields=required_fields(BASES),
        exports=("ex/note",),
        capabilities=(describe,),
    )
    manifest = manifest_of(
        (), inputs=frozenset({"ex/bases"}), outputs=frozenset({"ex/bases"}), forms=(form,)
    )
    bases = Artifact(BASES, RecordList(BASES.fields, [{BASE: D("2")}]))
    computation = service(manifest)

    forms = computation.compose(EX_ON, 2025)
    (worksheet,) = computation.compute(EX_ON, 2025, bases)["ex/labelled"]

    assert forms.form("ex/labelled").derived == ()
    assert worksheet.get(NOTE).value == "x"


def test_instances_that_are_not_a_registered_kind_are_unknown() -> None:
    form = replace(RENTAL, instances="ex/nowhere")

    with pytest.raises(UnknownRegistrationError, match="ex/nowhere"):
        service(rental_manifest(form, inputs=frozenset({"ex/nowhere"}))).compose(EX_ON, 2025)


def test_instances_that_are_not_a_record_list_kind_are_refused_naming_the_form() -> None:
    form = replace(RENTAL, instances="ex/gross_rent")

    with pytest.raises(InvalidCompositionError) as caught:
        service(rental_manifest(form, inputs=frozenset({"ex/gross_rent"}))).compose(EX_ON, 2025)

    assert "ex/rental" in str(caught.value)
    assert "ex/gross_rent" in str(caught.value)


# --- limits: the manifest's maximum and exclusive group reach the form set ---------------------


def test_a_forms_maximum_is_enforced_on_the_instances_given() -> None:
    manifest = rental_manifest(replace(RENTAL, max_instances=1))

    with pytest.raises(ValidationError, match=r"form 'ex/rental' allows at most 1 instance\(s\)"):
        service(manifest).compute(EX_ON, 2025, TWO_RENTALS)


def test_a_form_within_its_maximum_computes() -> None:
    manifest = rental_manifest(replace(RENTAL, max_instances=2))

    worksheet = service(manifest).compute(EX_ON, 2025, TWO_RENTALS)["ex-on/return"][0]

    assert worksheet.get(TOTAL_NET_INCOME).value == D("14000")


def test_two_forms_of_a_group_with_instances_are_refused_naming_both() -> None:
    manifest = replace(
        both_manifest(),
        forms=(
            replace(RENTAL, exclusive_group="ex/either"),
            replace(SCALING, exclusive_group="ex/either"),
        ),
    )
    bases = Artifact(BASES, RecordList(BASES.fields, [{BASE: D(1)}]))

    with pytest.raises(ValidationError, match=r"'ex/rental'.*'ex/scaling'.*'ex/either'"):
        service(manifest).compute(EX_ON, 2025, TWO_RENTALS, bases)


def test_a_group_naming_one_form_is_refused_when_the_form_set_is_built() -> None:
    manifest = rental_manifest(replace(RENTAL, exclusive_group="ex/alone"))

    with pytest.raises(InvalidCompositionError, match="exclusive group 'ex/alone'.*'ex/rental'"):
        service(manifest).compose(EX_ON, 2025)


# --- limits: a minimum, and limits on the default list of a form without instances ---------------


def with_default_limits(manifest: Manifest, **limits: Any) -> Manifest:
    """The manifest with the limits on its default form `ex-on/return` (one default instance)."""
    return replace(
        manifest,
        forms=tuple(replace(f, **limits) if f.name == RETURN else f for f in manifest.forms),
    )


def test_a_forms_minimum_is_enforced_on_the_instances_given() -> None:
    manifest = rental_manifest(replace(RENTAL, min_instances=3))

    with pytest.raises(
        ValidationError, match=r"form 'ex/rental' needs at least 3 instance\(s\), got 2"
    ):
        service(manifest).compute(EX_ON, 2025, TWO_RENTALS)


def test_a_form_within_its_minimum_and_maximum_computes() -> None:
    manifest = rental_manifest(replace(RENTAL, min_instances=2, max_instances=2))

    worksheet = service(manifest).compute(EX_ON, 2025, TWO_RENTALS)["ex-on/return"][0]

    assert worksheet.get(TOTAL_NET_INCOME).value == D("14000")


def test_a_minimum_above_the_maximum_is_refused_naming_the_form() -> None:
    with pytest.raises(InvalidManifestError, match="form 'ex/rental': min_instances 3 is above"):
        replace(RENTAL, min_instances=3, max_instances=2)


def test_a_declared_empty_list_is_refused_by_a_minimum_of_one() -> None:
    manifest = rental_manifest(replace(RENTAL, min_instances=1))
    empty = Artifact(RENTALS, RecordList(RENTALS.fields, []))

    with pytest.raises(
        ValidationError, match=r"form 'ex/rental' needs at least 1 instance\(s\), got 0"
    ):
        service(manifest).compute(EX_ON, 2025, empty)


def test_exactly_one_instance_on_a_declared_list() -> None:
    manifest = rental_manifest(replace(RENTAL, min_instances=1, max_instances=1))
    one = rentals(("12000", "2000", units()))

    worksheet = service(manifest).compute(EX_ON, 2025, one)["ex-on/return"][0]

    assert worksheet.get(TOTAL_NET_INCOME).value == D("10000")
    with pytest.raises(ValidationError, match="allows at most 1"):
        service(manifest).compute(EX_ON, 2025, TWO_RENTALS)


def test_exactly_one_instance_on_a_default_list_is_a_no_op() -> None:
    manifest = with_default_limits(rental_manifest(), min_instances=1, max_instances=1)

    worksheet = service(manifest).compute(EX_ON, 2025, TWO_RENTALS)["ex-on/return"][0]

    assert worksheet.get(TOTAL_NET_INCOME).value == D("14000")


def test_a_minimum_of_zero_on_a_default_list_is_a_no_op() -> None:
    manifest = with_default_limits(rental_manifest(), min_instances=0)

    assert service(manifest).compute(EX_ON, 2025, TWO_RENTALS)["ex-on/return"]


def test_a_minimum_above_one_on_a_default_list_is_refused_when_the_manifest_is_built() -> None:
    with pytest.raises(InvalidManifestError) as caught:
        with_default_limits(rental_manifest(), min_instances=2)

    assert str(caught.value) == (
        "form 'ex-on/return': min_instances 2 can never hold: "
        "a form without an instances list has one instance"
    )


def test_a_default_list_form_claims_its_group() -> None:
    manifest = with_default_limits(
        rental_manifest(replace(RENTAL, exclusive_group="ex/either")), exclusive_group="ex/either"
    )
    empty = Artifact(RENTALS, RecordList(RENTALS.fields, []))

    with pytest.raises(
        ValidationError,
        match=r"'ex-on/return'.*'ex/rental'.*'ex/either'|'ex/rental'.*'ex-on/return'.*'ex/either'",
    ):
        service(manifest).compute(EX_ON, 2025, TWO_RENTALS)
    assert service(manifest).compute(EX_ON, 2025, empty)


def test_two_forms_of_a_group_that_both_require_an_instance_are_refused_when_composed() -> None:
    manifest = replace(
        both_manifest(),
        forms=(
            replace(RENTAL, exclusive_group="ex/either", min_instances=1),
            replace(SCALING, exclusive_group="ex/either", min_instances=1),
        ),
    )

    with pytest.raises(InvalidCompositionError, match=r"'ex/either'.*'ex/rental'.*'ex/scaling'"):
        service(manifest).compose(EX_ON, 2025)


# --- required, defaults, fields and predicates, checked against the artifact kinds ---------------


def test_a_field_of_the_instances_kind_the_manifest_does_not_declare_is_refused_at_compose() -> (
    None
):
    form = replace(RENTAL, fields=required_fields(RENTALS)[:-1])

    with pytest.raises(InvalidManifestError, match="form 'ex/rental': field 'ex/units' of "):
        service(rental_manifest(form)).compose(EX_ON, 2025)


def test_a_declared_field_the_instances_kind_does_not_have_is_refused_at_compose() -> None:
    ghost = InputDeclaration(name="ex/ghost", required=True)
    form = replace(RENTAL, fields=(*required_fields(RENTALS), ghost))

    with pytest.raises(InvalidManifestError, match="field 'ex/ghost' is not a field of "):
        service(rental_manifest(form)).compose(EX_ON, 2025)


def test_a_field_default_that_does_not_suit_its_kind_is_refused_at_compose() -> None:
    expenses = InputDeclaration("ex/expenses", False, Default("lots"), "Line 2")
    fields = tuple(
        expenses if field.name == "ex/expenses" else field for field in required_fields(RENTALS)
    )

    with pytest.raises(InvalidManifestError, match="input 'ex/expenses': default 'lots' must be"):
        service(rental_manifest(replace(RENTAL, fields=fields))).compose(EX_ON, 2025)


def test_an_optional_field_with_a_default_that_suits_its_kind_composes() -> None:
    expenses = InputDeclaration("ex/expenses", False, Default("0"), "Line 2")
    fields = tuple(
        expenses if field.name == "ex/expenses" else field for field in required_fields(RENTALS)
    )

    service(rental_manifest(replace(RENTAL, fields=fields))).compose(EX_ON, 2025)


def test_an_input_default_that_does_not_suit_its_kind_is_refused_at_compose() -> None:
    manifest = rental_manifest()
    inputs = {
        **manifest.inputs,
        "ex/rentals": InputDeclaration("ex/rentals", False, Default("0"), "Line 1"),
    }

    with pytest.raises(
        InvalidManifestError, match="input 'ex/rentals': default '0' must be an empty"
    ):
        service(replace(manifest, inputs=inputs)).compose(EX_ON, 2025)


@pytest.mark.parametrize("kind", [GROSS_RENT, OTHER_AMOUNT])
def test_an_optional_form_gated_by_a_money_amount_is_refused_at_compose(
    kind: ArtifactKind[Any],
) -> None:
    gated = replace(
        SCALING, required=False, required_when=kind.identifier, basis="Complete this form if ..."
    )
    inputs = frozenset({*scaling_manifest().inputs, kind.identifier})
    manifest = edited(scaling_manifest(), inputs=inputs, forms=(gated,))

    with pytest.raises(InvalidManifestError, match="required_when 'ex/.*' is not a yes/no"):
        service(manifest).compose(EX_ON, 2025)
