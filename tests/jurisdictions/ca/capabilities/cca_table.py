"""Shared test data for the capital cost allowance capabilities, T776 and T2125 Area A.

The `class_rates` dataset holds the classes these tests use, with the rates of Guides T4036 and
T4002 ("Class 1 (4%)", "Class 8 (20%)", "Class 10 (30%)", "Class 10.1 (30%)", "Class 12 (100%)",
"Class 43.1 (30%)", "Class 50 (55%)", "Class 53 (50%)", "Class 55 (40%)") and the factors of
T776 Notes 7 and 8: "one and one half (Classes 43.1, 54, and 56), 7 divided by 8 (Class 55), and
one half (Classes 43.2 and 53)", "9 divided by 11 (Class 50)", "The factor is 0 for any remaining
AIIPs not listed in this note"; "two and one third (Classes 43.1, 46, 54, and 56), one and one
half (Class 55), 1 (Class 53), 9 divided by 11 (Class 50), and 0 (Classes 12, 13, 14, 15, and
59). The factor is one half for any remaining RIIPs not listed in this note." Class 12 is exempt
from the half-year rule and Class 10.1 excluded from recapture and terminal loss, as decided on the
ticket.

The list of classes, the list of column 22 amounts ("Column 22: Non-compliant amount of CCA (see
Chart B below)", one record of the class number and the amount per class) and the produced kinds
are made-up `ex/` kinds, declared here and not in the catalog: the rental and the business lists
are declared when T776 and T2125 are wired. The fields are the catalog's own `ca/` kinds. Each
record of the classes holds one Area A row: column 1 (the class number), column 2, column 3,
column 5, column 11, column 12, the CCA claimed and whether no property is left in the class
(Note 3).
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any, cast

from tax_engine.application.services.tax_computation import TaxComputationService
from tax_engine.domain.artifact import Artifact, ArtifactKind, ArtifactRegistry
from tax_engine.domain.capability import CapabilityRegistry
from tax_engine.domain.errors import NotFoundError
from tax_engine.domain.jurisdiction import Jurisdiction
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import CapabilitySelection, Form, Manifest
from tax_engine.domain.parameters.class_rates import (
    CLASS_RATES,
    ClassRate,
    ClassRates,
    HalfYearRule,
    HalfYearRuleOnSale,
    RecaptureAndTerminalLoss,
)
from tax_engine.domain.parameters.datasets import ParameterDataset
from tax_engine.domain.parameters.fraction import Fraction
from tax_engine.domain.parameters.kind import ParameterKind
from tax_engine.domain.parameters.rate import Rate
from tax_engine.domain.parameters.rounding import RoundingMode, RoundingRule, RoundTo
from tax_engine.domain.record_list import RecordList, RecordListKind
from tax_engine.jurisdictions.ca.catalog import (
    CCA_ADDITIONS,
    CCA_AIIP_ADDITIONS,
    CCA_CLAIMED,
    CCA_CLASS_NUMBER,
    CCA_NO_PROPERTY_LEFT,
    CCA_PROCEEDS,
    CCA_RIIP_ADDITIONS,
    CCA_UCC_AT_END,
    CCA_UCC_AT_START,
    NON_COMPLIANT_CCA,
)
from tests.manifest_support import required_inputs

D = Decimal
F = Fraction
CENT = RoundTo(D("0.01"), RoundingMode.HALF_UP)
APPLIES = HalfYearRule.APPLIES
EXEMPT = HalfYearRule.EXEMPT
INCLUDED = RecaptureAndTerminalLoss.APPLIES
EXCLUDED = RecaptureAndTerminalLoss.EXCLUDED
NOT_ON_SALE = HalfYearRuleOnSale.DOES_NOT_APPLY

CLASS_FIELDS = (
    CCA_CLASS_NUMBER,
    CCA_UCC_AT_START,
    CCA_ADDITIONS,
    CCA_PROCEEDS,
    CCA_AIIP_ADDITIONS,
    CCA_RIIP_ADDITIONS,
    CCA_CLAIMED,
    CCA_NO_PROPERTY_LEFT,
)
CLASSES = RecordListKind("ex/cca_classes", fields=CLASS_FIELDS)
NON_COMPLIANT = RecordListKind("ex/non_compliant_cca", fields=(CCA_CLASS_NUMBER, NON_COMPLIANT_CCA))
CCA_CLAIM = ArtifactKind("ex/cca_claim", Decimal, non_negative=True)
RECAPTURED_CCA = ArtifactKind("ex/recaptured_cca", Decimal, non_negative=True)
TERMINAL_LOSS = ArtifactKind("ex/terminal_loss", Decimal, non_negative=True)
CLOSING_UCC = RecordListKind("ex/closing_ucc", fields=(CCA_CLASS_NUMBER, CCA_UCC_AT_END))

CLASS_1 = ClassRate(D("1"), Rate(D("0.04")), APPLIES, INCLUDED, F(0, 1), F(1, 2), NOT_ON_SALE)
CLASS_8 = ClassRate(D("8"), Rate(D("0.20")), APPLIES, INCLUDED, F(0, 1), F(1, 2), NOT_ON_SALE)
CLASS_10 = ClassRate(D("10"), Rate(D("0.30")), APPLIES, INCLUDED, F(0, 1), F(1, 2), NOT_ON_SALE)
CLASS_10_1 = ClassRate(D("10.1"), Rate(D("0.30")), APPLIES, EXCLUDED, F(0, 1), F(1, 2), NOT_ON_SALE)
CLASS_12 = ClassRate(D("12"), Rate(D("1")), EXEMPT, INCLUDED, F(0, 1), F(0, 1), NOT_ON_SALE)
CLASS_43_1 = ClassRate(D("43.1"), Rate(D("0.30")), APPLIES, INCLUDED, F(3, 2), F(7, 3), NOT_ON_SALE)
CLASS_50 = ClassRate(D("50"), Rate(D("0.55")), APPLIES, INCLUDED, F(9, 11), F(9, 11), NOT_ON_SALE)
CLASS_53 = ClassRate(D("53"), Rate(D("0.50")), APPLIES, INCLUDED, F(1, 2), F(1, 1), NOT_ON_SALE)
CLASS_55 = ClassRate(D("55"), Rate(D("0.40")), APPLIES, INCLUDED, F(7, 8), F(3, 2), NOT_ON_SALE)
ALL_CLASSES = (
    CLASS_1,
    CLASS_8,
    CLASS_10,
    CLASS_10_1,
    CLASS_12,
    CLASS_43_1,
    CLASS_50,
    CLASS_53,
    CLASS_55,
)


def class_rates(
    rounding: RoundingRule = CENT,
    classes: tuple[ClassRate, ...] = ALL_CLASSES,
    full_year_days: int = 365,
    longest_fiscal_period_days: int = 366,
) -> ParameterDataset[ClassRates]:
    """By default the classes above, to the cent, with 365 days in a full year and 366 in the
    longest fiscal period."""
    return ParameterDataset(
        "ca/cca_class_rates",
        2025,
        CLASS_RATES,
        ClassRates(classes, full_year_days, longest_fiscal_period_days),
        rounding,
        ("https://example.org/t4036",),
    )


def row(
    number: str,
    ucc_at_start: str = "0",
    additions: str = "0",
    proceeds: str = "0",
    aiip_additions: str = "0",
    riip_additions: str = "0",
    claimed: str = "0",
    no_property_left: int = 0,
) -> dict[ArtifactKind[Any], Decimal | int]:
    """One Area A row: columns 1, 2, 3, 5, 11 and 12, the CCA claimed and Note 3's flag."""
    return {
        CCA_CLASS_NUMBER: D(number),
        CCA_UCC_AT_START: D(ucc_at_start),
        CCA_ADDITIONS: D(additions),
        CCA_PROCEEDS: D(proceeds),
        CCA_AIIP_ADDITIONS: D(aiip_additions),
        CCA_RIIP_ADDITIONS: D(riip_additions),
        CCA_CLAIMED: D(claimed),
        CCA_NO_PROPERTY_LEFT: no_property_left,
    }


