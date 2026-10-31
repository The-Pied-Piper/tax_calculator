"""Shared test data for the BusinessVehicleExpenses capability, Form T2125 Charts A to C.

The five datasets are made-up `example.org` datasets with the printed figures of the chart lines:
the `year_amounts` tables of Chart B line 18 "($350*** ÷ 30)" with its footnote "For passenger
vehicles bought after 2023. For passenger vehicles bought after 2000 and before 2024, the amount is
$300", and of Chart C lines 23, 25 and 27 ("$44,706", "$1,100" and "$38,000") with endnotes 11 to
13 for leases entered into in 2024, 2023, 2022 and before 2022; the 30 of lines 18 and 25, the 85%
of line 24 and a half-up rounding to the cent. The sales tax rate is the artifact of the caller's
province, "Use a GST rate of 5% or HST rate applicable to your province.", given in percent. The
record list of vehicles and the produced kind are the catalog's own `ca/business_vehicles` and
`ca/business_motor_vehicle_expenses`; each record of the vehicles holds the amounts of one
vehicle's Charts A to C that the caller enters, and the years that choose the figure set.
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
from tax_engine.domain.parameters.credit import CREDIT, Credit
from tax_engine.domain.parameters.datasets import ParameterDataset
from tax_engine.domain.parameters.kind import ParameterKind
from tax_engine.domain.parameters.rate import RATE, Rate
from tax_engine.domain.parameters.rounding import RoundingMode, RoundTo
from tax_engine.domain.parameters.rounding_only import ROUNDING_ONLY, RoundingOnly
from tax_engine.domain.parameters.year_amounts import YEAR_AMOUNTS, YearAmounts, YearAmountsRow
from tax_engine.domain.record_list import RecordList, RecordListKind
from tax_engine.jurisdictions.ca.capabilities.business_vehicle_expenses import (
    BusinessVehicleExpenses,
)
from tax_engine.jurisdictions.ca.catalog import (
    BUSINESS_FISCAL_PERIOD_DAYS,
    BUSINESS_MOTOR_VEHICLE_EXPENSES,
    BUSINESS_VEHICLE_BUSINESS_KILOMETRES,
    BUSINESS_VEHICLE_ELECTRICITY_ZEV,
    BUSINESS_VEHICLE_FUEL_AND_OIL,
    BUSINESS_VEHICLE_INSURANCE,
    BUSINESS_VEHICLE_INTEREST_DAYS,
    BUSINESS_VEHICLE_INTEREST_PAYABLE,
    BUSINESS_VEHICLE_LEASE_CHARGES,
    BUSINESS_VEHICLE_LEASE_DAYS,
    BUSINESS_VEHICLE_LEASE_DEPOSITS_MADE,
    BUSINESS_VEHICLE_LEASE_DEPOSITS_REFUNDABLE,
    BUSINESS_VEHICLE_LEASE_DEPOSITS_TOTAL,
    BUSINESS_VEHICLE_LEASE_PAYMENTS_BEFORE,
    BUSINESS_VEHICLE_LEASE_REPAYMENT_OWING,
    BUSINESS_VEHICLE_LEASE_YEAR,
    BUSINESS_VEHICLE_LICENCE_AND_REGISTRATION,
    BUSINESS_VEHICLE_LIST_PRICE,
    BUSINESS_VEHICLE_MAINTENANCE_AND_REPAIRS,
    BUSINESS_VEHICLE_OTHER_EXPENSES_10,
    BUSINESS_VEHICLE_OTHER_EXPENSES_11,
    BUSINESS_VEHICLE_PARKING_FEES,
    BUSINESS_VEHICLE_PASSENGER_VEHICLE,
    BUSINESS_VEHICLE_PURCHASE_YEAR,
    BUSINESS_VEHICLE_SALES_TAX_RATE,
    BUSINESS_VEHICLE_SUPPLEMENTARY_INSURANCE,
    BUSINESS_VEHICLE_TOTAL_KILOMETRES,
    BUSINESS_VEHICLES,
)
from tests.manifest_support import required_inputs

D = Decimal
CENT = RoundTo(D("0.01"), RoundingMode.HALF_UP)
SOURCES = ("https://example.org/t2125",)

VEHICLES = BUSINESS_VEHICLES
SALES_TAX_RATE = BUSINESS_VEHICLE_SALES_TAX_RATE
FISCAL_PERIOD_DAYS = BUSINESS_FISCAL_PERIOD_DAYS
MOTOR_VEHICLE_EXPENSES = BUSINESS_MOTOR_VEHICLE_EXPENSES

# The slot names and the dataset families they are wired to, in the capability's slot order.
FAMILIES = {
    "interest_limits": "ca/business_vehicle_interest_limits",
    "lease_limits": "ca/business_vehicle_lease_limits",
    "days_divisor": "ca/business_vehicle_days_divisor",
    "lease_price_rate": "ca/business_vehicle_lease_price_rate",
    "deposit_minimum": "ca/business_vehicle_deposit_minimum",
    "rounding": "ca/business_vehicle_rounding",
}


def credit(family: str, amount: str) -> ParameterDataset[Credit]:
    return ParameterDataset(family, 2025, CREDIT, Credit(amount=D(amount)), CENT, SOURCES)


def year_amounts(
    family: str, *rows: tuple[int | None, dict[str, str]]
) -> ParameterDataset[YearAmounts]:
    """A `year_amounts` dataset of rows, newest first: (from_year or None, amounts by name)."""
    table = YearAmounts(
        tuple(
            YearAmountsRow(from_year, {name: D(value) for name, value in amounts.items()})
            for from_year, amounts in rows
        )
    )
    return ParameterDataset(family, 2025, YEAR_AMOUNTS, table, CENT, SOURCES)


def interest_limits(*rows: tuple[int | None, str]) -> ParameterDataset[YearAmounts]:
    """The Chart B limit by year of purchase: (from_year or None, the `interest_limit`)."""
    return year_amounts(
        FAMILIES["interest_limits"], *((year, {"interest_limit": value}) for year, value in rows)
    )


def lease_limits(
    *rows: tuple[int | None, str, str, str],
) -> ParameterDataset[YearAmounts]:
    """The Chart C limits by year of lease: (from_year or None, `list_price_limit`,
    `lease_charge_limit`, `lease_cost_limit`)."""
    return year_amounts(
        FAMILIES["lease_limits"],
        *(
            (
                year,
                {
                    "list_price_limit": list_price,
                    "lease_charge_limit": charge,
                    "lease_cost_limit": cost,
                },
            )
            for year, list_price, charge, cost in rows
        ),
    )


def datasets() -> dict[str, ParameterDataset[Any]]:
    """The six datasets, by slot name: the two tables by year as the form prints them (the
    $350/$300 of Chart B and the five sets of Chart C), the 30, the 85%, the guide's $1,000 and the
    rounding."""
    return {
        # Chart B footnote: $350 for a vehicle bought after 2023, $300 after 2000 and before 2024,
        # nothing printed for 2000 or earlier.
        "interest_limits": interest_limits((2024, "350"), (2001, "300")),
        # Chart C line 23, 25 and 27 and endnotes 11 to 13: the 2025 set, then the leases entered
        # into in 2024, 2023, 2022 and before 2022.
        "lease_limits": lease_limits(
            (2025, "44706", "1100", "38000"),
            (2024, "43529", "1050", "37000"),
            (2023, "42353", "950", "36000"),
            (2022, "40000", "900", "34000"),
            (None, "35294", "800", "30000"),
        ),
        "days_divisor": credit(FAMILIES["days_divisor"], "30"),
        "lease_price_rate": ParameterDataset(
            FAMILIES["lease_price_rate"], 2025, RATE, Rate(D("0.85")), CENT, SOURCES
        ),
        "deposit_minimum": credit(FAMILIES["deposit_minimum"], "1000"),
        "rounding": ParameterDataset(
            FAMILIES["rounding"], 2025, ROUNDING_ONLY, RoundingOnly(), CENT, SOURCES
        ),
    }


def capability(**replaced: ParameterDataset[Any]) -> BusinessVehicleExpenses:
    """The capability over the datasets above (any slot may be replaced by name)."""
    return BusinessVehicleExpenses(
        **{**datasets(), **replaced},
        vehicles=VEHICLES,
        sales_tax_rate=SALES_TAX_RATE,
        fiscal_period_days=FISCAL_PERIOD_DAYS,
        output=MOTOR_VEHICLE_EXPENSES,
    )


def vehicle(
    business_kilometres: str = "0",
    total_kilometres: str = "0",
    fuel_and_oil: str = "0",
    insurance: str = "0",
    licence_and_registration: str = "0",
    maintenance_and_repairs: str = "0",
    electricity_zev: str = "0",
    other_expenses_10: str = "0",
    other_expenses_11: str = "0",
    parking_fees: str = "0",
    supplementary_insurance: str = "0",
    interest_payable: str = "0",
    interest_days: str = "0",
    lease_charges: str = "0",
    lease_payments_before: str = "0",
    lease_days: str = "0",
    list_price: str = "0",
    passenger_vehicle: str = "1",
    purchase_year: str = "2025",
    lease_year: str = "2025",
    lease_repayment_owing: str = "0",
    lease_deposits_made: str = "0",
    lease_deposits_refundable: str = "0",
    lease_deposits_total: str = "0",
) -> dict[ArtifactKind[Any], Decimal | int]:
    """One vehicle: Chart A amounts 1, 2, 3, 5, 6, 7, 9, 10, 11, 14 and 15, Chart B amount 17 and
    its days, Chart C amounts 20, 21, 22 and 23, whether it is a passenger vehicle (1 unless given),
    the year the vehicle was bought and the year the lease was entered into (2025 unless given, the
    figure set printed in the chart body), whether its lease has a repayment owing, and whether
    deposits were made, whether they are refundable and their total (0 unless given)."""
    return {
        BUSINESS_VEHICLE_BUSINESS_KILOMETRES: D(business_kilometres),
        BUSINESS_VEHICLE_TOTAL_KILOMETRES: D(total_kilometres),
        BUSINESS_VEHICLE_FUEL_AND_OIL: D(fuel_and_oil),
        BUSINESS_VEHICLE_INSURANCE: D(insurance),
        BUSINESS_VEHICLE_LICENCE_AND_REGISTRATION: D(licence_and_registration),
        BUSINESS_VEHICLE_MAINTENANCE_AND_REPAIRS: D(maintenance_and_repairs),
        BUSINESS_VEHICLE_ELECTRICITY_ZEV: D(electricity_zev),
        BUSINESS_VEHICLE_OTHER_EXPENSES_10: D(other_expenses_10),
        BUSINESS_VEHICLE_OTHER_EXPENSES_11: D(other_expenses_11),
        BUSINESS_VEHICLE_PARKING_FEES: D(parking_fees),
        BUSINESS_VEHICLE_SUPPLEMENTARY_INSURANCE: D(supplementary_insurance),
        BUSINESS_VEHICLE_INTEREST_PAYABLE: D(interest_payable),
        BUSINESS_VEHICLE_INTEREST_DAYS: D(interest_days),
        BUSINESS_VEHICLE_LEASE_CHARGES: D(lease_charges),
        BUSINESS_VEHICLE_LEASE_PAYMENTS_BEFORE: D(lease_payments_before),
        BUSINESS_VEHICLE_LEASE_DAYS: D(lease_days),
        BUSINESS_VEHICLE_LIST_PRICE: D(list_price),
        BUSINESS_VEHICLE_PASSENGER_VEHICLE: int(passenger_vehicle),
        BUSINESS_VEHICLE_PURCHASE_YEAR: int(purchase_year),
        BUSINESS_VEHICLE_LEASE_YEAR: int(lease_year),
        BUSINESS_VEHICLE_LEASE_REPAYMENT_OWING: int(lease_repayment_owing),
        BUSINESS_VEHICLE_LEASE_DEPOSITS_MADE: int(lease_deposits_made),
        BUSINESS_VEHICLE_LEASE_DEPOSITS_REFUNDABLE: int(lease_deposits_refundable),
        BUSINESS_VEHICLE_LEASE_DEPOSITS_TOTAL: D(lease_deposits_total),
    }


def vehicles(*records: dict[ArtifactKind[Any], Decimal | int]) -> Artifact[Any]:
    """A `ca/business_vehicles` artifact of one record per vehicle, in order."""
    assert isinstance(VEHICLES, RecordListKind)
    return Artifact(VEHICLES, RecordList(VEHICLES.fields, records))


def sales_tax_rate(percent: str = "13") -> Artifact[Any]:
    """The GST or HST rate of the caller's province, in percent."""
    return Artifact(SALES_TAX_RATE, D(percent))


