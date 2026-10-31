"""Form T2125 in the CA-ON manifest: any number of statements, and what the return reads.

T2125 is the form `ca/t2125`, one instance for each statement (one for each business). Its
selections live in the part `03b_t2125.yaml` under the `form:` key; the caller supplies the
statements as the record list `ca/t2125_statements`, whose fields are the T2125 inputs; and the form
exports its line 9946, "Your net income (loss)", which T1 line 13500 "Net" totals over the
statements. The entries of the form are listed in `manifest_families/t2125.py`. The five printed
constants of Charts B and C are the datasets of the form's one `ca/business_vehicle_expenses` step;
the return selects none of them.
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
from tax_engine.domain.manifest import CapabilitySelection, Form, Manifest
from tax_engine.domain.record_list import RecordListKind
from tax_engine.jurisdictions.ca.catalog import NET_ON_BUSINESS_LINE, T2125_STATEMENTS
from tests.jurisdictions.ca_on.manifest_families import t2125
from tests.jurisdictions.ca_on.manifest_support import (
    INPUTS_PARTS,
    capabilities_of,
    instance_fields,
    lists,
    required_entries,
)

CA_ON = JurisdictionCode("CA-ON")
PART = Path(tax_engine.jurisdictions.ca_on.__file__).parent / "manifests" / "v1" / "03b_t2125.yaml"
# The part is split in two to stay under 30 KB: the second holds the later steps.
PART_2 = PART.with_name("03b_t2125_2.yaml")
INCOME_PART = PART.with_name("03_income.yaml")
INPUTS_PART = PART.with_name("01_inputs.yaml")
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
    (found,) = (each for each in manifest().forms if each.name == "ca/t2125")
    return found


def composed() -> FormComposition:
    return build_tax_computation().compose(CA_ON, 2025).form("ca/t2125")


# --- the part and the form -----------------------------------------------------------------------


def test_the_t2125_part_declares_the_form_ca_t2125_with_its_instances_and_exports() -> None:
    declared = yaml.safe_load(PART.read_text())["form"]

    assert declared == {
        "name": "ca/t2125",
        "required": True,
        "fields": required_entries(instance_fields("ca/t2125")),
        "instances": "ca/t2125_statements",
        "exports": list(t2125.FORM_EXPORTS),
    }


def test_the_manifest_has_the_form_t2125_beside_the_other_forms() -> None:
    found = form()

    assert found.name == "ca/t2125"
    assert found.instances == "ca/t2125_statements"
    assert found.exports == t2125.FORM_EXPORTS


def test_the_form_holds_the_64_t2125_selections() -> None:
    # The 55 selections of one vehicle's Charts A to C (22 of them) are now one step over the
    # statement's vehicles; the statement's line code adds one `ca/count_refused_by_conditions`
    # check, three `ca/count_by_conditions` flags and six `core/times_count` routed amounts of the
    # net and the gross. One more is the partner check of the business (in
    # `03y_t2125_partner_checks.yaml`): the partner answer checked.
    found = form()

    assert len(found.capabilities) == 64
    assert set(found.capabilities) == t2125.FORM_STEPS


def test_the_return_selects_only_the_total_of_line_9946_and_none_of_the_form_steps() -> None:
    (default, *_) = manifest().forms
    selected = set(default.capabilities)

    assert t2125.STEPS <= selected
    # What the form holds, the return holds not at all: the five printed constants of Charts B and C
    # are datasets of the form's vehicles step, and no part of the return selects them.
    assert not selected & t2125.FORM_STEPS
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
        "sales_tax_rate": "ca/business_vehicle_sales_tax_rate",
        "fiscal_period_days": "ca/business_fiscal_period_days",
    }
    assert own.produces == {"output": "ca/business_motor_vehicle_expenses"}


def test_the_form_has_no_step_of_its_own_for_the_chart_lines_or_the_constants() -> None:
    produced = {step.produces["output"] for step in form().capabilities}

    assert not produced & VEHICLE_CONSTANTS
    assert not any(identifier.startswith("ca/business_vehicle_") for identifier in produced)
    assert not PART.with_name("03f_t2125_vehicle_limits.yaml").exists()


def test_the_t2125_part_is_not_over_30_kb_and_the_other_parts_hold_no_t2125_input() -> None:
    assert PART.stat().st_size <= 30 * 1024
    assert PART_2.stat().st_size <= 30 * 1024
    for other in INPUTS_PARTS:
        text = other.read_text()
        for identifier in t2125.FORM_INPUTS:
            assert not lists(text, identifier), (other.name, identifier)


# --- the instances input -------------------------------------------------------------------------


def test_the_instances_are_the_one_input_of_the_manifest_in_place_of_the_t2125_inputs() -> None:
    inputs = manifest().inputs.keys()

    assert t2125.INPUTS <= inputs
    assert inputs.isdisjoint(t2125.FORM_INPUTS)


def test_the_statements_kind_is_a_record_list_of_every_t2125_input_in_order() -> None:
    assert isinstance(T2125_STATEMENTS, RecordListKind)
    assert T2125_STATEMENTS.identifier == "ca/t2125_statements"
    assert frozenset(field.identifier for field in T2125_STATEMENTS.fields) == t2125.FORM_INPUTS
    assert len(T2125_STATEMENTS.fields) == len(t2125.FORM_INPUTS) == 68


def test_the_area_a_list_of_a_statement_is_a_nested_record_list() -> None:
    nested = {
        field.identifier for field in T2125_STATEMENTS.fields if isinstance(field, RecordListKind)
    }

    assert nested == {"ca/business_cca_classes", "ca/business_vehicles"}


def test_the_catalog_registers_the_statements_kind_beside_the_other_record_lists() -> None:
    build_tax_computation()

    assert ArtifactRegistry.shared().kind("ca/t2125_statements") is T2125_STATEMENTS


# --- the outputs and the node --------------------------------------------------------------------


def test_the_return_declares_no_output_for_the_exports_nothing_reads() -> None:
    (default, *_) = manifest().forms
    exports = set(default.exports)

    assert t2125.OUTPUTS <= exports
    assert (
        not {
            "ca/business_closing_ucc",
            "ca/business_home_carry_forward",
            "ca/business_immediate_expensing_claim",
            "ca/business_immediate_expensing_limit_unprorated",
        }
        & exports
    )
    assert not {export for export in exports if "." in export}


def test_the_form_set_runs_the_form_on_the_statements_and_derives_its_sixteen_kinds() -> None:
    found = composed()

    assert found.instances == T2125_STATEMENTS
    assert found.imports == frozenset()
    assert found.derived == (
        t2125.NET_INCOME_PER_STATEMENT,
        t2125.NET_ON_PROFESSIONAL_LINE_PER_STATEMENT,
        t2125.NET_ON_COMMISSION_LINE_PER_STATEMENT,
        t2125.GROSS_ON_BUSINESS_LINE_PER_STATEMENT,
        t2125.GROSS_ON_PROFESSIONAL_LINE_PER_STATEMENT,
        t2125.GROSS_ON_COMMISSION_LINE_PER_STATEMENT,
        t2125.BUSINESS_CLOSING_UCC_PER_STATEMENT,
        t2125.BUSINESS_HOME_CARRY_FORWARD_PER_STATEMENT,
        t2125.BUSINESS_IMMEDIATE_EXPENSING_CLAIM_PER_STATEMENT,
        t2125.BUSINESS_IMMEDIATE_EXPENSING_LIMIT_UNPRORATED_PER_STATEMENT,
        t2125.BUSINESS_LAND_ADDITIONS_PER_STATEMENT,
        t2125.BUSINESS_LAND_DISPOSITIONS_PER_STATEMENT,
        t2125.BUSINESS_LIABILITIES_PER_STATEMENT,
        t2125.BUSINESS_DRAWINGS_PER_STATEMENT,
        t2125.BUSINESS_CAPITAL_CONTRIBUTIONS_PER_STATEMENT,
        t2125.BUSINESS_JOURNALISM_LABOUR_TAX_CREDIT_PER_STATEMENT,
    )


def test_the_routed_net_export_is_a_record_list_of_the_signed_net_on_the_business_line() -> None:
    (net,) = (
        kind for kind in composed().derived if kind.identifier == "ca/t2125.net_on_business_line"
    )

    assert net == t2125.NET_INCOME_PER_STATEMENT
    assert net.fields == (NET_ON_BUSINESS_LINE,)
    assert NET_ON_BUSINESS_LINE.non_negative is False


def test_the_selections_inside_the_form_are_wired_as_they_were_on_the_return() -> None:
    inner = {
        (type(capability), capability.consumes, capability.produces)
        for capability in composed().composition.order
    }

    assert inner == t2125.FORM_WIRING


# --- the line code: each statement's net and gross on the T1 line of its code ------------------


def test_each_flag_is_a_count_of_the_statements_code_by_its_own_conditions() -> None:
    flags = [step for step in form().capabilities if step.name == "ca/count_by_conditions"]

    assert {step.produces["output"]: step.params["conditions"] for step in flags} == {
        "ca/business_line_is_business": "ca/t2125_line_is_business",
        "ca/business_line_is_professional": "ca/t2125_line_is_professional",
        "ca/business_line_is_commission": "ca/t2125_line_is_commission",
    }
    assert all(
        step.consumes == {"counts": ("ca/business_income_line_checked",), "amounts": ()}
        for step in flags
    )


def test_each_routed_amount_is_the_net_or_the_gross_times_its_lines_flag() -> None:
    routed = [
        step for step in form().capabilities if step.name == "core/times_count" and _is_routed(step)
    ]

    assert {
        step.produces["output"]: (step.consumes["amount"], step.consumes["count"])
        for step in routed
    } == {
        "ca/net_on_business_line": ("ca/business_income", "ca/business_line_is_business"),
        "ca/net_on_professional_line": ("ca/business_income", "ca/business_line_is_professional"),
        "ca/net_on_commission_line": ("ca/business_income", "ca/business_line_is_commission"),
        "ca/gross_on_business_line": ("ca/business_gross_income", "ca/business_line_is_business"),
        "ca/gross_on_professional_line": (
            "ca/business_gross_income",
            "ca/business_line_is_professional",
        ),
        "ca/gross_on_commission_line": (
            "ca/business_gross_income",
            "ca/business_line_is_commission",
        ),
    }


def _is_routed(step: CapabilitySelection) -> bool:
    output = step.produces["output"]
    return output.startswith(("ca/net_on_", "ca/gross_on_", "ca/business_line_is_"))


def test_the_routing_rounds_nothing_so_the_form_has_no_rounding_step() -> None:
    routed = [step for step in form().capabilities if _is_routed(step)]

    assert routed
    assert not [step for step in routed if step.name == "ca/apply_percentage"]
    assert not [step for step in routed if "rounding" in step.params]


def test_the_line_9946_stays_the_signed_net_inside_the_form_named_business_income() -> None:
    (net,) = [
        step for step in form().capabilities if step.produces.get("output") == "ca/business_income"
    ]

    assert net.name == "core/subtract"
    assert net.consumes == {
        "amount": "ca/business_net_income_after_adjustments",
        "less": "ca/business_home_expenses",
    }


def test_the_return_declares_the_three_grosses_as_outputs_and_exports_the_routed_lines() -> None:
    (default, *_) = manifest().forms
    gross = {
        "ca/gross_business_income",
        "ca/gross_professional_income",
        "ca/gross_commission_income",
    }
    routed = {
        "ca/net_on_business_line",
        "ca/net_on_professional_line",
        "ca/net_on_commission_line",
        "ca/gross_on_business_line",
        "ca/gross_on_professional_line",
        "ca/gross_on_commission_line",
    }

    assert t2125.OUTPUTS == frozenset(gross)
    assert routed <= set(t2125.FORM_EXPORTS)
    assert gross <= set(default.exports)
    # The 9946 line is read inside the form only; the nets are not declared outputs of the form.
    assert "ca/business_income" not in t2125.FORM_EXPORTS
    assert not {"ca/business_income", "ca/professional_income", "ca/commission_income"} & (
        t2125.OUTPUTS
    )


def test_the_manifest_part_for_t2125_stays_under_30_kilobytes() -> None:
    assert PART.stat().st_size <= 30 * 1024
    assert PART_2.stat().st_size <= 30 * 1024


# The Class 10.1 vehicle additions check, in `03q_t2125_vehicle_additions_check.yaml`:

CHECKS_PART = PART.with_name("03q_t2125_vehicle_additions_check.yaml")


def test_the_checks_part_declares_only_its_form_and_the_vehicle_additions_check() -> None:
    declared = yaml.safe_load(CHECKS_PART.read_text())

    assert set(declared) == {"form", "capabilities"}
    assert declared["form"] == {"name": "ca/t2125"}
    assert declared["capabilities"] == [
        {
            "name": "ca/cca_vehicle_additions_checks",
            "params": {"prescribed_amounts": "ca/cca_vehicle_prescribed_amounts"},
            "consumes": {
                "classes": "ca/business_cca_classes",
                "sales_tax_rate": "ca/business_vehicle_sales_tax_rate",
            },
            "produces": {"output": "ca/business_cca_classes_checked"},
        }
    ]


def test_the_proceeds_step_reads_the_checked_list_and_produces_the_adjusted_one() -> None:
    steps = capabilities_of(PART, PART_2)
    (proceeds,) = [step for step in steps if step["name"] == "ca/cca_vehicle_proceeds"]

    assert proceeds["consumes"] == {
        "classes": "ca/business_cca_classes_checked",
        "sales_tax_rate": "ca/business_vehicle_sales_tax_rate",
    }
    assert proceeds["produces"] == {"output": "ca/business_cca_classes_adjusted"}


# The partner check, in `03y_t2125_partner_checks.yaml`: the partner answer checked to be 0 or 1.
PARTNER_CHECKS_PART = PART.with_name("03y_t2125_partner_checks.yaml")


def test_the_partner_checks_part_declares_only_the_form_ca_t2125_and_its_one_check() -> None:
    declared = yaml.safe_load(PARTNER_CHECKS_PART.read_text())

    assert set(declared) == {"form", "capabilities"}
    assert declared["form"] == {"name": "ca/t2125"}
    assert declared["capabilities"] == [
        {
            "name": "ca/yes_or_no_count",
            "consumes": {"count": "ca/business_partner"},
            "produces": {"output": "ca/business_partner_checked"},
        },
    ]


def test_the_business_choose_by_count_reads_the_checked_partner_answer() -> None:
    # Part 5 "Your share of line 9369 or the amount from your T5013 slip": the choice reads the
    # partner answer checked to be 0 or 1 (the step above), as the farm and fish choices do.
    declared = capabilities_of(PART, PART_2)
    (choice,) = [
        step
        for step in declared
        if step.get("name") == "core/choose_by_count"
        and step["consumes"].get("when_any") == "ca/business_partner_share"
    ]

    assert choice["consumes"]["count"] == "ca/business_partner_checked"
