"""Form T776 in the CA-ON manifest: a form with any number of statements, and what the return reads.

T776 is the form `ca/t776`, one instance for each statement (one for each rental operation). Its
selections live in the part `03e_t776.yaml` under the `form:` key; the caller supplies the
statements as the record list `ca/t776_statements`, whose fields are the T776 inputs; and the form
exports its line 9946, "Your net income (loss)", which T1 line 12600 "Net" totals over the
statements. The entries of the form are listed in `manifest_families/t776.py`.
"""

from __future__ import annotations

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
    GROSS_RENTAL_INCOME,
    NET_RENTAL_INCOME,
    T776_STATEMENTS,
)
from tests.jurisdictions.ca_on.manifest_families import t776
from tests.jurisdictions.ca_on.manifest_support import (
    INPUTS_PARTS,
    capabilities_of,
    instance_fields,
    required_entries,
)

CA_ON = JurisdictionCode("CA-ON")
PART = Path(tax_engine.jurisdictions.ca_on.__file__).parent / "manifests" / "v1" / "03e_t776.yaml"
# The part is split in two to stay under 30 KB: the second holds the later steps.
PART_2 = PART.with_name("03e_t776_2.yaml")
INCOME_PART = PART.with_name("03_income.yaml")
INPUTS_PART = PART.with_name("01_inputs.yaml")
CHECKS_PART = PART.with_name("03e_t776_checks.yaml")
ADDITIONS_PART = PART.with_name("03t_t776_vehicle_additions_check.yaml")
AMOUNT_7_PART = PART.with_name("03z_t776_partner_amount_7.yaml")
SLIP_CHECKS_PART = PART.with_name("03z_t776_t5013_slip_checks.yaml")
CCA_POOL_PART = PART.with_name("03z_t776_cca_pool_statement.yaml")
AREAS_B_C_PART = PART.with_name("03e_t776_additions.yaml")


def coowner_checks() -> list[dict[str, object]]:
    """The eight checks of the co-owner's figures, in order: the share of recaptured CCA (line
    9947), the share of the terminal loss (line 9948) and the share of the CCA claim (Area A amount
    ii), each at most the whole of its class table; then the share of line 9369 (amount 2) against
    its bounds: the loss size of the whole (negated when negative), the upper bound (the whole's
    positive part), the lower bound (the whole's negative part), the share at most the upper bound,
    and at least the lower bound (`ca/rental_coowner_share_lower_checked`, exported)."""
    return [
        {
            "name": "core/at_most",
            "consumes": {
                "amount": "ca/rental_coowner_recaptured_cca",
                "bound": "ca/rental_cca_table_recapture",
            },
            "produces": {"output": "ca/rental_coowner_recaptured_cca_checked"},
        },
        {
            "name": "core/at_most",
            "consumes": {
                "amount": "ca/rental_coowner_terminal_loss",
                "bound": "ca/rental_cca_table_terminal_loss",
            },
            "produces": {"output": "ca/rental_coowner_terminal_loss_checked"},
        },
        {
            "name": "core/at_most",
            "consumes": {
                "amount": "ca/rental_coowner_cca_claim",
                "bound": "ca/rental_cca_table_claim",
            },
            "produces": {"output": "ca/rental_coowner_cca_claim_checked"},
        },
        {
            "name": "ca/positive_part_of_negation",
            "consumes": {"amount": "ca/rental_net_income_before_adjustments"},
            "produces": {"output": "ca/rental_net_income_loss_size"},
        },
        {
            "name": "core/sum",
            "consumes": {
                "parts": [
                    "ca/rental_net_income_before_adjustments",
                    "ca/rental_net_income_loss_size",
                ]
            },
            "produces": {"output": "ca/rental_net_income_upper_bound"},
        },
        {
            "name": "core/subtract",
            "consumes": {
                "amount": "ca/rental_net_income_before_adjustments",
                "less": "ca/rental_net_income_upper_bound",
            },
            "produces": {"output": "ca/rental_net_income_lower_bound"},
        },
        {
            "name": "core/at_most",
            "consumes": {
                "amount": "ca/rental_coowner_share",
                "bound": "ca/rental_net_income_upper_bound",
            },
            "produces": {"output": "ca/rental_coowner_share_checked"},
        },
        {
            "name": "core/at_most",
            "consumes": {
                "amount": "ca/rental_net_income_lower_bound",
                "bound": "ca/rental_coowner_share_checked",
            },
            "produces": {"output": "ca/rental_coowner_share_lower_checked"},
        },
    ]


