"""Shared test data for the CcaVehicleProceeds capability, Form T2125 Area A endnote 2.

T2125 (2025), Area A endnote 2: "The proceeds of disposition of a zero-emission passenger vehicle
(ZEPV) that has been included in Class 54, or a passenger vehicle bought after April 18, 2021, that
has been included in Class 10.1, and whose cost is more than the prescribed amount will be adjusted
based on a factor equal to its prescribed amount as a proportion of the actual cost of the vehicle.
For dispositions after July 29, 2019, you will have to adjust the actual cost of the vehicle for
any payments or repayments of government assistance that you may have received or repaid for the
vehicle. If the passenger vehicle in Class 10.1 is not designated for immediate expensing
treatment, this special rule does not apply."

Guide T4002 2025, "Class 10.1 (30%)": "The capital cost limits of a Class 10.1 passenger vehicle
are the following prescribed amounts: $30,000 for vehicles acquired before 2022, plus the GST/HST
or PST; $34,000 for vehicles acquired in 2022, plus the GST/HST or PST; $36,000 for vehicles
acquired in 2023, plus the GST/HST or PST; $37,000 for vehicles acquired in 2024, plus the GST/HST
or PST; $38,000 for vehicles acquired in 2025, plus the GST/HST or PST".

The dataset is a made-up `example.org` dataset of those five prescribed amounts, a `year_amounts`
table with the amount `prescribed_amount` and a half-up rounding to the cent. The list of classes
and the produced list are the catalog's own `ca/business_cca_classes` and
`ca/business_cca_classes_adjusted`; each record of the classes holds the Area A row's columns and
the three fields of the adjustment (the year the vehicle was acquired, 0 when the rule does not
apply to the row, its actual cost and the government assistance received less repaid). The sales
tax rate is the caller's, in percent, the catalog's `ca/business_vehicle_sales_tax_rate`.

A Class 54 row (Guide T4036 2025, "Class 54 (30%)") also holds a list of its sold zero-emission
passenger vehicles, the catalog's `ca/cca_sold_zepvs`, each with the year it was acquired, its cost,
the government assistance for it, its proceeds and the DIEP part of them; the list is the fourth
field the adjusted list leaves out. The dataset of its prescribed amounts is a made-up
`example.org` `year_amounts` table of the three amounts of Class 54: $61,000 from 2023, $59,000 for
2022 and $55,000 from 2019 (a year before 2019 has no row), also with a half-up rounding to the
cent.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

from tax_engine.application.services.tax_computation import TaxComputationService
from tax_engine.domain.artifact import Artifact, ArtifactKind, ArtifactRegistry
from tax_engine.domain.capability import CapabilityRegistry
from tax_engine.domain.errors import NotFoundError
from tax_engine.domain.jurisdiction import Jurisdiction
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import CapabilitySelection, Form, Manifest
from tax_engine.domain.parameters.datasets import ParameterDataset
from tax_engine.domain.parameters.kind import ParameterKind
from tax_engine.domain.parameters.rounding import RoundingMode, RoundingRule, RoundTo
from tax_engine.domain.parameters.year_amounts import YEAR_AMOUNTS, YearAmounts, YearAmountsRow
from tax_engine.domain.record_list import RecordList, RecordListKind
from tax_engine.jurisdictions.ca.capabilities.cca_vehicle_proceeds import CcaVehicleProceeds
from tax_engine.jurisdictions.ca.catalog import (
    BUSINESS_CCA_CLASSES,
    BUSINESS_CCA_CLASSES_ADJUSTED,
    BUSINESS_VEHICLE_SALES_TAX_RATE,
    CCA_ADDITIONS,
    CCA_AIIP_ADDITIONS,
    CCA_CLAIMED,
    CCA_CLASS_NUMBER,
    CCA_DIEP_ADDITIONS,
    CCA_DIEP_PROCEEDS,
    CCA_HALF_YEAR_RULE_DIFFERS,
    CCA_IMMEDIATE_EXPENSING,
    CCA_NO_PROPERTY_LEFT,
    CCA_PERSONAL_PART_REMAINING,
    CCA_PROCEEDS,
    CCA_RATE_ELECTION,
    CCA_RIIP_ADDITIONS,
    CCA_SOLD_ZEPVS,
    CCA_UCC_AT_START,
    CCA_VEHICLE_ACQUIRED_YEAR,
    CCA_VEHICLE_COST,
    CCA_VEHICLE_GOVERNMENT_ASSISTANCE,
    CCA_ZEPV_DIEP_PROCEEDS,
    CCA_ZEPV_PROCEEDS,
)
from tax_engine.jurisdictions.ca.trace import CcaVehicleProceedsLine, CcaZepvProceedsLine
from tests.manifest_support import required_inputs

D = Decimal
CENT = RoundTo(D("0.01"), RoundingMode.HALF_UP)
DOLLAR = RoundTo(D("1"), RoundingMode.HALF_UP)
SOURCES = ("https://example.org/t4002",)
FAMILY = "ca/cca_vehicle_prescribed_amounts"
ZEPV_FAMILY = "ca/cca_zepv_prescribed_amounts"

# A row of the classes: the Area A fields, and the sold vehicles of a Class 54 row.
CcaRow = dict[ArtifactKind[Any], Decimal | int | RecordList]

CLASSES = BUSINESS_CCA_CLASSES
ADJUSTED = BUSINESS_CCA_CLASSES_ADJUSTED
SALES_TAX_RATE = BUSINESS_VEHICLE_SALES_TAX_RATE

# The four fields of the adjustment, the last of the classes and not in the adjusted list: the
# three of a Class 10.1 vehicle and the list of a Class 54 row's sold vehicles.
VEHICLE_FIELDS = (
    CCA_VEHICLE_ACQUIRED_YEAR,
    CCA_VEHICLE_COST,
    CCA_VEHICLE_GOVERNMENT_ASSISTANCE,
    CCA_SOLD_ZEPVS,
)

# Guide T4002 "Class 10.1 (30%)": 38,000 for 2025, 37,000 for 2024, 36,000 for 2023, 34,000 for
# 2022 and 30,000 for a vehicle acquired before 2022 (the open-ended row), each plus the tax.
PRESCRIBED = (
    (2025, "38000"),
    (2024, "37000"),
    (2023, "36000"),
    (2022, "34000"),
    (None, "30000"),
)


def prescribed_amounts(
    rounding: RoundingRule = CENT,
    rows: tuple[tuple[int | None, str], ...] = PRESCRIBED,
) -> ParameterDataset[YearAmounts]:
    """The prescribed amounts by year acquired, newest first: (from_year or None, the
    `prescribed_amount`)."""
    table = YearAmounts(
        tuple(YearAmountsRow(year, {"prescribed_amount": D(amount)}) for year, amount in rows)
    )
    return ParameterDataset(FAMILY, 2025, YEAR_AMOUNTS, table, rounding, SOURCES)


# Guide T4036 "Class 54 (30%)": $61,000 for vehicles acquired after December 31, 2022 (2023 and
# later), $59,000 after December 31, 2021 and before January 1, 2023 (2022), and $55,000 after
# March 18, 2019 and before January 1, 2022 (2019 to 2021, the oldest row: no row before 2019).
ZEPV_PRESCRIBED = (
    (2023, "61000"),
    (2022, "59000"),
    (2019, "55000"),
)


def zepv_prescribed_amounts(
    rounding: RoundingRule = CENT,
    rows: tuple[tuple[int | None, str], ...] = ZEPV_PRESCRIBED,
) -> ParameterDataset[YearAmounts]:
    """The Class 54 prescribed amounts by year acquired, newest first: (from_year or None, the
    `prescribed_amount`)."""
    table = YearAmounts(
        tuple(YearAmountsRow(year, {"prescribed_amount": D(amount)}) for year, amount in rows)
    )
    return ParameterDataset(ZEPV_FAMILY, 2025, YEAR_AMOUNTS, table, rounding, SOURCES)


def capability(
    dataset: ParameterDataset[YearAmounts] | None = None,
    zepv_dataset: ParameterDataset[YearAmounts] | None = None,
) -> CcaVehicleProceeds:
    return CcaVehicleProceeds(
        dataset or prescribed_amounts(),
        zepv_dataset or zepv_prescribed_amounts(),
        CLASSES,
        SALES_TAX_RATE,
        ADJUSTED,
    )


def row(
    number: str = "10.1",
    ucc_at_start: str = "0",
    additions: str = "0",
    proceeds: str = "0",
    diep_proceeds: str = "0",
    *,
    year: int = 0,
    cost: str = "0",
    assistance: str = "0",
    diep_additions: str = "0",
    immediate_expensing: str = "0",
    claimed: str = "0",
    no_property_left: int = 0,
    personal_part_remaining: str = "0",
    half_year_rule_differs: int = 0,
    rate_election: int = 0,
    aiip_additions: str = "0",
    riip_additions: str = "0",
    sold: tuple[CcaRow, ...] = (),
) -> CcaRow:
    """One Area A row of the T2125 list: columns 1, 2, 3, 4, 5, 6, 9, 11, 12 and the claim, the
    other flags, the year, actual cost and government assistance of the adjustment, and the
    vehicles `sold` (none by default; Class 54 only)."""
    return {
        CCA_CLASS_NUMBER: D(number),
        CCA_UCC_AT_START: D(ucc_at_start),
        CCA_ADDITIONS: D(additions),
        CCA_DIEP_ADDITIONS: D(diep_additions),
        CCA_PROCEEDS: D(proceeds),
        CCA_DIEP_PROCEEDS: D(diep_proceeds),
        CCA_IMMEDIATE_EXPENSING: D(immediate_expensing),
        CCA_AIIP_ADDITIONS: D(aiip_additions),
        CCA_RIIP_ADDITIONS: D(riip_additions),
        CCA_CLAIMED: D(claimed),
        CCA_NO_PROPERTY_LEFT: no_property_left,
        CCA_PERSONAL_PART_REMAINING: D(personal_part_remaining),
        CCA_HALF_YEAR_RULE_DIFFERS: half_year_rule_differs,
        CCA_RATE_ELECTION: rate_election,
        CCA_VEHICLE_ACQUIRED_YEAR: year,
        CCA_VEHICLE_COST: D(cost),
        CCA_VEHICLE_GOVERNMENT_ASSISTANCE: D(assistance),
        CCA_SOLD_ZEPVS: RecordList(CCA_SOLD_ZEPVS.fields, sold),
    }


def zepv(
    year: int,
    cost: str,
    proceeds: str,
    diep_proceeds: str = "0",
    assistance: str = "0",
) -> CcaRow:
    """One sold zero-emission passenger vehicle of a Class 54 row: the year it was acquired (0 when
    the rule does not apply to it), its cost, its proceeds, the DIEP part of them and the
    government assistance for it."""
    return {
        CCA_VEHICLE_ACQUIRED_YEAR: year,
        CCA_VEHICLE_COST: D(cost),
        CCA_VEHICLE_GOVERNMENT_ASSISTANCE: D(assistance),
        CCA_ZEPV_PROCEEDS: D(proceeds),
        CCA_ZEPV_DIEP_PROCEEDS: D(diep_proceeds),
    }


def classes(*rows: CcaRow) -> Artifact[Any]:
    """A `ca/business_cca_classes` artifact of one record per row, in order."""
    assert isinstance(CLASSES, RecordListKind)
    return Artifact(CLASSES, RecordList(CLASSES.fields, rows))


def sales_tax_rate(percent: str = "13") -> Artifact[Any]:
    """The GST or HST rate of the caller's province, in percent."""
    return Artifact(SALES_TAX_RATE, D(percent))


