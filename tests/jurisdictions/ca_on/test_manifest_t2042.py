"""Form T2042 in the CA-ON manifest: any number of statements, and what the return reads.

T2042 is the form `ca/t2042`, one instance for each statement (one for each farming business). Its
selections live in the part `03c_t2042.yaml` under the `form:` key; the caller supplies the
statements as the record list `ca/t2042_statements`, whose fields are the T2042 inputs; and the form
exports its line 9946, "Your net income (loss)", which T1 line 14100 "Net" totals over the
statements. The entries of the form are listed in `manifest_families/t2042.py`. The printed
constants of Charts B and C are the datasets of the form's one motor vehicle step; the return
selects none of them.
"""

from __future__ import annotations

from itertools import chain
from pathlib import Path

import yaml

import tax_engine.jurisdictions.ca_on

# lists the packages; build_tax_computation registers their catalogs
import tax_engine.registrations
from tax_engine import build_tax_computation
from tax_engine.adapters.outbound.yaml_jurisdictions import YamlJurisdictionSource
from tax_engine.domain.artifact import ArtifactRegistry
from tax_engine.domain.form import FormComposition
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import Form, Manifest
from tax_engine.domain.record_list import RecordListKind
from tax_engine.jurisdictions.ca.catalog import FARMING_INCOME, T2042_STATEMENTS
from tests.jurisdictions.ca_on.manifest_families import t2042
from tests.jurisdictions.ca_on.manifest_support import (
    INPUTS_PARTS,
    capabilities_of,
    instance_fields,
    lists,
    required_entries,
)

CA_ON = JurisdictionCode("CA-ON")
PART = Path(tax_engine.jurisdictions.ca_on.__file__).parent / "manifests" / "v1" / "03c_t2042.yaml"
# The part is split in two to stay under 30 KB: the second holds the later steps.
PART_2 = PART.with_name("03c_t2042_2.yaml")
INCOME_PART = PART.with_name("03_income.yaml")
INPUTS_PART = PART.with_name("01_inputs.yaml")
CHECKS_PART = PART.with_name("03m_t2042_checks.yaml")
VEHICLE_CONSTANTS = frozenset(
    {
        "ca/business_vehicle_days_divisor",
    }
)


def manifest() -> Manifest:
    (only,) = (
        YamlJurisdictionSource(tax_engine.registrations.JURISDICTIONS.roots())
        .get_jurisdiction(CA_ON)
        .manifests
    )
    return only


def form() -> Form:
    (found,) = (each for each in manifest().forms if each.name == "ca/t2042")
    return found


def composed() -> FormComposition:
    return build_tax_computation().compose(CA_ON, 2025).form("ca/t2042")


# --- the part and the form -----------------------------------------------------------------------


def test_the_t2042_part_declares_the_form_ca_t2042_with_its_instances_and_exports() -> None:
    declared = yaml.safe_load(PART.read_text())["form"]

    assert declared == {
        "name": "ca/t2042",
        "required": True,
        "fields": required_entries(instance_fields("ca/t2042")),
        "instances": "ca/t2042_statements",
        "exports": list(t2042.FORM_EXPORTS),
    }


def test_the_manifest_has_the_form_t2042_beside_the_other_forms() -> None:
    found = form()

    assert found.name == "ca/t2042"
    assert found.instances == "ca/t2042_statements"
    assert found.exports == t2042.FORM_EXPORTS


def test_the_form_holds_the_166_t2042_selections_through_the_chart_b_and_c_and_the_presence() -> (
    None
):
    # The 130 selections of before, and 16 new ones at the start of Chart B: each province's row 1
    # (gross income) and row 4 (salaries and wages), now totals over the statement's province list
    # in place of the statement's 16 starting amounts.
    # One more is the check of the partner answer (in `03m_t2042_checks.yaml`).
    # The selections of Charts A to C of one vehicle and the five printed constants are now one
    # step over the statement's vehicles, the form's only selection for them. Form T2043's Chart A
    # adds amount 5 (a sum), amount 6 (a subtraction),
    # amount 7 and 8 (the prorated amount, one exact fraction rounded to the cent) and, for each of
    # the eight provinces, a count of the designated province and the amount 8 times that count. The
    # form selects exactly these.
    # Eighteen more are the presence of the statement in each of the nine places for Form T2043 box
    # 67062: for each province a count (the Chart A place, or a Chart B amount for it, 1 when any
    # applies) and the statement counted (`core/per_unit_amount`), and the same for outside eight.
    found = form()

    assert len(t2042.FORM_STEPS) == 166
    assert set(found.capabilities) == t2042.FORM_STEPS