def classes(*rows: dict[ArtifactKind[Any], Decimal | int]) -> Artifact[Any]:
    """An `ex/cca_classes` artifact of one record per row, in order."""
    return Artifact(CLASSES, RecordList(CLASSES.fields, rows))


def non_compliant_cca(*amounts: tuple[str, str]) -> Artifact[Any]:
    """An `ex/non_compliant_cca` artifact of one record per (class number, column 22) pair, in
    order."""
    return Artifact(
        NON_COMPLIANT,
        RecordList(
            NON_COMPLIANT.fields,
            [
                {CCA_CLASS_NUMBER: D(number), NON_COMPLIANT_CCA: D(amount)}
                for number, amount in amounts
            ],
        ),
    )


# No class has a column 22.
NO_COLUMN_22 = non_compliant_cca()

# The ticket's acceptance rows. A class with additions: Class 8, UCC 10,000 at the start and
# 3,000 of additions, so column 7 is 13,000, column 18 one half of 3,000 = 1,500, column 19
# 11,500 and the maximum 20% of it, 2,300.00.
WITH_ADDITIONS = row("8", "10000", "3000", claimed="2300")
# A class with a disposition causing recapture: Class 10, UCC 5,000 and proceeds of 8,000, so
# column 7 is -3,000, a recapture of 3,000 (Note 3), no CCA and a UCC of 0 at the end of the year.
WITH_RECAPTURE = row("10", "5000", proceeds="8000")
# A class closing with a terminal loss: Class 1, UCC 20,000, proceeds of 15,000 and no property
# left, so column 7 is 5,000, a terminal loss of 5,000 (Note 3), no CCA and a UCC of 0.
WITH_TERMINAL_LOSS = row("1", "20000", proceeds="15000", no_property_left=1)