def chart_checks() -> list[dict[str, object]]:
    """The three steps of Chart A's column 3, in `03e_t776_checks.yaml`: the column 3 total of the
    short-term rental units, at most line 9365 (the short-term portion of the total expenses); then
    line B (`ca/rental_non_compliant_expenses`) at most that checked total, so the check runs before
    line 1 subtracts line B."""
    return [
        {
            "name": "ca/short_term_rental_related_expenses",
            "consumes": {"units": "ca/short_term_rental_units"},
            "produces": {"output": "ca/short_term_rental_related_expenses_total"},
        },
        {
            "name": "core/at_most",
            "consumes": {
                "amount": "ca/short_term_rental_related_expenses_total",
                "bound": "ca/rental_short_term_portion",
            },
            "produces": {"output": "ca/short_term_rental_related_expenses_total_checked"},
        },
        {
            "name": "core/at_most",
            "consumes": {
                "amount": "ca/rental_non_compliant_expenses",
                "bound": "ca/short_term_rental_related_expenses_total_checked",
            },
            "produces": {"output": "ca/rental_non_compliant_expenses_checked"},
        },
    ]


def manifest() -> Manifest:
    (only,) = (
        YamlJurisdictionSource(tax_engine.registrations.JURISDICTIONS.roots())
        .get_jurisdiction(CA_ON)
        .manifests
    )
    return only


def form() -> Form:
    (found,) = (found for found in manifest().forms if found.name == "ca/t776")
    return found


def composed() -> FormComposition:
    found = build_tax_computation().compose(CA_ON, 2025).form("ca/t776")
    return found


# --- the part and the form -----------------------------------------------------------------------


def test_the_t776_part_declares_the_form_ca_t776_with_its_instances_and_exports() -> None:
    declared = yaml.safe_load(PART.read_text())["form"]

    assert declared == {
        "name": "ca/t776",
        "required": True,
        "fields": required_entries(instance_fields("ca/t776")),
        "instances": "ca/t776_statements",
        "exports": list(t776.FORM_EXPORTS),
    }


def test_the_manifest_has_the_form_t776_beside_the_other_forms() -> None:
    found = form()

    assert found.name == "ca/t776"
    assert found.instances == "ca/t776_statements"
    assert found.exports == t776.FORM_EXPORTS


def test_the_form_holds_the_t776_selections() -> None:
    # The selections of the T776 form: the step of the days of the fiscal period
    # (`ca/fiscal_period_days`), which the prorated CCA steps consume, the step that prorates the
    # immediate expensing limit by those days (`ca/prorated_by_fiscal_period_days`), the checks
    # of the co-owner and partner answers (in `03e_t776_checks.yaml`), the steps that count the
    # co-owner and partner answers conflicting with the figures entered, the checks of the
    # co-owner's figures (`coowner_checks`), the steps of Chart A's column 3 (`chart_checks`: the
    # total, checked at most line 9365, and line B checked after it), the Class 10.1 cost of
    # additions check of Area A, in `03t_t776_vehicle_additions_check.yaml`, the totals of Areas B
    # and C (lines 9925 and 9927, in `03e_t776_additions.yaml`), the T5013 slip checks, in
    # `03z_t776_t5013_slip_checks.yaml`, and the figure of the statement for the CCA limit over
    # all the statements, in `03z_t776_cca_pool_statement.yaml`, and amount 7 of a partner, in
    # `03z_t776_partner_amount_7.yaml`.
    found = form()

    assert set(found.capabilities) == t776.FORM_STEPS