def test_the_checks_part_declares_only_the_form_ca_t2042_and_its_one_check() -> None:
    declared = yaml.safe_load(CHECKS_PART.read_text())

    assert set(declared) == {"form", "capabilities"}
    assert declared["form"] == {"name": "ca/t2042"}
    assert declared["capabilities"] == [
        {
            "name": "ca/yes_or_no_count",
            "consumes": {"count": "ca/farm_partner"},
            "produces": {"output": "ca/farm_partner_checked"},
        },
    ]


def test_the_return_selects_only_the_total_of_line_9946_and_none_of_the_form_steps() -> None:
    (default, *_) = manifest().forms
    selected = set(default.capabilities)

    assert t2042.STEPS <= selected
    # What the form holds, the return holds not at all: the printed constants of Charts B and C
    # are datasets of the form's vehicle step, and no part of the return selects them.
    assert not selected & t2042.FORM_STEPS
    produced = set(chain.from_iterable(step.produces.values() for step in selected))
    assert not produced & VEHICLE_CONSTANTS


def test_the_form_selects_one_vehicles_step_over_the_printed_constants_datasets() -> None:
    (own,) = [step for step in form().capabilities if step.name == "ca/business_vehicle_expenses"]

    assert own.params == {
        "interest_limits": "ca/business_vehicle_interest_limits",
        "lease_limits": "ca/business_vehicle_lease_limits",
        "days_divisor": "ca/business_vehicle_days_divisor",
        "lease_price_rate": "ca/business_vehicle_lease_price_rate",
        "deposit_minimum": "ca/business_vehicle_deposit_minimum",
        "rounding": "ca/business_vehicle_rounding",
    }
    assert own.consumes == {
        "vehicles": "ca/business_vehicles",
        "sales_tax_rate": "ca/farm_vehicle_sales_tax_rate",
        "fiscal_period_days": "ca/farm_fiscal_period_days",
    }
    assert own.produces == {"output": "ca/farm_motor_vehicle_expenses"}


def test_the_form_has_no_step_of_its_own_for_the_chart_lines_or_the_constants() -> None:
    produced = {step.produces["output"] for step in form().capabilities}

    assert not produced & VEHICLE_CONSTANTS
    assert not any(identifier.startswith("ca/farm_vehicle_") for identifier in produced)


def test_the_t2042_part_is_not_over_30_kb_and_the_other_parts_hold_no_t2042_input() -> None:
    assert PART.stat().st_size <= 30 * 1024
    assert PART_2.stat().st_size <= 30 * 1024
    for other in INPUTS_PARTS:
        text = other.read_text()
        for identifier in t2042.FORM_INPUTS:
            assert not lists(text, identifier), (other.name, identifier)


# --- the instances input -------------------------------------------------------------------------


def test_the_instances_are_the_one_input_of_the_manifest_in_place_of_the_t2042_inputs() -> None:
    inputs = manifest().inputs.keys()

    assert t2042.INPUTS <= inputs
    assert inputs.isdisjoint(t2042.FORM_INPUTS)


def test_the_statements_kind_is_a_record_list_of_every_t2042_input_in_order() -> None:
    assert isinstance(T2042_STATEMENTS, RecordListKind)
    assert T2042_STATEMENTS.identifier == "ca/t2042_statements"
    assert frozenset(field.identifier for field in T2042_STATEMENTS.fields) == t2042.FORM_INPUTS
    # The statement's inputs: the Chart B province list stands for the 16 Chart B amounts.
    assert len(T2042_STATEMENTS.fields) == len(t2042.FORM_INPUTS) == 103


