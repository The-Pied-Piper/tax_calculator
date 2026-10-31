"""Form T929 in the CA-ON manifest: one copy at most, the copies of the return's steps, and the line
21500 the return reads.

Form T929 (the disability supports deduction, T1 line 21500) is the form `ca/t929`, run once for
the one copy of the form the return carries (none, with an empty `ca/t929_instances`; at most one).
Its selections are in the parts `05k_t929.yaml` (the form's header and its 13 own steps,
`OWN_STEPS`, the last of which, the FHSA check, is in `05t_t929_yes_or_no_flag_check.yaml`),
`05l_t929_copies_1.yaml`, `05m_t929_copies_2.yaml`, `05x_t929_copies_3.yaml`,
`05p_t1436_lines_1_to_7_t929.yaml`,
`05r_t1223_part_c_t929.yaml` and `05w_t929_foreign_property_tax_over_limit.yaml` (the form only,
with the copies
of the return's steps that compute net income and the T1436 lines 1 to 7, `COPIED_STEPS`). The
return keeps the originals, and a guard checks that each copy is its original on the return,
except the line 23300 sum, which the return adds the deduction to. The return re-produces the
deduction with one `core/record_total` over the form's derived kind, placed before that sum in
`05_deductions.yaml`.
The entries are listed in `manifest_families/t929.py`.
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
from tax_engine.domain.capabilities.sum import Sum
from tax_engine.domain.capabilities.times_count import TimesCount
from tax_engine.domain.form import FormComposition
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import CapabilitySelection, Form, Manifest
from tax_engine.domain.record_list import RecordListKind
from tax_engine.jurisdictions.ca.catalog import (
    DEDUCTIONS_FROM_TOTAL_INCOME,
    DISABILITY_SUPPORTS_DEDUCTION,
    OTHER_EMPLOYMENT_EXPENSES,
    OTHER_SPLIT_INCOME_CHECKED,
    OTHER_SPLIT_INCOME_TOTAL,
    SUPPORT_PAYMENTS_DEDUCTION,
    SUPPORT_PAYMENTS_DEDUCTION_CHECKED,
    T929_INSTANCES,
    TOTAL_SPLIT_INCOME,
)
from tests.jurisdictions.ca_on.manifest_families import t929
from tests.jurisdictions.ca_on.manifest_support import (
    INPUTS_PARTS,
    inputs_text,
    instance_fields,
    lists,
    required_entries,
)

CA_ON = JurisdictionCode("CA-ON")
PARTS = Path(tax_engine.jurisdictions.ca_on.__file__).parent / "manifests" / "v1"
FORM_PARTS = (
    "05k_t929.yaml",
    "05l_t929_copies_1.yaml",
    "05m_t929_copies_2.yaml",
    "05p_t1436_lines_1_to_7_t929.yaml",
    "05r_t1223_part_c_t929.yaml",
    "05w_t929_foreign_property_tax_over_limit.yaml",
    "05x_t929_copies_3.yaml",
    "05y_t929_t746_deduction.yaml",
    "05z_t929_t1043_deduction.yaml",
    "05y_t929_copies_4.yaml",
)
COPIES_PARTS = FORM_PARTS[1:]
DEDUCTIONS_PART = PARTS / "05_deductions.yaml"
DEDUCTIONS_SUM = "ca/deductions_from_total_income"
DEDUCTION_PRODUCER = "ca/disability_supports_deduction"
# T1 line 22900 (ticket #446) is a part of the line 23300 sum of the return only, after line 22400.
OTHER_EMPLOYMENT_PRODUCER = "ca/other_employment_expenses"
# The copies read the manifest's inputs only, so they count Schedule 8's Part 4 and Part 5 from the
# filer's inputs; the return counts them from the checked counts that refuse a Form RC381 return.
CHECKED_COUNTS = {
    "ca/cpp_part_4_completed": "ca/cpp_part_4_completed_checked",
    "ca/cpp_part_5_completed": "ca/cpp_part_5_completed_checked",
    # Form T2205's routing: 65 or older at the end of the year (born in 1960 or earlier).
    "ca/born_in_1960_or_earlier": "ca/born_in_1960_or_earlier_checked",
}
# The line 23300 sum of the return reads these checked amounts where the copy reads the inputs they
# are checked from: the copy is a form, which cannot read the return's artifacts (and the check
# refuses any return on which the two would differ). The line 4 sum of Form T1206
# (`ca/total_split_income`) is copied the same way: the return reads the checked line 3, the copy
# reads line 3 as entered.
CHECKED_TO_RAW = {
    SUPPORT_PAYMENTS_DEDUCTION_CHECKED: SUPPORT_PAYMENTS_DEDUCTION,
    OTHER_SPLIT_INCOME_CHECKED: OTHER_SPLIT_INCOME_TOTAL,
}


def manifest() -> Manifest:
    (only,) = (
        YamlJurisdictionSource(tax_engine.registrations.JURISDICTIONS.roots())
        .get_jurisdiction(CA_ON)
        .manifests
    )
    return only


def form() -> Form:
    (found,) = (found for found in manifest().forms if found.name == "ca/t929")
    return found


def composed() -> FormComposition:
    return build_tax_computation().compose(CA_ON, 2025).form("ca/t929")


def return_wiring() -> set[tuple[type, frozenset[object], frozenset[object]]]:
    composition = build_tax_computation().compose(CA_ON, 2025).form("ca-on/return").composition
    return {
        (type(capability), capability.consumes, capability.produces)
        for capability in composition.order
    }


def produced_by(selections: set[CapabilitySelection], name: str) -> CapabilitySelection:
    (found,) = (selection for selection in selections if name in selection.produces.values())
    return found


# --- the parts and the form ----------------------------------------------------------------------


def test_the_first_part_declares_the_form_t929_with_its_instances_limits_and_exports() -> None:
    declared = yaml.safe_load((PARTS / FORM_PARTS[0]).read_text())["form"]

    assert declared == {
        "name": "ca/t929",
        "required": True,
        "fields": required_entries(instance_fields("ca/t929")),
        "instances": "ca/t929_instances",
        "max_instances": 1,
        "min_instances": 0,
        "exports": list(t929.FORM_EXPORTS),
    }
    assert len(t929.FORM_EXPORTS) == 7


def test_the_copies_parts_declare_only_the_form_ca_t929() -> None:
    for name in COPIES_PARTS:
        assert yaml.safe_load((PARTS / name).read_text())["form"] == {"name": "ca/t929"}, name


def test_each_t929_part_is_not_over_30_kb() -> None:
    for name in FORM_PARTS:
        assert (PARTS / name).stat().st_size <= 30 * 1024, name


def test_the_manifest_has_the_form_t929_with_at_most_one_instance() -> None:
    found = form()

    assert found.name == "ca/t929"
    assert found.instances == "ca/t929_instances"
    assert found.exports == t929.FORM_EXPORTS
    assert (found.min_instances, found.max_instances) == (0, 1)
    assert found.exclusive_group is None


def test_the_form_holds_the_13_own_selections_and_its_copies() -> None:
    found = form()

    assert len(t929.OWN_STEPS) == 13
    assert t929.FORM_STEPS == t929.OWN_STEPS | t929.COPIED_STEPS
    assert len(found.capabilities) == len(t929.FORM_STEPS)
    assert set(found.capabilities) == t929.FORM_STEPS


def test_the_return_totals_the_deduction_with_one_record_total_and_no_form_step() -> None:
    (default, *_) = manifest().forms
    selected = set(default.capabilities)

    assert t929.STEPS <= selected
    # The return checks the same flag as the form's own check (`05t_t929_yes_or_no_flag_check.yaml`
    # and `30_yes_or_no_flag_checks.yaml` select the same step), so that one step is on both.
    shared_checks = {step for step in t929.OWN_STEPS if step.name == "ca/yes_or_no_count"}
    assert selected & t929.OWN_STEPS == shared_checks
    assert {step.name for step in t929.STEPS} == {"core/record_total"}
    assert len(t929.STEPS) == 1


# --- the guard: each copy is its original on the return ------------------------------------------


def test_guard_every_copied_step_is_its_original_on_the_return_except_the_line_23300_sum() -> None:
    (default, *_) = manifest().forms
    selected = set(default.capabilities)
    copied_sum = produced_by(t929.COPIED_STEPS, DEDUCTIONS_SUM)
    copied_total_split = produced_by(t929.COPIED_STEPS, TOTAL_SPLIT_INCOME.identifier)

    counted = {
        step
        for step in t929.COPIED_STEPS
        if step.name == "core/times_count" and step.consumes["count"] in CHECKED_COUNTS
    }
    assert len(counted) == 4
    assert t929.COPIED_STEPS - {copied_sum, copied_total_split} - counted <= selected
    for step in counted:
        count = step.consumes["count"]
        assert isinstance(count, str)
        assert (
            CapabilitySelection(
                name=step.name,
                params=step.params,
                consumes={**step.consumes, "count": CHECKED_COUNTS[count]},
                produces=step.produces,
            )
            in selected
        )
    original_sum = produced_by(selected, DEDUCTIONS_SUM)
    assert original_sum.name == copied_sum.name == "core/sum"
    assert original_sum.params == copied_sum.params
    # The return's sum is the copy's with the deduction added after child care expenses, and with
    # the checked line 22000 amount (refused above line 21999) where the copy reads the input.
    raw_of = {checked.identifier: raw.identifier for checked, raw in CHECKED_TO_RAW.items()}
    original_parts = [raw_of.get(part, part) for part in original_sum.consumes["parts"]]
    copied_parts = copied_sum.consumes["parts"]
    assert set(original_parts) == set(copied_parts) | {
        DEDUCTION_PRODUCER,
        OTHER_EMPLOYMENT_PRODUCER,
    }
    assert (
        original_parts.index(DEDUCTION_PRODUCER)
        == original_parts.index("ca/child_care_expenses") + 1
    )
    assert original_sum.produces == copied_sum.produces
    # Form T1206 line 4 (`ca/total_split_income`) is the copy's sum with the checked line 3 read
    # where the copy reads the raw line 3, and the same output.
    original_total_split = produced_by(selected, TOTAL_SPLIT_INCOME.identifier)
    assert original_total_split.name == copied_total_split.name == "core/sum"
    assert [raw_of.get(part, part) for part in original_total_split.consumes["parts"]] == list(
        copied_total_split.consumes["parts"]
    )
    assert original_total_split.produces == copied_total_split.produces


def test_guard_each_copied_step_is_wired_as_its_original_on_the_return() -> None:
    own_outputs = {output for step in t929.OWN_STEPS for output in step.produces.values()}
    form_wiring = {
        (type(capability), capability.consumes, capability.produces)
        for capability in composed().composition.order
    }
    copied_wiring = {
        wiring
        for wiring in form_wiring
        if not {kind.identifier for kind in wiring[2]} & own_outputs
    }

    assert len(copied_wiring) == len(t929.COPIED_STEPS)
    # The return's wiring read back to the raw inputs the copy reads (`CHECKED_TO_RAW`).
    raw_of_kind: dict[object, object] = {k: v for k, v in CHECKED_TO_RAW.items()}
    return_wiring_raw = {
        (kind_type, frozenset(raw_of_kind.get(kind, kind) for kind in consumed), produced)
        for kind_type, consumed, produced in return_wiring()
    }
    missing = copied_wiring - return_wiring_raw
    # The line 23300 sum differs (the return adds the deduction to it, reads the checked line 22000)
    # and the two Part 4 and Part 5 counts (the return reads the checked counts). The line 4 sum
    # reads the checked line 3 on the return, so it matches once read back.
    counted = {wiring for wiring in missing if wiring[0] is TimesCount}
    assert len(counted) == 4
    (only,) = missing - counted
    assert only[0] is Sum
    assert only[2] == frozenset({DEDUCTIONS_FROM_TOTAL_INCOME})
    assert only[1] | {DISABILITY_SUPPORTS_DEDUCTION, OTHER_EMPLOYMENT_EXPENSES} in {
        frozenset(raw_of_kind.get(kind, kind) for kind in wiring[1])
        for wiring in return_wiring()
        if wiring[0] is Sum and wiring[2] == frozenset({DEDUCTIONS_FROM_TOTAL_INCOME})
    }


# --- the return's deduction and the line 23300 sum -----------------------------------------------


def test_the_return_totals_the_deduction_before_the_line_23300_sum_in_05_deductions() -> None:
    steps = yaml.safe_load(DEDUCTIONS_PART.read_text())["capabilities"]
    totals = [
        index
        for index, step in enumerate(steps)
        if step["name"] == "core/record_total" and step["produces"]["output"] == DEDUCTION_PRODUCER
    ]
    sums = [
        index
        for index, step in enumerate(steps)
        if step["name"] == "core/sum" and step["produces"]["output"] == DEDUCTIONS_SUM
    ]

    (total,) = totals
    (summed,) = sums
    assert steps[total]["consumes"] == {"records": "ca/t929.disability_supports_deduction"}
    assert total < summed
    parts = steps[summed]["consumes"]["parts"]
    assert parts.index(DEDUCTION_PRODUCER) == parts.index("ca/child_care_expenses") + 1


def test_the_other_parts_hold_no_t929_input() -> None:
    inputs_text_ = inputs_text()

    for identifier in t929.INPUTS:
        assert f"- name: {identifier}\n" in inputs_text_, identifier
    for name in sorted(path.name for path in PARTS.glob("*.yaml")):
        if name in (*FORM_PARTS, *(part.name for part in INPUTS_PARTS)):
            continue
        text = (PARTS / name).read_text()
        for identifier in t929.INPUTS:
            assert not lists(text, identifier), (name, identifier)


def test_the_disability_supports_deduction_is_no_longer_a_manifest_input() -> None:
    assert DISABILITY_SUPPORTS_DEDUCTION.identifier not in manifest().inputs.keys()
    assert not lists(inputs_text(), DEDUCTION_PRODUCER, indent="  ")


# --- the instances and the inputs -----------------------------------------------------------------


def test_the_instances_are_an_input_of_the_manifest() -> None:
    assert t929.INPUTS <= manifest().inputs.keys()
    assert "ca/t929_instances" in manifest().inputs.keys()


def test_the_instances_kind_is_a_record_list_with_no_fields() -> None:
    assert isinstance(T929_INSTANCES, RecordListKind)
    assert T929_INSTANCES.identifier == "ca/t929_instances"
    assert T929_INSTANCES.fields == ()


def test_the_catalog_registers_the_instances_kind_beside_the_other_record_lists() -> None:
    build_tax_computation()

    assert ArtifactRegistry.shared().kind("ca/t929_instances") is T929_INSTANCES


# --- the form and the return ----------------------------------------------------------------------


def test_the_form_runs_once_per_instance_and_derives_its_seven_kinds() -> None:
    found = composed()

    assert found.instances == T929_INSTANCES
    assert {kind.identifier for kind in found.imports} == t929.IMPORTS
    assert [kind.identifier for kind in found.derived] == [
        f"ca/t929.{export.removeprefix('ca/')}" for export in t929.FORM_EXPORTS
    ]
    assert (found.min_instances, found.max_instances) == (0, 1)


def test_the_form_own_selections_are_wired_as_declared() -> None:
    inner = {
        (type(capability), capability.consumes, capability.produces)
        for capability in composed().composition.order
    }

    assert len(composed().composition.order) == len(t929.FORM_STEPS)
    assert t929.FORM_WIRING <= inner
    assert len(t929.FORM_WIRING) == 13


def test_the_return_wiring_is_one_record_total_over_the_form_derived_kind() -> None:
    assert len(t929.WIRING) == 1
    assert {wiring[0].__name__ for wiring in t929.WIRING} == {"RecordTotal"}
    assert t929.WIRING <= return_wiring()


def test_the_return_declares_no_output_for_the_form_lines() -> None:
    (default, *_) = manifest().forms

    assert not {export for export in default.exports if export.startswith("ca/t929")}
    assert DEDUCTION_PRODUCER not in default.exports
