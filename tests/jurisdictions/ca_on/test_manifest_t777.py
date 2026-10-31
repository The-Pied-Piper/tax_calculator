"""Form T777 in the CA-ON manifest: its two forms, and what the return reads of them.

T777, the Statement of Employment Expenses, is the form `ca/t777`, which has no instances list, so
it runs once. Its selections live in three parts: `03k_t777.yaml` (the capital cost allowance
schedule of Parts A and B, under the `form:` key with its exports), `03q_t777_lines.yaml` (the
lines 3, 4, 9, 11, 15, 16 and 17 and the line 3 and line 16 charts, under the same form) and
`03r_t777_relocation.yaml` (the labour mobility relocation form `ca/t777_relocation`, run once for
each relocation of `ca/t777_relocations`). Its inputs (the row lists, the page 1 expenses, the chart
figures and the relocations) live in `01c_t777_inputs.yaml`. The return reads line 17 (T1
line 22900,
in `05s_other_employment_expenses.yaml`); no other part reads the form's exports.

The entries of the forms are listed in `manifest_families/t777.py`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

import yaml

import tax_engine.jurisdictions.ca_on

# lists the packages; build_tax_computation registers their catalogs
import tax_engine.registrations
from tax_engine import build_tax_computation
from tax_engine.adapters.outbound.yaml_jurisdictions import YamlJurisdictionSource
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import Form, Manifest
from tests.jurisdictions.ca_on.manifest_families import t777
from tests.jurisdictions.ca_on.manifest_support import (
    input_names,
    instance_fields,
    required_entries,
)

CA_ON = JurisdictionCode("CA-ON")
MANIFESTS = Path(tax_engine.jurisdictions.ca_on.__file__).parent / "manifests" / "v1"
PART = MANIFESTS / "03k_t777.yaml"
INPUTS_PART = MANIFESTS / "01c_t777_inputs.yaml"
LINES_PART = MANIFESTS / "03q_t777_lines.yaml"
LEASING_PART = MANIFESTS / "03q_t777_leasing_chart.yaml"
RELOCATION_PART = MANIFESTS / "03r_t777_relocation.yaml"
ADDITIONS_PART = MANIFESTS / "03u_t777_vehicle_additions_check.yaml"
CLASS_PART = MANIFESTS / "03v_t777_vehicle_class_check.yaml"
NON_ARMS_LENGTH_PART = MANIFESTS / "03w_t777_vehicle_non_arms_length_check.yaml"
CHANGE_IN_USE_PART = MANIFESTS / "03x_t777_vehicle_change_in_use_check.yaml"
PART_A_CHANGE_IN_USE_PART = MANIFESTS / "03y_t777_change_in_use_check.yaml"
TOOLS_PART = MANIFESTS / "03q_t777_tradespersons_tools_maximum.yaml"
INTEREST_PART = MANIFESTS / "03q_t777_interest_chart.yaml"
APPRENTICE_PART = MANIFESTS / "03q_t777_apprentice_mechanic_tools_maximum.yaml"
ARTISTS_PART = MANIFESTS / "03q_t777_artists_employment_expenses_maximum.yaml"
MUSICAL_INSTRUMENT_PART = MANIFESTS / "03q_t777_musical_instrument_expenses_limit.yaml"
T777_PARTS = (
    PART,
    INPUTS_PART,
    LINES_PART,
    TOOLS_PART,
    LEASING_PART,
    INTEREST_PART,
    APPRENTICE_PART,
    ARTISTS_PART,
    MUSICAL_INSTRUMENT_PART,
    RELOCATION_PART,
    ADDITIONS_PART,
    CLASS_PART,
    NON_ARMS_LENGTH_PART,
    CHANGE_IN_USE_PART,
    PART_A_CHANGE_IN_USE_PART,
)
LAYOUT = re.compile(r"^\d\d[a-z]?_[a-z0-9_]+\.yaml$")

# The T777 lines of page 1 to 3 that the form computes and exports, in the order of `FORM_EXPORTS`.
NEW_LINE_EXPORTS = (
    "ca/t777_line_3",
    "ca/t777_line_4",
    "ca/t777_tools_formula_b",
    "ca/t777_tradespersons_tools_maximum_deduction",
    "ca/t777_line_9",
    "ca/t777_apprentice_mechanic_tools_maximum_deduction",
    "ca/t777_line_10",
    "ca/t777_artists_employment_expenses_maximum_deduction",
    "ca/t777_artists_expenses_carried_forward_out",
    "ca/t777_line_14",
    "ca/t777_line_11",
    "ca/t777_line_15",
    "ca/t777_line_16",
    "ca/t777_work_space_expenses",
    "ca/t777_line_17",
    "ca/t777_work_space_carried_forward_out",
)


def manifest() -> Manifest:
    (only,) = (
        YamlJurisdictionSource(tax_engine.registrations.JURISDICTIONS.roots())
        .get_jurisdiction(CA_ON)
        .manifests
    )
    return only


def form() -> Form:
    (found,) = (each for each in manifest().forms if each.name == "ca/t777")
    return found


def relocation_form() -> Form:
    (found,) = (each for each in manifest().forms if each.name == "ca/t777_relocation")
    return found


def referenced(values: Iterable[object]) -> set[str]:
    """Every identifier named by the values of a selection's slots (a slot may hold a tuple)."""
    names: set[str] = set()
    for value in values:
        if isinstance(value, tuple):
            names |= set(value)
        else:
            names.add(str(value))
    return names