def test_the_area_a_list_the_vehicles_and_the_chart_b_provinces_are_nested_record_lists() -> None:
    nested = {
        field.identifier for field in T2042_STATEMENTS.fields if isinstance(field, RecordListKind)
    }

    assert nested == {
        "ca/business_vehicles",
        "ca/farm_cca_classes",
        "ca/farm_chart_b_provinces",
    }


SIXTEEN_CHART_B_AMOUNTS = frozenset(
    {
        f"ca/farm_chart_b_{line}_{province}"
        for line in ("gross_income", "salaries")
        for province in ("on", "mb", "sk", "ab", "ns", "pe", "nl", "nb")
    }
)


def test_the_sixteen_chart_b_amounts_are_computed_exports_and_no_longer_statement_inputs() -> None:
    # Form T2043 Chart B row 1 and row 4 for each designated province are now totals over the
    # statement's province list, so the statement does not take them; the form still exports them.
    assert len(SIXTEEN_CHART_B_AMOUNTS) == 16
    assert SIXTEEN_CHART_B_AMOUNTS.isdisjoint(t2042.FORM_INPUTS)
    assert not SIXTEEN_CHART_B_AMOUNTS & {field.identifier for field in T2042_STATEMENTS.fields}
    assert SIXTEEN_CHART_B_AMOUNTS <= set(t2042.FORM_EXPORTS)


def test_the_catalog_registers_the_statements_kind_beside_the_other_record_lists() -> None:
    build_tax_computation()

    assert ArtifactRegistry.shared().kind("ca/t2042_statements") is T2042_STATEMENTS


def test_the_presence_is_nine_counts_and_nine_statement_counted_amounts_of_each_statement() -> None:
    # Form T2043 box 67062: one count of the statement in each of the nine places (ON, MB, SK, AB,
    # NS, PE, NL, NB, then outside eight), each read from its Chart A count and Chart B amounts or
    # the outside-eight counts, and one amount of the statement counted for each place.
    found = form()
    counts = [
        each
        for each in found.capabilities
        if each.name == "ca/count_by_conditions"
        and str(each.params.get("conditions", "")).startswith("ca/farm_present_")
    ]
    amounts = [
        each
        for each in found.capabilities
        if each.name == "core/per_unit_amount"
        and each.params == {"amount": "ca/farm_statement_counted"}
    ]
    places = ("on", "mb", "sk", "ab", "ns", "pe", "nl", "nb", "outside_eight")

    assert len(counts) == 9
    assert {each.produces["output"] for each in counts} == {
        *(f"ca/farm_present_in_province_{place}" for place in places[:-1]),
        "ca/farm_present_outside_eight",
    }
    assert len(amounts) == 9
    assert {each.produces["output"] for each in amounts} == {
        f"ca/farm_present_amount_{place}" for place in places
    }


def test_the_nine_presence_amounts_are_exports_of_the_statement_and_not_read_by_the_return() -> (
    None
):
    (default, *_) = manifest().forms
    presence = {
        f"ca/farm_present_amount_{place}"
        for place in ("on", "mb", "sk", "ab", "ns", "pe", "nl", "nb", "outside_eight")
    }

    assert presence <= set(form().exports)
    assert not presence & set(default.exports)


# --- the outputs and the node --------------------------------------------------------------------


def test_the_return_declares_no_output_for_the_exports_nothing_reads() -> None:
    (default, *_) = manifest().forms
    exports = set(default.exports)

    assert t2042.OUTPUTS <= exports
    assert (
        not {
            "ca/farm_closing_ucc",
            "ca/farm_home_carry_forward",
            "ca/farm_immediate_expensing_claim",
            "ca/farm_immediate_expensing_limit_unprorated",
        }
        & exports
    )
    assert not {export for export in exports if "." in export}


