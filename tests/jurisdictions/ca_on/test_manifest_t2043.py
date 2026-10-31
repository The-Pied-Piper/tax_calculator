"""Form T2043 in the CA-ON manifest: its own form, and what the return reads of it.

T2043, the Return of Fuel Charge Proceeds to Farmers Tax Credit, is the form `ca/t2043`, which has
no instances list, so it runs once. Its selections live in the part `03i_t2043.yaml` under the
`form:` key; its eight partnership credits are manifest inputs (`01_inputs.yaml`); and it exports
line 5D, which the return adds into line 48200 in `14_refund.yaml`, read as
`ca/t2043.fuel_charge_credit_farmers`. Its Chart A amounts are selections of the form `ca/t2042`,
in the part `03h_t2043_chart_a.yaml`, one record for each statement. The entries of the form are
listed in `manifest_families/t2043.py`.
"""

from __future__ import annotations

from pathlib import Path

import yaml

import tax_engine.jurisdictions.ca_on

# lists the packages; build_tax_computation registers their catalogs
import tax_engine.registrations
from tax_engine import build_tax_computation
from tax_engine.adapters.outbound.yaml_jurisdictions import YamlJurisdictionSource
from tax_engine.domain.form import FormComposition
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import Form, Manifest
from tests.jurisdictions.ca_on.manifest_families import t2042, t2043
from tests.jurisdictions.ca_on.manifest_support import inputs_text