# --- the parts and the forms ---------------------------------------------------------------------


def test_the_t777_part_declares_the_form_ca_t777_with_no_instances_and_its_exports() -> None:
    declared = yaml.safe_load(PART.read_text())["form"]

    # No `instances`: the form has no list of copies and runs once. The exports of the lines
    # computed in `03q_t777_lines.yaml` are declared here with the CCA exports.
    assert declared == {
        "name": "ca/t777",
        "required": True,
        "exports": list(t777.FORM_EXPORTS),
    }


def test_the_lines_part_is_a_part_of_the_form_ca_t777_and_declares_no_exports_of_its_own() -> None:
    # The same form as `03k_t777.yaml`, as `03h_t2043_chart_a.yaml` is a part of `ca/t2042`: its
    # selections join the form's, and its exports are declared in the form's own part.
    assert yaml.safe_load(LINES_PART.read_text())["form"] == {"name": "ca/t777"}


def test_the_tools_part_is_a_part_of_the_form_ca_t777_and_declares_no_exports_of_its_own() -> None:
    # The tradesperson's tools maximum of the Guide: the same form, its exports are in `PART`.
    assert yaml.safe_load(TOOLS_PART.read_text())["form"] == {"name": "ca/t777"}


def test_the_interest_part_is_a_part_of_the_form_ca_t777_and_declares_no_exports_of_its_own() -> (
    None
):
    # Line 26 and the interest chart of the Guide: the same form, its exports are in `PART`.
    assert yaml.safe_load(INTEREST_PART.read_text())["form"] == {"name": "ca/t777"}


def test_the_apprentice_part_is_a_part_of_the_form_ca_t777_and_declares_no_exports_of_its_own() -> (
    None
):
    # The apprentice mechanic tools maximum of the Guide: the same form, its exports are in `PART`.
    assert yaml.safe_load(APPRENTICE_PART.read_text())["form"] == {"name": "ca/t777"}


def test_the_artists_part_is_a_part_of_the_form_ca_t777_and_declares_no_exports_of_its_own() -> (
    None
):
    # The artists' employment expenses limit of the Guide: the same form, its exports are in `PART`.
    assert yaml.safe_load(ARTISTS_PART.read_text())["form"] == {"name": "ca/t777"}