def trace_line(
    position: int,
    applied: bool,
    prescribed_amount: str,
    actual_cost: str,
    proceeds: str,
    adjusted_proceeds: str,
    diep_proceeds: str = "0",
    adjusted_diep_proceeds: str = "0",
) -> CcaVehicleProceedsLine:
    return CcaVehicleProceedsLine(
        ADJUSTED,
        position,
        applied,
        D(prescribed_amount),
        D(actual_cost),
        D(proceeds),
        D(adjusted_proceeds),
        D(diep_proceeds),
        D(adjusted_diep_proceeds),
    )


def zepv_line(
    position: int,
    vehicle: int,
    applied: bool,
    prescribed_amount: str,
    actual_cost: str,
    proceeds: str,
    adjusted_proceeds: str,
    diep_proceeds: str = "0",
    adjusted_diep_proceeds: str = "0",
) -> CcaZepvProceedsLine:
    """The line of the vehicle `vehicle` of the row `position`, both from 1."""
    return CcaZepvProceedsLine(
        ADJUSTED,
        position,
        vehicle,
        applied,
        D(prescribed_amount),
        D(actual_cost),
        D(proceeds),
        D(adjusted_proceeds),
        D(diep_proceeds),
        D(adjusted_diep_proceeds),
    )


# Return CZ's vehicle (see returns/2025_return_cz.yaml): a Class 10.1 passenger vehicle bought in
# 2025 for 50,000 plus the 13% HST (56,500.00) and sold for 40,000, all of it a DIEP's: the
# prescribed amount with tax is 38,000 + 4,940 = 42,940 and the factor 42,940 / 56,500 = 0.76, so
# the proceeds become 40,000 x 0.76 = 30,400.00.
SOLD = row(
    "10.1",
    additions="42940",
    proceeds="40000",
    diep_proceeds="40000",
    diep_additions="42940",
    year=2025,
    cost="56500.00",
)