def test_the_checks_part_declares_only_the_form_ca_t776_and_its_checks() -> None:
    declared = yaml.safe_load(CHECKS_PART.read_text())

    assert set(declared) == {"form", "capabilities"}
    assert declared["form"] == {"name": "ca/t776"}
    assert (
        declared["capabilities"]
        == [
            {
                "name": "ca/yes_or_no_count",
                "consumes": {"count": "ca/rental_coowner"},
                "produces": {"output": "ca/rental_coowner_checked"},
            },
            {
                "name": "ca/yes_or_no_count",
                "consumes": {"count": "ca/rental_partner"},
                "produces": {"output": "ca/rental_partner_checked"},
            },
        ]
        + coowner_checks()
        + chart_checks()
    )


def test_the_return_selects_no_t776_step_of_its_own_but_the_total_of_line_9946() -> None:
    (default, *_) = manifest().forms
    selected = set(default.capabilities)

    assert t776.STEPS <= selected
    assert selected.isdisjoint(t776.FORM_STEPS)


def test_the_t776_part_is_not_over_30_kb_and_the_other_parts_hold_no_t776_step() -> None:
    assert PART.stat().st_size <= 30 * 1024
    assert PART_2.stat().st_size <= 30 * 1024
    assert CHECKS_PART.stat().st_size <= 30 * 1024
    assert ADDITIONS_PART.stat().st_size <= 30 * 1024
    assert SLIP_CHECKS_PART.stat().st_size <= 30 * 1024
    assert CCA_POOL_PART.stat().st_size <= 30 * 1024
    assert AMOUNT_7_PART.stat().st_size <= 30 * 1024
    assert AREAS_B_C_PART.stat().st_size <= 30 * 1024
    for other in INPUTS_PARTS:
        text = other.read_text()
        assert "ca/rental_" not in text, other.name
        assert "ca/short_term_rental" not in text, other.name


# --- the instances input -------------------------------------------------------------------------


def test_the_instances_are_the_one_input_of_the_manifest_in_place_of_the_t776_inputs() -> None:
    inputs = manifest().inputs.keys()

    assert t776.INPUTS <= inputs
    assert inputs.isdisjoint(t776.FORM_INPUTS)


def test_the_statements_kind_is_a_record_list_of_every_t776_input_in_order() -> None:
    assert isinstance(T776_STATEMENTS, RecordListKind)
    assert T776_STATEMENTS.identifier == "ca/t776_statements"
    assert frozenset(field.identifier for field in T776_STATEMENTS.fields) == t776.FORM_INPUTS
    assert len(T776_STATEMENTS.fields) == len(t776.FORM_INPUTS)


def test_the_lists_of_a_statement_are_nested_record_lists() -> None:
    nested = {
        field.identifier for field in T776_STATEMENTS.fields if isinstance(field, RecordListKind)
    }

    assert nested == {
        "ca/rental_properties",
        "ca/short_term_rental_units",
        "ca/short_term_rental_cca_units",
        "ca/rental_cca_classes",
        "ca/rental_equipment_additions",
        "ca/rental_building_additions",
    }


def test_the_catalog_registers_the_statements_kind_beside_the_other_record_lists() -> None:
    build_tax_computation()

    assert ArtifactRegistry.shared().kind("ca/t776_statements") is T776_STATEMENTS


# --- the outputs and the node --------------------------------------------------------------------


def test_the_return_declares_no_output_for_the_exports_nothing_reads_but_the_gross_income() -> None:
    (default, *_) = manifest().forms
    exports = set(default.exports)

    assert t776.OUTPUTS <= exports
    assert (
        not {
            "ca/short_term_rental_gross_rents",
            "ca/rental_short_term_portion",
            "ca/rental_closing_ucc",
            "ca/rental_non_compliant_cca",
            "ca/short_term_rental_non_compliant_cca_by_class",
            "ca/rental_immediate_expensing_claim",
            "ca/rental_immediate_expensing_limit_unprorated",
            "ca/rental_equipment_additions_total",
            "ca/rental_building_additions_total",
        }
        & exports
    )
    assert not {export for export in exports if "." in export}