def test_the_musical_instrument_part_is_a_part_of_form_t777_and_declares_no_exports() -> None:
    # The musical instrument expenses limit of the Guide: the same form, its exports are in `PART`.
    assert yaml.safe_load(MUSICAL_INSTRUMENT_PART.read_text())["form"] == {"name": "ca/t777"}


def test_the_relocation_part_declares_the_form_with_its_instances_and_exports() -> None:
    declared = yaml.safe_load(RELOCATION_PART.read_text())["form"]

    assert declared == {
        "name": "ca/t777_relocation",
        "required": True,
        "fields": required_entries(instance_fields("ca/t777_relocation")),
        "instances": "ca/t777_relocations",
        "exports": list(t777.RELOCATION_EXPORTS),
    }


def test_the_manifest_has_the_form_t777_with_no_instances_and_its_exports() -> None:
    found = form()

    assert found.name == "ca/t777"
    assert found.instances is None
    assert found.exports == t777.FORM_EXPORTS


def test_the_manifest_has_the_relocation_form_with_the_relocations_as_its_instances() -> None:
    found = relocation_form()

    assert found.instances == t777.RELOCATION_INSTANCES
    assert found.exports == t777.RELOCATION_EXPORTS


def test_the_form_exports_the_printed_lines_it_computes_as_well_as_the_cca_exports() -> None:
    assert set(t777.FORM_EXPORTS) == {
        *NEW_LINE_EXPORTS,
        "ca/t777_line_13",
        "ca/t777_musical_instrument_expenses_maximum_deduction",
        "ca/t777_musical_instrument_expenses_checked",
        "ca/t777_line_25",
        "ca/t777_lease_chart_conflict_checked",
        "ca/t777_class_8_closing_ucc",
        "ca/t777_vehicle_closing_ucc",
        "ca/t777_part_b_closing_ucc",
    }


def test_the_inputs_part_declares_the_form_s_inputs() -> None:
    declared = input_names(yaml.safe_load(INPUTS_PART.read_text()))

    assert set(declared) == t777.INPUTS
    assert t777.INPUTS <= manifest().inputs.keys()


def test_the_t777_parts_are_named_by_the_layout_rule_and_not_over_30_kb() -> None:
    for part in T777_PARTS:
        assert LAYOUT.match(part.name), part.name
        assert part.stat().st_size <= 30 * 1024, part.name


def test_only_the_t777_parts_and_the_return_s_line_22900_part_read_the_form_t777() -> None:
    # T1 line 22900 (`05s_other_employment_expenses.yaml`) reads line 17 of the form, and no other
    # part of the return reads any export of the form or of the relocation form.
    allowed = {path.name for path in T777_PARTS} | {
        "05s_other_employment_expenses.yaml",
        "05x_t777_apprentice_mechanic_tools_net_income_check.yaml",
        "02_outputs.yaml",
    }
    for path in MANIFESTS.glob("*.yaml"):
        if path.name in allowed:
            continue
        assert "ca/t777" not in path.read_text(), path.name


# --- the selections of the form ------------------------------------------------------------------


def test_the_form_steps_read_only_its_inputs_or_what_a_step_of_the_form_produces() -> None:
    # The steps are read part by part in file order, and the Class 10.1 additions check, class
    # check, non-arm's-length purchase check and change in use check (in `03u_`, `03v_`, `03w_` and
    # `03x_` parts) come after `03k_t777.yaml`, whose Part B claim reads their output: the order
    # the steps run in is checked by the composition, not by this file order.
    produced: set[str] = set()
    for step in form().capabilities:
        produced |= set(step.produces.values())
    known = set(manifest().inputs.keys()) | produced
    for step in form().capabilities:
        # A dotted reference is a copy's export of the relocation form, read as `form.export`.
        plain = {name for name in referenced(step.consumes.values()) if "." not in name}
        assert plain <= known, step.name

    assert set(t777.FORM_EXPORTS) <= produced