class _Jurisdictions:
    def __init__(self, jurisdiction: Jurisdiction) -> None:
        self._jurisdiction = jurisdiction

    def get_jurisdiction(self, code: JurisdictionCode) -> Jurisdiction:
        return self._jurisdiction


class _Parameters:
    def __init__(self, dataset: ParameterDataset[ClassRates]) -> None:
        self._dataset = dataset

    def get[T](self, family: str, tax_year: int, kind: ParameterKind[T]) -> ParameterDataset[T]:
        if (family, tax_year, kind) != (self._dataset.family, 2025, CLASS_RATES):
            raise NotFoundError(f"no {family} dataset for tax year {tax_year}")
        return cast(ParameterDataset[T], self._dataset)


def service(
    capability: str,
    output: ArtifactKind[Any],
    dataset: ParameterDataset[ClassRates] | None = None,
    checks_claim: bool = False,
    classes_kind: ArtifactKind[Any] = CLASSES,
    extra: Mapping[str, ArtifactKind[Any]] | None = None,
) -> TaxComputationService:
    """A computation of the one `capability` over `classes_kind` (`ex/cca_classes` unless given),
    producing `output`; one that refuses a claim (`checks_claim`) also consumes
    `ex/non_compliant_cca` as `non_compliant`, and `extra` maps further consumed slot names to
    their kinds."""
    dataset = dataset or class_rates()
    extra = extra or {}
    code = JurisdictionCode("CA-ON")
    consumes = {"classes": classes_kind.identifier}
    if checks_claim:
        consumes["non_compliant"] = NON_COMPLIANT.identifier
    consumes |= {slot: kind.identifier for slot, kind in extra.items()}
    inputs = frozenset(consumes.values())
    selection = CapabilitySelection(
        name=capability,
        params={"class_rates": dataset.family},
        consumes=consumes,
        produces={"output": output.identifier},
    )
    manifest = Manifest(
        jurisdiction=code,
        version=1,
        valid_from_tax_year=2025,
        inputs=required_inputs(inputs),
        forms=(
            Form(
                required=True,
                name=code.namespace.identifier("return"),
                instances=None,
                exports=(output.identifier,),
                capabilities=(selection,),
            ),
        ),
    )
    artifacts = ArtifactRegistry()
    for kind in (classes_kind, NON_COMPLIANT, output, *extra.values()):
        artifacts.register(kind.identifier, kind)
    return TaxComputationService(
        _Jurisdictions(Jurisdiction(code=code, manifests=(manifest,))),
        _Parameters(dataset),
        CapabilityRegistry.shared(),
        artifacts,
    )