def fiscal_period_days(days: int = 365) -> Artifact[Any]:
    """The days of the statement's fiscal period: 365 unless given (a full year, as the
    `ca/business_fiscal_period_days` of a statement with no days entered)."""
    return Artifact(FISCAL_PERIOD_DAYS, days)


# Return BB's leased passenger vehicle used half for business (see returns/2025_return_bb.yaml):
# Chart B interest 400 on 183 days, Chart C lease charges 2550 over 183 days at a list price of
# 60000, and a 13% HST rate: line 19 is 400, line 28 is 2147.00, line 12 is 5000 and lines 13 and
# 16 are 2500.
LEASED = vehicle(
    business_kilometres="5000",
    total_kilometres="10000",
    fuel_and_oil="1000",
    insurance="600",
    maintenance_and_repairs="200",
    other_expenses_10="653",
    interest_payable="400",
    interest_days="183",
    lease_charges="2550",
    lease_days="183",
    list_price="60000",
)


class _Jurisdictions:
    def __init__(self, jurisdiction: Jurisdiction) -> None:
        self._jurisdiction = jurisdiction

    def get_jurisdiction(self, code: JurisdictionCode) -> Jurisdiction:
        return self._jurisdiction


class _Parameters:
    def __init__(self, found: dict[str, ParameterDataset[Any]]) -> None:
        self._found = found

    def get[T](self, family: str, tax_year: int, kind: ParameterKind[T]) -> ParameterDataset[T]:
        dataset = self._found.get(family)
        if dataset is None or (tax_year, kind) != (dataset.tax_year, dataset.kind):
            raise NotFoundError(f"no {family} dataset for tax year {tax_year}")
        return cast(ParameterDataset[T], dataset)