def test_the_form_holds_the_cca_steps_the_seventeen_line_steps_and_the_leasing_chart() -> None:
    # 16 CCA selections (`03k_t777.yaml`, `03u_t777_vehicle_additions_check.yaml`,
    # `03v_t777_vehicle_class_check.yaml`, `03w_t777_vehicle_non_arms_length_check.yaml`,
    # `03x_t777_vehicle_change_in_use_check.yaml` and the two Part A change in use checks of
    # `03y_t777_change_in_use_check.yaml`), 17 line selections (`03q_t777_lines.yaml`) and 19
    # leasing chart selections (`03q_t777_leasing_chart.yaml`).
    selected = set(form().capabilities)

    assert t777.LINE_STEPS <= selected
    assert t777.TOOLS_STEPS <= selected
    assert t777.LEASING_STEPS <= selected
    assert t777.INTEREST_STEPS <= selected
    assert t777.APPRENTICE_STEPS <= selected
    assert t777.ARTISTS_STEPS <= selected
    assert t777.MUSICAL_INSTRUMENT_STEPS <= selected
    assert len(form().capabilities) == 110
    assert len(t777.LINE_STEPS) == 17
    assert len(t777.TOOLS_STEPS) == 12
    assert len(t777.LEASING_STEPS) == 24
    assert len(t777.INTEREST_STEPS) == 3
    assert len(t777.APPRENTICE_STEPS) == 23
    assert len(t777.ARTISTS_STEPS) == 9
    assert len(t777.MUSICAL_INSTRUMENT_STEPS) == 5


def test_the_leasing_chart_part_is_a_part_of_the_form_t777() -> None:
    assert yaml.safe_load(LEASING_PART.read_text())["form"] == {"name": "ca/t777"}


def test_the_interest_chart_ends_in_line_26_and_line_29_reads_it() -> None:
    produced = {output for step in t777.INTEREST_STEPS for output in step.produces.values()}

    assert "ca/t777_line_26" in produced
    assert "ca/t777_line_26" in LINES_PART.read_text()


def test_the_leasing_chart_ends_in_line_27_and_line_29_reads_it() -> None:
    produced = {output for step in t777.LEASING_STEPS for output in step.produces.values()}

    assert "ca/t777_vehicle_leasing_costs" in produced
    assert "ca/t777_vehicle_leasing_costs" in LINES_PART.read_text()


def test_the_form_is_built_of_the_cca_table_capabilities() -> None:
    names = {step.name for step in form().capabilities}

    assert t777.FORM_TABLE_CAPABILITIES <= names


def test_the_part_a_checks_read_each_raw_list_and_pass_its_checked_list_on() -> None:
    checks = [step for step in form().capabilities if step.name in t777.FORM_CHECK_CAPABILITIES]

    assert {(tuple(step.consumes.items()), tuple(step.produces.items())) for step in checks} == {
        (
            (("classes", "ca/t777_class_8_rows"),),
            (("output", "ca/t777_class_8_checked_rows"),),
        ),
        (
            (("classes", "ca/t777_vehicle_rows"),),
            (("output", "ca/t777_vehicle_checked_rows"),),
        ),
    }
    assert t777.FORM_CHECKED_LISTS <= {value for step in checks for value in step.produces.values()}


def test_only_the_part_a_checks_read_the_raw_part_a_lists() -> None:
    raw = {"ca/t777_class_8_rows", "ca/t777_vehicle_rows"}
    for step in form().capabilities:
        if step.name in t777.FORM_CHECK_CAPABILITIES:
            continue
        assert not referenced(step.consumes.values()) & raw, step.name