def test_the_form_set_runs_the_form_on_the_statements_and_derives_its_kinds() -> None:
    found = composed()

    assert found.instances == T776_STATEMENTS
    assert found.imports == frozenset()
    assert found.derived == (
        t776.NET_RENTAL_INCOME_PER_STATEMENT,
        t776.GROSS_RENTAL_INCOME_PER_STATEMENT,
        t776.SHORT_TERM_RENTAL_GROSS_RENTS_PER_STATEMENT,
        t776.RENTAL_SHORT_TERM_PORTION_PER_STATEMENT,
        t776.RENTAL_CLOSING_UCC_PER_STATEMENT,
        t776.RENTAL_NON_COMPLIANT_CCA_PER_STATEMENT,
        t776.SHORT_TERM_RENTAL_NON_COMPLIANT_CCA_BY_CLASS_PER_STATEMENT,
        t776.RENTAL_IMMEDIATE_EXPENSING_CLAIM_PER_STATEMENT,
        t776.RENTAL_IMMEDIATE_EXPENSING_LIMIT_UNPRORATED_PER_STATEMENT,
        t776.RENTAL_EQUIPMENT_ADDITIONS_TOTAL_PER_STATEMENT,
        t776.RENTAL_BUILDING_ADDITIONS_TOTAL_PER_STATEMENT,
        t776.RENTAL_LAND_ADDITIONS_PER_STATEMENT,
        t776.RENTAL_LAND_DISPOSITIONS_PER_STATEMENT,
        t776.RENTAL_COOWNER_SHARE_LOWER_CHECKED_PER_STATEMENT,
        t776.RENTAL_T5013_SLIP_CONFLICT_CHECKED_PER_STATEMENT,
        t776.RENTAL_PARTNER_AMOUNT_7_CONFLICT_CHECKED_PER_STATEMENT,
        t776.RENTAL_INCOME_BEFORE_CCA_PER_STATEMENT,
        t776.RENTAL_CCA_CLAIM_ON_OWN_PROPERTIES_PER_STATEMENT,
    )


def test_the_net_income_export_is_a_record_list_of_the_signed_net_rental_income() -> None:
    (net,) = (kind for kind in composed().derived if kind.identifier == "ca/t776.net_rental_income")

    assert net == t776.NET_RENTAL_INCOME_PER_STATEMENT
    assert net.fields == (NET_RENTAL_INCOME,)


def test_the_gross_income_export_is_a_record_list_of_the_total_gross_rental_income() -> None:
    (gross,) = (
        kind for kind in composed().derived if kind.identifier == "ca/t776.gross_rental_income"
    )

    assert gross == t776.GROSS_RENTAL_INCOME_PER_STATEMENT
    assert gross.fields == (GROSS_RENTAL_INCOME,)


def test_the_selections_inside_the_form_are_wired_as_they_were_on_the_return() -> None:
    inner = {
        (type(capability), capability.consumes, capability.produces)
        for capability in composed().composition.order
    }

    assert inner == t776.FORM_WIRING


# The Class 10.1 cost of additions check of Area A, in `03t_t776_vehicle_additions_check.yaml`:


def test_the_additions_part_declares_only_the_form_ca_t776_and_the_vehicle_additions_check() -> (
    None
):
    declared = yaml.safe_load(ADDITIONS_PART.read_text())

    assert set(declared) == {"form", "capabilities"}
    assert declared["form"] == {"name": "ca/t776"}
    assert declared["capabilities"] == [
        {
            "name": "ca/cca_vehicle_additions_checks",
            "params": {"prescribed_amounts": "ca/cca_vehicle_prescribed_amounts"},
            "consumes": {
                "classes": "ca/rental_cca_classes",
                "sales_tax_rate": "ca/rental_vehicle_sales_tax_rate",
            },
            "produces": {"output": "ca/rental_cca_classes_checked"},
        }
    ]


# The totals of Areas B and C, in `03e_t776_additions.yaml`:


def test_the_areas_b_and_c_part_declares_only_the_form_ca_t776_and_the_two_totals() -> None:
    declared = yaml.safe_load(AREAS_B_C_PART.read_text())

    assert set(declared) == {"form", "capabilities"}
    assert declared["form"] == {"name": "ca/t776"}
    assert declared["capabilities"] == [
        {
            "name": "ca/rental_additions_total",
            "consumes": {"additions": "ca/rental_equipment_additions"},
            "produces": {"total": "ca/rental_equipment_additions_total"},
        },
        {
            "name": "ca/rental_additions_total",
            "consumes": {"additions": "ca/rental_building_additions"},
            "produces": {"total": "ca/rental_building_additions_total"},
        },
    ]


def test_the_proceeds_step_reads_the_checked_list_and_produces_the_adjusted_one() -> None:
    steps = capabilities_of(PART, PART_2)
    (proceeds,) = [step for step in steps if step["name"] == "ca/cca_vehicle_proceeds"]

    assert proceeds["consumes"] == {
        "classes": "ca/rental_cca_classes_checked",
        "sales_tax_rate": "ca/rental_vehicle_sales_tax_rate",
    }
    assert proceeds["produces"] == {"output": "ca/rental_cca_classes_adjusted"}


def test_the_additions_check_is_the_only_step_that_reads_the_raw_rental_cca_classes() -> None:
    # Every other step of the form reads the classes after the check (the checked list or what it
    # produces), so no Class 10.1 row of Area A reaches the table unchecked.
    readers = {
        step.name
        for step in form().capabilities
        if "ca/rental_cca_classes" in {value for value in step.consumes.values()}
    }

    assert readers == {"ca/cca_vehicle_additions_checks"}


# The T5013 slip answer and its checks, in `03z_t776_t5013_slip_checks.yaml`:


def test_the_slip_checks_part_declares_only_the_form_ca_t776_and_the_slip_checks() -> None:
    declared = yaml.safe_load(SLIP_CHECKS_PART.read_text())

    assert set(declared) == {"form", "capabilities"}
    assert declared["form"] == {"name": "ca/t776"}
    assert declared["capabilities"] == [
        {
            "name": "ca/yes_or_no_count",
            "consumes": {"count": "ca/rental_partner_t5013_slip"},
            "produces": {"output": "ca/rental_partner_t5013_slip_checked"},
        },
        {
            "name": "ca/cca_opening_ucc_total",
            "consumes": {"classes": "ca/rental_cca_classes_checked"},
            "produces": {"output": "ca/rental_cca_opening_ucc_total"},
        },
        {
            "name": "ca/cca_additions_total",
            "consumes": {"classes": "ca/rental_cca_classes_checked"},
            "produces": {"output": "ca/rental_cca_additions_total"},
        },
        {
            "name": "ca/cca_personal_part_remaining_total",
            "consumes": {"classes": "ca/rental_cca_classes_checked"},
            "produces": {"output": "ca/rental_cca_personal_part_remaining_total"},
        },
        {
            "name": "ca/count_by_conditions",
            "params": {"conditions": "ca/t776_t5013_slip_conflicts"},
            "consumes": {
                "counts": ["ca/rental_partner_checked", "ca/rental_partner_t5013_slip_checked"],
                "amounts": [
                    "ca/rental_cca_table_claim",
                    "ca/rental_gross_rents",
                    "ca/rental_other_income",
                    "ca/rental_advertising",
                    "ca/rental_insurance",
                    "ca/rental_interest_and_bank_charges",
                    "ca/rental_office_expenses",
                    "ca/rental_professional_fees",
                    "ca/rental_management_and_administration_fees",
                    "ca/rental_repairs_and_maintenance",
                    "ca/rental_salaries_wages_and_benefits",
                    "ca/rental_property_taxes",
                    "ca/rental_travel",
                    "ca/rental_utilities",
                    "ca/rental_motor_vehicle_expenses",
                    "ca/rental_other_expenses",
                    "ca/rental_cca_table_recapture",
                    "ca/rental_cca_table_terminal_loss",
                    "ca/rental_land_additions",
                    "ca/rental_land_dispositions",
                    "ca/rental_cca_opening_ucc_total",
                    "ca/rental_cca_additions_total",
                    "ca/rental_cca_personal_part_remaining_total",
                    "ca/rental_equipment_additions_total",
                    "ca/rental_building_additions_total",
                ],
            },
            "produces": {"output": "ca/rental_t5013_slip_conflict"},
        },
        {
            "name": "ca/count_refused_by_conditions",
            "params": {"conditions": "ca/t776_t5013_slip_conflict_refused"},
            "consumes": {"count": "ca/rental_t5013_slip_conflict"},
            "produces": {"output": "ca/rental_t5013_slip_conflict_checked"},
        },
    ]


