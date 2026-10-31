"""Form T2121 in the CA-ON manifest: any number of statements, and what the return reads.

T2121 is the form `ca/t2121`, one instance for each statement (one for each fishing business). Its
selections live in the part `03d_t2121.yaml` under the `form:` key; the caller supplies the
statements as the record list `ca/t2121_statements`, whose fields are the T2121 inputs; and the form
exports its line 9946, "Your net income (loss)", which T1 line 14300 "Net" totals over the
statements. The entries of the form are listed in `manifest_families/t2121.py`. The printed
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
from tax_engine.jurisdictions.ca.catalog import (
    FISH_BOAT_MAINLY_PERSONAL,
    FISHING_INCOME,
    T2121_STATEMENTS,
)
from tests.jurisdictions.ca_on.manifest_families import t2121
from tests.jurisdictions.ca_on.manifest_support import (
    INPUTS_PARTS,
    capabilities_of,
    instance_fields,
    lists,
    required_entries,
)

CA_ON = JurisdictionCode("CA-ON")
PART = Path(tax_engine.jurisdictions.ca_on.__file__).parent / "manifests" / "v1" / "03d_t2121.yaml"
# The part is split in two to stay under 30 KB: the second holds the later steps.
PART_2 = PART.with_name("03d_t2121_2.yaml")
INCOME_PART = PART.with_name("03_income.yaml")
INPUTS_PART = PART.with_name("01_inputs.yaml")
CHECKS_PART = PART.with_name("03n_t2121_checks.yaml")
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
    (found,) = (each for each in manifest().forms if each.name == "ca/t2121")
    return found


def composed() -> FormComposition:
    return build_tax_computation().compose(CA_ON, 2025).form("ca/t2121")


# --- the part and the form -----------------------------------------------------------------------


def test_the_t2121_part_declares_the_form_ca_t2121_with_its_instances_and_exports() -> None:
    declared = yaml.safe_load(PART.read_text())["form"]

    assert declared == {
        "name": "ca/t2121",
        "required": True,
        "fields": required_entries(instance_fields("ca/t2121")),
        "instances": "ca/t2121_statements",
        "exports": list(t2121.FORM_EXPORTS),
    }


def test_the_manifest_has_the_form_t2121_beside_the_other_forms() -> None:
    found = form()

    assert found.name == "ca/t2121"
    assert found.instances == "ca/t2121_statements"
    assert found.exports == t2121.FORM_EXPORTS


def test_the_form_holds_the_53_t2121_selections() -> None:
    # The selections of Charts A to C of one vehicle and the five printed constants are now one
    # step over the statement's vehicles, the form's only selection for them. One more is the
    # check of the partner answer (in `03n_t2121_checks.yaml`); four more are the steps of the
    # fishing boat used mainly for personal use (the net income before the limit, which the
    # immediate expensing check reads, the checked answer, the lesser amount and the choice of the
    # deductible total, in `03d_t2121.yaml`); line 9369 is the same step, reading the deductible
    # total.
    found = form()

    assert len(found.capabilities) == 53
    assert set(found.capabilities) == t2121.FORM_STEPS


def test_the_checks_part_declares_only_the_form_ca_t2121_and_its_one_check() -> None:
    declared = yaml.safe_load(CHECKS_PART.read_text())

    assert set(declared) == {"form", "capabilities"}
    assert declared["form"] == {"name": "ca/t2121"}
    assert declared["capabilities"] == [
        {
            "name": "ca/yes_or_no_count",
            "consumes": {"count": "ca/fish_partner"},
            "produces": {"output": "ca/fish_partner_checked"},
        },
    ]


def test_the_return_selects_only_the_total_of_line_9946_and_none_of_the_form_steps() -> None:
    (default, *_) = manifest().forms
    selected = set(default.capabilities)

    assert t2121.STEPS <= selected
    # What the form holds, the return holds not at all: the printed constants of Charts B and C
    # are datasets of the form's vehicle step, and no part of the return selects them.
    assert not selected & t2121.FORM_STEPS
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
        "sales_tax_rate": "ca/fish_vehicle_sales_tax_rate",
        "fiscal_period_days": "ca/fish_fiscal_period_days",
    }
    assert own.produces == {"output": "ca/fish_motor_vehicle_expenses"}


def test_the_form_has_no_step_of_its_own_for_the_chart_lines_or_the_constants() -> None:
    produced = {step.produces["output"] for step in form().capabilities}

    assert not produced & VEHICLE_CONSTANTS
    assert not any(identifier.startswith("ca/fish_vehicle_") for identifier in produced)


def test_the_t2121_part_is_not_over_30_kb_and_the_other_parts_hold_no_t2121_input() -> None:
    assert PART.stat().st_size <= 30 * 1024
    assert PART_2.stat().st_size <= 30 * 1024
    for other in INPUTS_PARTS:
        text = other.read_text()
        for identifier in t2121.FORM_INPUTS:
            assert not lists(text, identifier), (other.name, identifier)


# --- the instances input -------------------------------------------------------------------------


def test_the_instances_are_the_one_input_of_the_manifest_in_place_of_the_t2121_inputs() -> None:
    inputs = manifest().inputs.keys()

    assert t2121.INPUTS <= inputs
    assert inputs.isdisjoint(t2121.FORM_INPUTS)


def test_the_statements_kind_is_a_record_list_of_every_t2121_input_in_order() -> None:
    assert isinstance(T2121_STATEMENTS, RecordListKind)
    assert T2121_STATEMENTS.identifier == "ca/t2121_statements"
    assert frozenset(field.identifier for field in T2121_STATEMENTS.fields) == t2121.FORM_INPUTS
    assert len(T2121_STATEMENTS.fields) == len(t2121.FORM_INPUTS) == 59


def test_the_area_a_list_and_the_vehicles_of_a_statement_are_nested_record_lists() -> None:
    nested = {
        field.identifier for field in T2121_STATEMENTS.fields if isinstance(field, RecordListKind)
    }

    assert nested == {"ca/business_vehicles", "ca/fish_cca_classes"}


def test_the_catalog_registers_the_statements_kind_beside_the_other_record_lists() -> None:
    build_tax_computation()

    assert ArtifactRegistry.shared().kind("ca/t2121_statements") is T2121_STATEMENTS


# --- the outputs and the node --------------------------------------------------------------------


def test_the_return_declares_no_output_for_the_exports_nothing_reads() -> None:
    (default, *_) = manifest().forms
    exports = set(default.exports)

    assert t2121.OUTPUTS <= exports
    assert (
        not {
            "ca/fish_closing_ucc",
            "ca/fish_home_carry_forward",
            "ca/fish_immediate_expensing_claim",
            "ca/fish_immediate_expensing_limit_unprorated",
        }
        & exports
    )
    assert not {export for export in exports if "." in export}


def test_the_form_set_runs_the_form_on_the_statements_and_derives_its_ten_kinds() -> None:
    found = composed()

    assert found.instances == T2121_STATEMENTS
    assert found.imports == frozenset()
    assert found.derived == (
        t2121.NET_INCOME_PER_STATEMENT,
        t2121.FISH_CLOSING_UCC_PER_STATEMENT,
        t2121.FISH_HOME_CARRY_FORWARD_PER_STATEMENT,
        t2121.FISH_IMMEDIATE_EXPENSING_CLAIM_PER_STATEMENT,
        t2121.FISH_IMMEDIATE_EXPENSING_LIMIT_UNPRORATED_PER_STATEMENT,
        t2121.FISH_LAND_ADDITIONS_PER_STATEMENT,
        t2121.FISH_LAND_DISPOSITIONS_PER_STATEMENT,
        t2121.FISH_LIABILITIES_PER_STATEMENT,
        t2121.FISH_DRAWINGS_PER_STATEMENT,
        t2121.FISH_CAPITAL_CONTRIBUTIONS_PER_STATEMENT,
    )


def test_the_net_income_export_is_a_record_list_of_the_signed_fishing_income() -> None:
    (net,) = (kind for kind in composed().derived if kind.identifier == "ca/t2121.fishing_income")

    assert net == t2121.NET_INCOME_PER_STATEMENT
    assert net.fields == (FISHING_INCOME,)


def test_the_selections_inside_the_form_are_wired_as_they_were_on_the_return() -> None:
    inner = {
        (type(capability), capability.consumes, capability.produces)
        for capability in composed().composition.order
    }

    assert inner == t2121.FORM_WIRING


# The Class 10.1 vehicle additions check, in `03s_t2121_vehicle_additions_check.yaml`:

VEHICLE_CHECKS_PART = PART.with_name("03s_t2121_vehicle_additions_check.yaml")


def test_the_checks_part_declares_only_its_form_and_the_vehicle_additions_check() -> None:
    declared = yaml.safe_load(VEHICLE_CHECKS_PART.read_text())

    assert set(declared) == {"form", "capabilities"}
    assert declared["form"] == {"name": "ca/t2121"}
    assert declared["capabilities"] == [
        {
            "name": "ca/cca_vehicle_additions_checks",
            "params": {"prescribed_amounts": "ca/cca_vehicle_prescribed_amounts"},
            "consumes": {
                "classes": "ca/fish_cca_classes",
                "sales_tax_rate": "ca/fish_vehicle_sales_tax_rate",
            },
            "produces": {"output": "ca/fish_cca_classes_checked"},
        }
    ]


def test_the_proceeds_step_reads_the_checked_list_and_produces_the_adjusted_one() -> None:
    steps = capabilities_of(PART, PART_2)
    (proceeds,) = [step for step in steps if step["name"] == "ca/cca_vehicle_proceeds"]

    assert proceeds["consumes"] == {
        "classes": "ca/fish_cca_classes_checked",
        "sales_tax_rate": "ca/fish_vehicle_sales_tax_rate",
    }
    assert proceeds["produces"] == {"output": "ca/fish_cca_classes_adjusted"}


# --- the fishing boat used mainly for personal use ----------------------------------------------


def test_the_boat_answer_is_the_last_field_of_the_statements_and_is_a_count() -> None:
    # Guide T4002 (page 51): the answer is the filer's fact, asked for each statement, 0 or 1.
    assert T2121_STATEMENTS.fields[-1] is FISH_BOAT_MAINLY_PERSONAL
    assert FISH_BOAT_MAINLY_PERSONAL.identifier == "ca/fish_boat_mainly_personal"


def test_the_part_declares_the_four_boat_steps_right_before_line_9369() -> None:
    steps = capabilities_of(PART, PART_2)
    produced = [next(iter(step["produces"].values())) for step in steps]
    first = produced.index("ca/fish_boat_mainly_personal_checked")

    assert produced[first : first + 5] == [
        "ca/fish_boat_mainly_personal_checked",
        "ca/fish_expenses_limited_to_catch_income",
        "ca/fish_total_expenses_deductible",
        "ca/fish_net_income_before_adjustments",
        "ca/fish_share_of_net_income",
    ]
    assert steps[first : first + 4] == [
        {
            "name": "ca/yes_or_no_count",
            "consumes": {"count": "ca/fish_boat_mainly_personal"},
            "produces": {"output": "ca/fish_boat_mainly_personal_checked"},
        },
        {
            "name": "core/lesser_of",
            "consumes": {
                "amounts": ["ca/fish_total_expenses", "ca/fish_gross_income_before_expenses"]
            },
            "produces": {"output": "ca/fish_expenses_limited_to_catch_income"},
        },
        {
            "name": "core/choose_by_count",
            "consumes": {
                "count": "ca/fish_boat_mainly_personal_checked",
                "when_none": "ca/fish_total_expenses",
                "when_any": "ca/fish_expenses_limited_to_catch_income",
            },
            "produces": {"output": "ca/fish_total_expenses_deductible"},
        },
        {
            "name": "core/subtract",
            "consumes": {
                "amount": "ca/fish_gross_income_before_expenses",
                "less": "ca/fish_total_expenses_deductible",
            },
            "produces": {"output": "ca/fish_net_income_before_adjustments"},
        },
    ]