def test_the_class_8_claim_closing_ucc_and_vehicle_proceeds_read_the_change_in_use_rows() -> None:
    # Line 13 and the Class 8 closing UCC read the Class 8 rows that passed the change in use check;
    # the sold-vehicle proceeds read the vehicle rows that passed it, and what they produce is the
    # list the vehicle claim reads.
    readers = {
        step.name
        for step in form().capabilities
        if "ca/t777_class_8_change_in_use_checked_rows" in referenced(step.consumes.values())
    }
    proceeds = [step for step in form().capabilities if step.name == "ca/cca_vehicle_proceeds"]

    assert readers == {"ca/cca_claim", "ca/closing_ucc"}
    assert [step.consumes["classes"] for step in proceeds] == [
        "ca/t777_vehicle_change_in_use_checked_rows"
    ]
    assert [step.produces["output"] for step in proceeds] == ["ca/t777_vehicle_rows_adjusted"]


def test_the_part_a_checked_rows_are_read_by_the_change_in_use_checks_only() -> None:
    # The Part A checks pass their rows on to the change in use checks and to nothing else: the
    # Class 8 and vehicle claims, the closing UCC and the proceeds read the change in use rows.
    for identifier in t777.FORM_CHANGE_IN_USE_READS:
        readers = {
            step.name
            for step in form().capabilities
            if identifier in referenced(step.consumes.values())
        }
        assert readers == t777.FORM_CHANGE_IN_USE_CAPABILITIES, identifier


def test_the_part_a_change_in_use_checks_read_the_part_a_checked_rows_and_produce_their_lists() -> (
    None
):
    checks = [
        step for step in form().capabilities if step.name in t777.FORM_CHANGE_IN_USE_CAPABILITIES
    ]

    assert len(checks) == 2
    assert {step.produces["output"] for step in checks} == t777.FORM_CHANGE_IN_USE_CHECKED_LISTS
    assert {
        name for step in checks for name in referenced(step.consumes.values())
    } == t777.FORM_CHANGE_IN_USE_READS
    assert {step.consumes["classes"] for step in checks} == t777.FORM_CHANGE_IN_USE_READS


def test_the_part_a_change_in_use_part_declares_the_form_ca_t777_and_the_two_checks_only() -> None:
    declared = yaml.safe_load(PART_A_CHANGE_IN_USE_PART.read_text())

    assert set(declared) == {"form", "capabilities"}
    assert declared["form"] == {"name": "ca/t777"}
    assert declared["capabilities"] == [
        {
            "name": "ca/cca_change_in_use_checks",
            "consumes": {"classes": "ca/t777_class_8_checked_rows"},
            "produces": {"output": "ca/t777_class_8_change_in_use_checked_rows"},
        },
        {
            "name": "ca/cca_change_in_use_checks",
            "consumes": {"classes": "ca/t777_vehicle_checked_rows"},
            "produces": {"output": "ca/t777_vehicle_change_in_use_checked_rows"},
        },
    ]


def test_the_form_reads_its_three_class_rates_datasets_and_not_the_shared_one() -> None:
    read = {value for step in form().capabilities for value in step.params.values()}

    assert t777.FORM_DATASETS <= read
    assert "ca/cca_class_rates" not in read


def test_the_form_reads_the_datasets_of_its_lines_and_the_shared_rounding_of_line_30() -> None:
    read = {value for step in form().capabilities for value in step.params.values()}

    assert t777.LINE_DATASETS <= read


def test_the_form_steps_are_not_selected_by_the_return() -> None:
    (default, *_) = manifest().forms
    selected = set(default.capabilities)

    assert t777.STEPS <= selected
    assert not selected & set(form().capabilities)
    assert t777.OUTPUTS == frozenset(
        {"ca/t777_line_10_checked", "ca/t777_apprentice_mechanic_tools_carried_forward_out"}
    )
    # The return reads the form's exports only through the derived kinds `ca/t777.t777_line_17`
    # (T1 line 22900) and `ca/t777.t777_line_10` (the limit of the apprentice mechanic tools claim
    # to the net income), each by one core/record_total; no other step of the return reads them.
    readers = [
        each
        for each in default.capabilities
        if any(name.startswith("ca/t777.") for name in referenced(each.consumes.values()))
    ]

    assert [each.name for each in readers] == ["core/record_total"] * 3
    assert {name for each in readers for name in referenced(each.consumes.values())} == {
        "ca/t777.t777_line_17",
        "ca/t777.t777_line_10",
        "ca/t777.t777_apprentice_mechanic_tools_maximum_deduction",
    }