def test_the_form_set_runs_the_form_on_the_statements_and_derives_its_fifty_seven_kinds() -> None:
    found = composed()

    assert found.instances == T2042_STATEMENTS
    assert found.imports == frozenset()
    assert found.derived == (
        t2042.NET_INCOME_PER_STATEMENT,
        t2042.FARM_CLOSING_UCC_PER_STATEMENT,
        t2042.FARM_HOME_CARRY_FORWARD_PER_STATEMENT,
        t2042.FARM_IMMEDIATE_EXPENSING_CLAIM_PER_STATEMENT,
        t2042.FARM_IMMEDIATE_EXPENSING_LIMIT_UNPRORATED_PER_STATEMENT,
        t2042.FARM_CHART_A_GROSS_EXPENSES_PER_STATEMENT,
        t2042.FARM_AMOUNT_8_ON_PER_STATEMENT,
        t2042.FARM_AMOUNT_8_MB_PER_STATEMENT,
        t2042.FARM_AMOUNT_8_SK_PER_STATEMENT,
        t2042.FARM_AMOUNT_8_AB_PER_STATEMENT,
        t2042.FARM_AMOUNT_8_NS_PER_STATEMENT,
        t2042.FARM_AMOUNT_8_PE_PER_STATEMENT,
        t2042.FARM_AMOUNT_8_NL_PER_STATEMENT,
        t2042.FARM_AMOUNT_8_NB_PER_STATEMENT,
        t2042.FARM_CHART_B_GROSS_INCOME_ON_PER_STATEMENT,
        t2042.FARM_CHART_B_GROSS_INCOME_MB_PER_STATEMENT,
        t2042.FARM_CHART_B_GROSS_INCOME_SK_PER_STATEMENT,
        t2042.FARM_CHART_B_GROSS_INCOME_AB_PER_STATEMENT,
        t2042.FARM_CHART_B_GROSS_INCOME_NS_PER_STATEMENT,
        t2042.FARM_CHART_B_GROSS_INCOME_PE_PER_STATEMENT,
        t2042.FARM_CHART_B_GROSS_INCOME_NL_PER_STATEMENT,
        t2042.FARM_CHART_B_GROSS_INCOME_NB_PER_STATEMENT,
        t2042.FARM_CHART_B_SALARIES_ON_PER_STATEMENT,
        t2042.FARM_CHART_B_SALARIES_MB_PER_STATEMENT,
        t2042.FARM_CHART_B_SALARIES_SK_PER_STATEMENT,
        t2042.FARM_CHART_B_SALARIES_AB_PER_STATEMENT,
        t2042.FARM_CHART_B_SALARIES_NS_PER_STATEMENT,
        t2042.FARM_CHART_B_SALARIES_PE_PER_STATEMENT,
        t2042.FARM_CHART_B_SALARIES_NL_PER_STATEMENT,
        t2042.FARM_CHART_B_SALARIES_NB_PER_STATEMENT,
        t2042.FARM_CHART_B_ROW_2_WHEN_IN_USE_PER_STATEMENT,
        t2042.FARM_CHART_B_ROW_5_WHEN_IN_USE_PER_STATEMENT,
        t2042.FARM_CHART_C_AMOUNT_ON_PER_STATEMENT,
        t2042.FARM_CHART_C_AMOUNT_MB_PER_STATEMENT,
        t2042.FARM_CHART_C_AMOUNT_SK_PER_STATEMENT,
        t2042.FARM_CHART_C_AMOUNT_AB_PER_STATEMENT,
        t2042.FARM_CHART_C_AMOUNT_NS_PER_STATEMENT,
        t2042.FARM_CHART_C_AMOUNT_PE_PER_STATEMENT,
        t2042.FARM_CHART_C_AMOUNT_NL_PER_STATEMENT,
        t2042.FARM_CHART_C_AMOUNT_NB_PER_STATEMENT,
        t2042.FARM_LAND_ADDITIONS_PER_STATEMENT,
        t2042.FARM_LAND_DISPOSITIONS_PER_STATEMENT,
        t2042.FARM_QUOTA_ADDITIONS_PER_STATEMENT,
        t2042.FARM_QUOTA_DISPOSITIONS_PER_STATEMENT,
        t2042.FARM_LIABILITIES_PER_STATEMENT,
        t2042.FARM_DRAWINGS_PER_STATEMENT,
        t2042.FARM_CAPITAL_CONTRIBUTIONS_PER_STATEMENT,
        t2042.FARM_PRESENT_AMOUNT_ON_PER_STATEMENT,
        t2042.FARM_PRESENT_AMOUNT_MB_PER_STATEMENT,
        t2042.FARM_PRESENT_AMOUNT_SK_PER_STATEMENT,
        t2042.FARM_PRESENT_AMOUNT_AB_PER_STATEMENT,
        t2042.FARM_PRESENT_AMOUNT_NS_PER_STATEMENT,
        t2042.FARM_PRESENT_AMOUNT_PE_PER_STATEMENT,
        t2042.FARM_PRESENT_AMOUNT_NL_PER_STATEMENT,
        t2042.FARM_PRESENT_AMOUNT_NB_PER_STATEMENT,
        t2042.FARM_PRESENT_AMOUNT_OUTSIDE_EIGHT_PER_STATEMENT,
        t2042.FARM_FUEL_CHARGE_CREDIT_PER_STATEMENT,
    )