class _Jurisdictions:
    def __init__(self, jurisdiction: Jurisdiction) -> None:
        self._jurisdiction = jurisdiction

    def get_jurisdiction(self, code: JurisdictionCode) -> Jurisdiction:
        return self._jurisdiction


class _Parameters:
    def __init__(self, *datasets: ParameterDataset[YearAmounts]) -> None:
        self._datasets = {dataset.family: dataset for dataset in datasets}

    def get[T](self, family: str, tax_year: int, kind: ParameterKind[T]) -> ParameterDataset[T]:
        if tax_year != 2025 or kind != YEAR_AMOUNTS or family not in self._datasets:
            raise NotFoundError(f"no {family} dataset for tax year {tax_year}")
        return cast(ParameterDataset[T], self._datasets[family])


def service() -> TaxComputationService:
    """A computation of `ca/cca_vehicle_proceeds` over `ca/business_cca_classes` and the sales
    tax rate, producing `ca/business_cca_classes_adjusted`, wired as the T2125 manifest does."""
    code = JurisdictionCode("CA-ON")
    dataset = prescribed_amounts()
    zepv_dataset = zepv_prescribed_amounts()
    selection = CapabilitySelection(
        name="ca/cca_vehicle_proceeds",
        params={"prescribed_amounts": dataset.family, "zepv_prescribed_amounts": ZEPV_FAMILY},
        consumes={"classes": CLASSES.identifier, "sales_tax_rate": SALES_TAX_RATE.identifier},
        produces={"output": ADJUSTED.identifier},
    )
    manifest = Manifest(
        jurisdiction=code,
        version=1,
        valid_from_tax_year=2025,
        inputs=required_inputs(frozenset({CLASSES.identifier, SALES_TAX_RATE.identifier})),
        forms=(
            Form(
                required=True,
                name=code.namespace.identifier("return"),
                instances=None,
                exports=(ADJUSTED.identifier,),
                capabilities=(selection,),
            ),
        ),
    )
    artifacts = ArtifactRegistry()
    for kind in (CLASSES, SALES_TAX_RATE, ADJUSTED):
        artifacts.register(kind.identifier, kind)
    return TaxComputationService(
        _Jurisdictions(Jurisdiction(code=code, manifests=(manifest,))),
        _Parameters(dataset, zepv_dataset),
        CapabilityRegistry.shared(),
        artifacts,
    )