# --- the relocation form -------------------------------------------------------------------------


def test_the_relocation_form_holds_its_four_selections_for_lines_37_to_40() -> None:
    assert set(relocation_form().capabilities) == t777.RELOCATION_STEPS
    assert len(relocation_form().capabilities) == 4


def test_the_relocation_form_reads_its_record_fields_or_what_an_earlier_step_produced() -> None:
    known = set(t777.RELOCATION_FIELDS) | set(t777.RELOCATION_DATASETS)
    produced: set[str] = set()
    for step in relocation_form().capabilities:
        assert referenced(step.consumes.values()) <= known | produced, step.name
        produced |= set(step.produces.values())

    assert set(t777.RELOCATION_EXPORTS) <= produced


def test_the_relocation_form_reads_the_relocation_datasets_and_the_maximum_of_line_39() -> None:
    read = {value for step in relocation_form().capabilities for value in step.params.values()}

    assert read == set(t777.RELOCATION_DATASETS)


def test_the_form_totals_the_relocation_copies_and_refuses_line_41_above_the_maximum() -> None:
    # Line 41 "Total labour mobility deduction for the year (maximum $4,000)": the line 39 amounts
    # of the copies, totalled, and at most the maximum.
    total = [
        step
        for step in form().capabilities
        if step.consumes == {"records": "ca/t777_relocation.t777_relocation_deduction"}
    ]
    assert [step.name for step in total] == ["core/record_total"]
    assert [step.produces for step in total] == [{"output": "ca/t777_relocation_deduction_total"}]
    (capped,) = (
        step for step in form().capabilities if step.produces == {"output": "ca/t777_line_11"}
    )

    assert capped.name == "core/at_most"
    assert capped.consumes == {
        "amount": "ca/t777_relocation_deduction_total",
        "bound": "ca/t777_line_11_maximum",
    }


def test_the_relocation_form_is_not_a_form_of_the_return_and_its_copies_are_not_read_by_it() -> (
    None
):
    (default, *_) = manifest().forms
    assert not set(default.capabilities) & set(relocation_form().capabilities)
    for each in default.capabilities:
        assert "ca/t777_relocation." not in " ".join(referenced(each.consumes.values()))


def test_the_relocations_are_the_one_input_of_the_form_in_place_of_its_copy_fields() -> None:
    assert "ca/t777_relocations" in t777.INPUTS
    assert not t777.RELOCATION_FIELDS & t777.INPUTS


# --- the Class 10.1 cost of additions check of Part B (`03u_t777_vehicle_additions_check.yaml`) ---


def test_the_additions_part_declares_the_form_ca_t777_and_the_class_10_1_check_only() -> None:
    declared = yaml.safe_load(ADDITIONS_PART.read_text())

    assert set(declared) == {"form", "capabilities"}
    assert declared["form"] == {"name": "ca/t777"}
    assert declared["capabilities"] == [
        {
            "name": "ca/cca_vehicle_additions_checks",
            "params": {"prescribed_amounts": "ca/cca_vehicle_prescribed_amounts"},
            "consumes": {
                "classes": "ca/t777_part_b_checked_rows",
                "sales_tax_rate": "ca/t777_vehicle_sales_tax_rate",
            },
            "produces": {"output": "ca/t777_part_b_additions_checked_rows"},
        }
    ]