# The statement's figures for the limit over all statements, in `03z_t776_cca_pool_statement.yaml`:


def test_the_cca_pool_part_declares_only_the_form_ca_t776_and_the_statement_figures() -> None:
    declared = yaml.safe_load(CCA_POOL_PART.read_text())

    assert set(declared) == {"form", "capabilities"}
    assert declared["form"] == {"name": "ca/t776"}
    assert declared["capabilities"] == [
        {
            "name": "core/choose_by_count",
            "consumes": {
                "count": "ca/rental_partner_checked",
                "when_none": "ca/rental_net_income_after_terminal_loss",
                "when_any": "ca/rental_partner_amount_7",
            },
            "produces": {"output": "ca/rental_income_before_cca"},
        },
        {
            "name": "ca/positive_part_of_negation",
            "consumes": {"amount": "ca/rental_cca_table_claim"},
            "produces": {"output": "ca/rental_no_cca_claim"},
        },
        {
            "name": "core/choose_by_count",
            "consumes": {
                "count": "ca/rental_partner_checked",
                "when_none": "ca/rental_cca_claim",
                "when_any": "ca/rental_no_cca_claim",
            },
            "produces": {"output": "ca/rental_cca_claim_on_own_properties"},
        },
    ]


# Amount 7 of a partner, in `03z_t776_partner_amount_7.yaml`:


def test_the_amount_7_part_declares_only_the_form_ca_t776_and_the_steps_of_amount_7() -> None:
    declared = yaml.safe_load(AMOUNT_7_PART.read_text())

    assert set(declared) == {"form", "capabilities"}
    assert declared["form"] == {"name": "ca/t776"}
    assert declared["capabilities"] == [
        {
            "name": "ca/count_by_conditions",
            "params": {"conditions": "ca/t776_partner_amount_7_conflicts"},
            "consumes": {
                "counts": ["ca/rental_partner_checked", "ca/rental_partner_t5013_slip_checked"],
                "amounts": ["ca/rental_partner_share"],
            },
            "produces": {"output": "ca/rental_partner_amount_7_conflict"},
        },
        {
            "name": "ca/count_refused_by_conditions",
            "params": {"conditions": "ca/t776_partner_amount_7_conflict_refused"},
            "consumes": {"count": "ca/rental_partner_amount_7_conflict"},
            "produces": {"output": "ca/rental_partner_amount_7_conflict_checked"},
        },
        {
            "name": "core/at_most",
            "consumes": {
                "amount": "ca/rental_partner_percentage",
                "bound": "ca/rental_epop_percentage_maximum",
            },
            "produces": {"output": "ca/rental_partner_percentage_checked"},
        },
        {
            "name": "ca/apply_percentage",
            "params": {"rounding": "ca/rental_partner_share_rounding"},
            "consumes": {
                "amount": "ca/rental_net_income_after_cca",
                "percentage": "ca/rental_partner_percentage_checked",
            },
            "produces": {"output": "ca/rental_partner_share_of_amount_6"},
        },
        {
            "name": "core/choose_by_count",
            "consumes": {
                "count": "ca/rental_partner_t5013_slip_checked",
                "when_none": "ca/rental_partner_share_of_amount_6",
                "when_any": "ca/rental_partner_share",
            },
            "produces": {"output": "ca/rental_partner_amount_7"},
        },
    ]