def service() -> TaxComputationService:
    """A computation of `ca/business_vehicle_expenses` over `ca/business_vehicles` and the sales
    tax rate, producing `ca/business_motor_vehicle_expenses`, wired as the T2125 manifest does."""
    code = JurisdictionCode("CA-ON")
    found = datasets()
    selection = CapabilitySelection(
        name="ca/business_vehicle_expenses",
        params={slot: dataset.family for slot, dataset in found.items()},
        consumes={
            "vehicles": VEHICLES.identifier,
            "sales_tax_rate": SALES_TAX_RATE.identifier,
            "fiscal_period_days": FISCAL_PERIOD_DAYS.identifier,
        },
        produces={"output": MOTOR_VEHICLE_EXPENSES.identifier},
    )
    manifest = Manifest(
        jurisdiction=code,
        version=1,
        valid_from_tax_year=2025,
        inputs=required_inputs(
            frozenset(
                {VEHICLES.identifier, SALES_TAX_RATE.identifier, FISCAL_PERIOD_DAYS.identifier}
            )
        ),
        forms=(
            Form(
                required=True,
                name=code.namespace.identifier("return"),
                instances=None,
                exports=(MOTOR_VEHICLE_EXPENSES.identifier,),
                capabilities=(selection,),
            ),
        ),
    )
    artifacts = ArtifactRegistry()
    for kind in (VEHICLES, SALES_TAX_RATE, FISCAL_PERIOD_DAYS, MOTOR_VEHICLE_EXPENSES):
        artifacts.register(kind.identifier, kind)
    return TaxComputationService(
        _Jurisdictions(Jurisdiction(code=code, manifests=(manifest,))),
        _Parameters({dataset.family: dataset for dataset in found.values()}),
        CapabilityRegistry.shared(),
        artifacts,
    )