def test_the_class_part_declares_the_form_ca_t777_and_the_class_10_1_condition_check_only() -> None:
    declared = yaml.safe_load(CLASS_PART.read_text())

    assert set(declared) == {"form", "capabilities"}
    assert declared["form"] == {"name": "ca/t777"}
    assert declared["capabilities"] == [
        {
            "name": "ca/cca_vehicle_class_checks",
            "params": {"class_conditions": "ca/cca_class_10_1_conditions"},
            "consumes": {"classes": "ca/t777_part_b_additions_checked_rows"},
            "produces": {"output": "ca/t777_part_b_class_checked_rows"},
        }
    ]


def test_the_part_b_claim_reads_the_change_in_use_checked_rows_and_produces_the_claim() -> None:
    steps = yaml.safe_load(PART.read_text())["capabilities"]
    (claim,) = [step for step in steps if step["produces"] == {"output": "ca/t777_part_b_claim"}]

    assert claim["name"] == "ca/cca_claim"
    assert claim["consumes"] == {"classes": "ca/t777_part_b_change_in_use_checked_rows"}
    assert claim["params"] == {"class_rates": "ca/t777_part_b_class_rates"}


def test_the_part_b_closing_ucc_still_reads_the_part_b_checked_rows() -> None:
    # The Part B closing UCC is unchanged by the check: it reads the rows the Part B checks passed.
    steps = yaml.safe_load(PART.read_text())["capabilities"]
    (closing,) = [
        step for step in steps if step["produces"] == {"output": "ca/t777_part_b_closing_ucc"}
    ]

    assert closing["consumes"] == {"classes": "ca/t777_part_b_checked_rows"}


def test_the_part_b_checked_rows_are_read_by_the_additions_check_and_the_closing_ucc_only() -> None:
    readers = {
        step.name
        for step in form().capabilities
        if "ca/t777_part_b_checked_rows" in referenced(step.consumes.values())
    }

    assert readers == {"ca/closing_ucc", "ca/cca_vehicle_additions_checks"}


def test_the_part_b_additions_check_reads_the_prescribed_amounts_of_class_10_1() -> None:
    checks = [
        step for step in form().capabilities if step.name == "ca/cca_vehicle_additions_checks"
    ]

    assert [step.params["prescribed_amounts"] for step in checks] == [
        "ca/cca_vehicle_prescribed_amounts"
    ]
    assert t777.PART_B_ADDITIONS_CHECK_DATASETS <= {
        value for step in checks for value in step.params.values()
    }
    assert {step.produces["output"] for step in checks} == t777.PART_B_ADDITIONS_CHECKED_LISTS


def test_the_part_b_class_check_reads_the_class_conditions_of_class_10_1() -> None:
    checks = [step for step in form().capabilities if step.name == "ca/cca_vehicle_class_checks"]

    assert [step.params["class_conditions"] for step in checks] == ["ca/cca_class_10_1_conditions"]
    assert t777.PART_B_CLASS_CHECK_DATASETS <= {
        value for step in checks for value in step.params.values()
    }
    assert {step.produces["output"] for step in checks} == t777.PART_B_CLASS_CHECKED_LISTS
    assert {
        name for step in checks for name in referenced(step.consumes.values())
    } == t777.PART_B_ADDITIONS_CHECKED_LISTS


def test_the_non_arms_length_part_declares_the_form_ca_t777_and_the_purchase_check_only() -> None:
    declared = yaml.safe_load(NON_ARMS_LENGTH_PART.read_text())

    assert set(declared) == {"form", "capabilities"}
    assert declared["form"] == {"name": "ca/t777"}
    assert declared["capabilities"] == [
        {
            "name": "ca/cca_vehicle_non_arms_length_checks",
            "params": {"prescribed_amounts": "ca/cca_vehicle_prescribed_amounts"},
            "consumes": {
                "classes": "ca/t777_part_b_class_checked_rows",
                "sales_tax_rate": "ca/t777_vehicle_sales_tax_rate",
            },
            "produces": {"output": "ca/t777_part_b_non_arms_length_checked_rows"},
        }
    ]