CA_ON = JurisdictionCode("CA-ON")
PART = Path(tax_engine.jurisdictions.ca_on.__file__).parent / "manifests" / "v1" / "03i_t2043.yaml"
CHART_A_PART = PART.with_name("03h_t2043_chart_a.yaml")
REFUND_PART = PART.with_name("14_refund.yaml")
PARTNERSHIP_INPUTS = frozenset(
    {
        "ca/fuel_charge_partnership_credit_on",
        "ca/fuel_charge_partnership_credit_mb",
        "ca/fuel_charge_partnership_credit_sk",
        "ca/fuel_charge_partnership_credit_ab",
        "ca/fuel_charge_partnership_credit_ns",
        "ca/fuel_charge_partnership_credit_pe",
        "ca/fuel_charge_partnership_credit_nl",
        "ca/fuel_charge_partnership_credit_nb",
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
    (found,) = (each for each in manifest().forms if each.name == "ca/t2043")
    return found


def composed() -> FormComposition:
    return build_tax_computation().compose(CA_ON, 2025).form("ca/t2043")


# --- the parts and the form ----------------------------------------------------------------------


def test_the_t2043_part_declares_the_form_ca_t2043_with_no_instances_and_its_export() -> None:
    declared = yaml.safe_load(PART.read_text())["form"]

    # No `instances`: the form has no list of copies and runs once.
    assert declared == {
        "name": "ca/t2043",
        "required": True,
        "exports": list(t2043.FORM_EXPORTS),
    }


def test_the_chart_a_part_adds_selections_to_the_form_ca_t2042_and_declares_no_exports() -> None:
    declared = yaml.safe_load(CHART_A_PART.read_text())["form"]

    assert declared == {"name": "ca/t2042"}
    text = CHART_A_PART.read_text()
    assert "ca/farm_chart_a_subtotal" in text
    assert "ca/farm_chart_a_gross_expenses" in text


def test_the_manifest_has_the_form_t2043_with_no_instances_and_its_export() -> None:
    found = form()

    assert found.name == "ca/t2043"
    assert found.instances is None
    assert found.exports == t2043.FORM_EXPORTS


def test_the_form_holds_the_62_t2043_selections_with_line_5b_gated_on_part_4() -> None:
    # The 49 selections of before, the 11 of box 67062 (`BOX_67062_STEPS`): nine totals of the
    # statements present in each place, the statement count and the box, and the 2 of the
    # partnership credit tie (`PARTNERSHIP_CREDIT_TIE_STEPS`).
    found = form()

    assert len(found.capabilities) == 62
    assert set(found.capabilities) == t2043.FORM_STEPS
    line_5b = [
        each
        for each in found.capabilities
        if each.produces == {"output": "ca/fuel_charge_part_5b_credit"}
    ]
    assert len(line_5b) == 1
    assert line_5b[0].name == "ca/threshold_gate"
    assert line_5b[0].params == {"threshold": "ca/fuel_charge_expense_threshold"}
    assert line_5b[0].consumes == {
        "amount": "ca/fuel_charge_part_4_total",
        "gate": "ca/fuel_charge_gross_farming_expenses",
    }


def test_the_return_selects_none_of_the_form_steps_and_declares_no_output_for_the_form() -> None:
    (default, *_) = manifest().forms
    selected = set(default.capabilities)

    assert t2043.STEPS <= selected
    assert not selected & t2043.FORM_STEPS
    assert t2043.OUTPUTS == frozenset()
    assert "ca/fuel_charge_credit_farmers" not in set(default.exports)


def test_the_box_is_a_form_export_the_return_does_not_declare() -> None:
    # Like the other exports nothing on the return reads, the box is exported by the form only.
    (default, *_) = manifest().forms

    assert "ca/fuel_charge_multiple_provinces_box" in form().exports
    assert "ca/fuel_charge_multiple_provinces_box" not in default.exports


def test_the_partnership_credit_tie_totals_line_9951_and_checks_it_against_5c() -> None:
    # Line 9951 of each statement (`ca/t2042.farm_fuel_charge_credit`, one record for each
    # statement) is totalled and the total is checked at most amount 5C. Amount 5C may be more
    # (the AgriStability and AgriInvest forms carry their own line 9951), so it is not checked
    # against the total, and amount 5D adds it as it was. The checked total is a form export.
    found = form()
    (total,) = (
        each
        for each in found.capabilities
        if each.consumes == {"records": "ca/t2042.farm_fuel_charge_credit"}
    )
    assert total.name == "core/record_total"
    assert total.produces == {"output": "ca/farm_fuel_charge_credit_total"}
    (check,) = (each for each in found.capabilities if each.name == "core/at_most")
    assert check.consumes == {
        "amount": "ca/farm_fuel_charge_credit_total",
        "bound": "ca/fuel_charge_partnership_credit_total",
    }
    assert check.produces == {"output": "ca/farm_fuel_charge_credit_total_checked"}
    assert "ca/farm_fuel_charge_credit_total_checked" in found.exports
    (line_5d,) = (
        each
        for each in found.capabilities
        if each.produces == {"output": "ca/fuel_charge_credit_farmers"}
    )
    assert "ca/fuel_charge_partnership_credit_total" in line_5d.consumes["parts"]


def test_the_box_totals_the_nine_places_and_counts_the_statements() -> None:
    # Each place's total is the statements' presence amount for that place, one record for each
    # statement (`ca/t2042.farm_present_amount_<place>`). The statement count is the record count of
    # the statements (through the ON record list), and the box counts the pairs of places.
    found = form()
    places = ("on", "mb", "sk", "ab", "ns", "pe", "nl", "nb")
    pairs = [
        *(
            (f"ca/t2042.farm_present_amount_{p}", f"ca/fuel_charge_farms_in_province_{p}")
            for p in places
        ),
        ("ca/t2042.farm_present_amount_outside_eight", "ca/fuel_charge_farms_outside_eight"),
    ]
    totals = [
        each
        for each in found.capabilities
        if each.name == "core/record_total"
        and str(each.consumes.get("records", "")).startswith("ca/t2042.farm_present_amount_")
    ]
    counts = [each for each in found.capabilities if each.name == "ca-on/record_count"]
    boxes = [
        each
        for each in found.capabilities
        if each.produces == {"output": "ca/fuel_charge_multiple_provinces_box"}
    ]

    assert {(each.consumes["records"], each.produces["output"]) for each in totals} == set(pairs)
    assert len(counts) == 1
    assert counts[0].consumes == {"records": "ca/t2042.farm_present_amount_on"}
    assert counts[0].produces == {"output": "ca/fuel_charge_farm_statement_count"}
    assert len(boxes) == 1
    assert boxes[0].name == "ca/count_by_conditions"
    assert boxes[0].params == {"conditions": "ca/fuel_charge_multiple_provinces_box_conditions"}
    assert boxes[0].consumes == {
        "counts": ("ca/fuel_charge_farm_statement_count",),
        "amounts": tuple(total for _, total in pairs),
    }


def test_the_t2043_parts_are_not_over_30_kb() -> None:
    assert PART.stat().st_size <= 30 * 1024
    assert CHART_A_PART.stat().st_size <= 30 * 1024


# --- the inputs ----------------------------------------------------------------------------------


def test_the_eight_partnership_credits_are_manifest_inputs_declared_in_the_inputs_part() -> None:
    assert t2043.INPUTS == PARTNERSHIP_INPUTS
    assert t2043.INPUTS <= manifest().inputs.keys()
    text = inputs_text()
    for identifier in sorted(t2043.INPUTS):
        assert f"- name: {identifier}\n" in text, identifier


def test_the_t2043_part_declares_no_input_of_its_own() -> None:
    assert "inputs" not in yaml.safe_load(PART.read_text())


# --- the return's line 48200 --------------------------------------------------------------------


def test_the_line_48200_sum_takes_the_t2043_credit_after_line_47555_and_before_line_47600() -> None:
    (default, *_) = manifest().forms
    (total,) = [
        each for each in default.capabilities if each.produces == {"output": "ca/total_credits"}
    ]
    parts = tuple(total.consumes["parts"])

    assert "ca/fuel_charge_credit_farmers_total" in parts
    between = parts.index("ca/fuel_charge_credit_farmers_total")
    assert parts.index("ca/journalism_labour_tax_credit") < between
    assert between < parts.index("ca/tax_paid_by_instalments")
    assert "ca/t2043.fuel_charge_credit_farmers" not in parts
    assert "ca/fuel_charge_credit_farmers" not in parts


def test_the_return_totals_the_t2043_export_into_line_47556_before_the_line_48200_sum() -> None:
    (default, *_) = manifest().forms
    (total,) = [
        each
        for each in default.capabilities
        if each.produces == {"output": "ca/fuel_charge_credit_farmers_total"}
    ]

    assert total.name == "core/record_total"
    assert total.consumes == {"records": "ca/t2043.fuel_charge_credit_farmers"}
    assert total in t2043.STEPS


def test_the_line_48200_part_names_the_t2043_line_47556_in_its_comment() -> None:
    text = REFUND_PART.read_text()

    assert "line 47556" in text
    assert "ca/fuel_charge_credit_farmers_total" in text


# --- the composition -----------------------------------------------------------------------------


def test_the_form_set_runs_the_form_once_and_reads_the_chart_records_of_form_t2042() -> None:
    found = composed()

    assert found.instances is None
    assert found.imports == frozenset(
        {
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
        }
    )


def test_the_selections_inside_the_form_are_wired_as_declared() -> None:
    inner = {
        (type(capability), capability.consumes, capability.produces)
        for capability in composed().composition.order
    }

    assert inner == t2043.FORM_WIRING