def test_the_chart_a_exports_are_read_by_form_t2043_and_not_by_the_return() -> None:
    (default, *_) = manifest().forms
    chart_a = {
        "ca/farm_chart_a_gross_expenses",
        "ca/farm_amount_8_on",
        "ca/farm_amount_8_mb",
        "ca/farm_amount_8_sk",
        "ca/farm_amount_8_ab",
        "ca/farm_amount_8_ns",
        "ca/farm_amount_8_pe",
        "ca/farm_amount_8_nl",
        "ca/farm_amount_8_nb",
    }

    assert chart_a <= set(form().exports)
    assert not chart_a & set(default.exports)
    assert not chart_a & set(t2042.OUTPUTS)


def test_the_net_income_export_is_a_record_list_of_the_signed_farming_income() -> None:
    (net,) = (kind for kind in composed().derived if kind.identifier == "ca/t2042.farming_income")

    assert net == t2042.NET_INCOME_PER_STATEMENT
    assert net.fields == (FARMING_INCOME,)


def test_the_selections_inside_the_form_are_wired_as_they_were_on_the_return() -> None:
    inner = {
        (type(capability), capability.consumes, capability.produces)
        for capability in composed().composition.order
    }

    assert inner == t2042.FORM_WIRING


# The Class 10.1 vehicle additions check, in `03r_t2042_vehicle_additions_check.yaml`:

VEHICLE_CHECKS_PART = PART.with_name("03r_t2042_vehicle_additions_check.yaml")


def test_the_checks_part_declares_only_its_form_and_the_vehicle_additions_check() -> None:
    declared = yaml.safe_load(VEHICLE_CHECKS_PART.read_text())

    assert set(declared) == {"form", "capabilities"}
    assert declared["form"] == {"name": "ca/t2042"}
    assert declared["capabilities"] == [
        {
            "name": "ca/cca_vehicle_additions_checks",
            "params": {"prescribed_amounts": "ca/cca_vehicle_prescribed_amounts"},
            "consumes": {
                "classes": "ca/farm_cca_classes",
                "sales_tax_rate": "ca/farm_vehicle_sales_tax_rate",
            },
            "produces": {"output": "ca/farm_cca_classes_checked"},
        }
    ]


def test_the_proceeds_step_reads_the_checked_list_and_produces_the_adjusted_one() -> None:
    steps = capabilities_of(PART, PART_2)
    (proceeds,) = [step for step in steps if step["name"] == "ca/cca_vehicle_proceeds"]

    assert proceeds["consumes"] == {
        "classes": "ca/farm_cca_classes_checked",
        "sales_tax_rate": "ca/farm_vehicle_sales_tax_rate",
    }
    assert proceeds["produces"] == {"output": "ca/farm_cca_classes_adjusted"}