def test_the_change_in_use_part_declares_the_form_ca_t777_and_the_change_in_use_check_only() -> (
    None
):
    declared = yaml.safe_load(CHANGE_IN_USE_PART.read_text())

    assert set(declared) == {"form", "capabilities"}
    assert declared["form"] == {"name": "ca/t777"}
    assert declared["capabilities"] == [
        {
            "name": "ca/cca_vehicle_change_in_use_checks",
            "consumes": {"classes": "ca/t777_part_b_non_arms_length_checked_rows"},
            "produces": {"output": "ca/t777_part_b_change_in_use_checked_rows"},
        }
    ]


def test_the_part_b_non_arms_length_check_reads_the_prescribed_amounts_of_class_10_1() -> None:
    checks = [
        step for step in form().capabilities if step.name == "ca/cca_vehicle_non_arms_length_checks"
    ]

    assert [step.params["prescribed_amounts"] for step in checks] == [
        "ca/cca_vehicle_prescribed_amounts"
    ]
    assert t777.PART_B_NON_ARMS_LENGTH_CHECK_DATASETS <= {
        value for step in checks for value in step.params.values()
    }
    assert {step.produces["output"] for step in checks} == t777.PART_B_NON_ARMS_LENGTH_CHECKED_LISTS
    assert {
        name for step in checks for name in referenced(step.consumes.values())
    } == t777.PART_B_CLASS_CHECKED_LISTS | {"ca/t777_vehicle_sales_tax_rate"}


def test_the_part_b_change_in_use_check_reads_the_non_arms_length_checked_rows() -> None:
    checks = [
        step for step in form().capabilities if step.name == "ca/cca_vehicle_change_in_use_checks"
    ]

    assert len(checks) == 1
    assert {step.produces["output"] for step in checks} == t777.PART_B_CHANGE_IN_USE_CHECKED_LISTS
    assert {
        name for step in checks for name in referenced(step.consumes.values())
    } == t777.PART_B_NON_ARMS_LENGTH_CHECKED_LISTS


def test_the_part_b_claim_runs_after_the_checks_in_the_composed_form() -> None:
    # The composition orders the form's steps by what they read: the Class 10.1 rows are checked
    # before the Part B claim is totalled, whatever the order of the parts.
    order = build_tax_computation().compose(CA_ON, 2025).form("ca/t777").composition.order
    position = {
        kind.identifier: i for i, capability in enumerate(order) for kind in capability.produces
    }

    assert (
        position["ca/t777_part_b_additions_checked_rows"]
        < position["ca/t777_part_b_class_checked_rows"]
    )
    assert (
        position["ca/t777_part_b_class_checked_rows"]
        < position["ca/t777_part_b_non_arms_length_checked_rows"]
    )
    assert (
        position["ca/t777_part_b_non_arms_length_checked_rows"]
        < position["ca/t777_part_b_change_in_use_checked_rows"]
    )
    assert position["ca/t777_part_b_change_in_use_checked_rows"] < position["ca/t777_part_b_claim"]


def test_the_part_a_change_in_use_checks_run_between_the_part_a_checks_and_their_claims() -> None:
    # The composition orders the Part A steps by what they read: each Class 8 and vehicle row is
    # checked for a change in use before line 13, the Class 8 closing UCC and the proceeds read it.
    order = build_tax_computation().compose(CA_ON, 2025).form("ca/t777").composition.order
    position = {
        kind.identifier: i for i, capability in enumerate(order) for kind in capability.produces
    }

    assert (
        position["ca/t777_class_8_checked_rows"]
        < position["ca/t777_class_8_change_in_use_checked_rows"]
        < position["ca/t777_line_13"]
    )
    assert (
        position["ca/t777_vehicle_checked_rows"]
        < position["ca/t777_vehicle_change_in_use_checked_rows"]
        < position["ca/t777_vehicle_rows_adjusted"]
    )
