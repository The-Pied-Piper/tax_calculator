"""Form T1-M in the CA-ON manifest: any number of moves, and what the return reads.

T1-M is the form `ca/t1_m`, one instance for each move (each eligible move gets its own form). Its
selections live in the part `05k_t1_m.yaml` under the `form:` key; the caller supplies the moves as
the record list `ca/t1_m_moves`, whose fields are the caller's inputs of one move; and the form
exports its line 29, "Enter this amount on line 21900 of your return", which T1 line 21900 totals
over the moves, and its line 30, which nothing on the return reads. The entries of the form are
listed in `manifest_families/t1_m.py`.
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
    MOVING_EXPENSES_CLAIM,
    MOVING_EXPENSES_DEDUCTION,
    T1_M_MOVES,
)
from tests.jurisdictions.ca_on.manifest_families import t1_m
from tests.jurisdictions.ca_on.manifest_families.t1139 import (
    BUSINESS_PROFIT_ON_RETURN_LINES,
    COMMISSION_PROFIT_ON_RETURN_LINES,
    FARMING_PROFIT_ON_RETURN_LINES,
    FISHING_PROFIT_ON_RETURN_LINES,
    PROFESSIONAL_PROFIT_ON_RETURN_LINES,
)
from tests.jurisdictions.ca_on.manifest_support import (
    INPUTS_PARTS,
    instance_fields,
    lists,
    required_entries,
)

CA_ON = JurisdictionCode("CA-ON")
PART = Path(tax_engine.jurisdictions.ca_on.__file__).parent / "manifests" / "v1" / "05k_t1_m.yaml"
INCOME_PART = PART.with_name("01_inputs.yaml")
DEDUCTIONS_PART = PART.with_name("05_deductions.yaml")
AMT_PART = PART.with_name("20_alternative_minimum_tax.yaml")


def manifest() -> Manifest:
    (only,) = (
        YamlJurisdictionSource(tax_engine.registrations.JURISDICTIONS.roots())
        .get_jurisdiction(CA_ON)
        .manifests
    )
    return only


def form() -> Form:
    (found,) = (each for each in manifest().forms if each.name == "ca/t1_m")
    return found


def composed() -> FormComposition:
    return build_tax_computation().compose(CA_ON, 2025).form("ca/t1_m")


# --- the part and the form -----------------------------------------------------------------------


def test_the_t1_m_part_declares_the_form_ca_t1_m_with_its_instances_and_exports() -> None:
    declared = yaml.safe_load(PART.read_text())["form"]

    assert declared == {
        "name": "ca/t1_m",
        "required": True,
        "fields": required_entries(instance_fields("ca/t1_m")),
        "instances": "ca/t1_m_moves",
        "exports": list(t1_m.FORM_EXPORTS),
    }


def test_the_manifest_has_the_form_t1_m_beside_the_other_forms() -> None:
    found = form()

    assert found.name == "ca/t1_m"
    assert found.instances == "ca/t1_m_moves"
    assert found.exports == t1_m.FORM_EXPORTS


def test_the_form_holds_the_22_t1_m_selections() -> None:
    found = form()

    assert len(found.capabilities) == 22
    assert set(found.capabilities) == t1_m.FORM_STEPS


def test_line_28_is_checked_against_the_income_lines_before_lines_29_and_30_read_it() -> None:
    # Line 28 "Net eligible income" is at most the income lines it is taken from (`core/at_most`);
    # the checked amount is the one the lesser of (line 29) and line 30 read, and the raw amount
    # is read by the check alone.
    steps = yaml.safe_load(PART.read_text())["capabilities"]

    def read_by(identifier: str) -> list[int]:
        """The positions of the steps of the part that consume `identifier` (in a list or alone)."""
        positions: list[int] = []
        for position, step in enumerate(steps):
            for value in step.get("consumes", {}).values():
                if value == identifier or (isinstance(value, list) and identifier in value):
                    positions.append(position)
        return positions

    checks = [
        position
        for position, step in enumerate(steps)
        if step["name"] == "core/at_most"
        and "ca/moving_net_eligible_income" in step.get("consumes", {}).values()
    ]
    assert len(checks) == 1, "the part holds one core/at_most step on line 28, its check"
    check = checks[0]
    assert steps[check]["produces"] == {"output": "ca/moving_net_eligible_income_checked"}
    assert steps[check]["consumes"] == {
        "amount": "ca/moving_net_eligible_income",
        "bound": "ca/moving_eligible_income_lines",
    }
    assert read_by("ca/moving_net_eligible_income") == [check]
    checked_readers = read_by("ca/moving_net_eligible_income_checked")
    assert checked_readers and all(position > check for position in checked_readers)


def test_the_return_selects_only_the_total_of_line_21900_and_none_of_the_form_steps() -> None:
    (default, *_) = manifest().forms
    selected = set(default.capabilities)

    assert t1_m.STEPS <= selected
    assert not selected & t1_m.FORM_STEPS
    produced = set(chain.from_iterable(step.produces.values() for step in selected))
    assert "ca/moving_expenses_deduction" in produced


def test_the_form_selects_the_40_kilometre_test_and_the_5000_maximum_from_their_datasets() -> None:
    by_name = {step.name: step for step in form().capabilities}

    assert by_name["ca/threshold_gate"].params == {"threshold": "ca/moving_distance_threshold"}
    assert by_name["core/credit_amount"].params == {"amount": "ca/moving_old_home_maintenance_cap"}


def test_the_t1_m_part_is_not_over_30_kb_and_the_other_parts_hold_no_t1_m_input() -> None:
    assert PART.stat().st_size <= 30 * 1024
    for other in (*INPUTS_PARTS, DEDUCTIONS_PART, AMT_PART):
        text = other.read_text()
        for identifier in t1_m.FORM_INPUTS:
            assert not lists(text, identifier), (other.name, identifier)


# --- the instances input -------------------------------------------------------------------------


def test_the_instances_are_the_one_input_of_the_manifest_in_place_of_the_t1_m_inputs() -> None:
    inputs = manifest().inputs.keys()

    assert t1_m.INPUTS <= inputs
    assert inputs.isdisjoint(t1_m.FORM_INPUTS)


def test_the_moves_kind_is_a_record_list_of_every_t1_m_input_in_line_order() -> None:
    assert isinstance(T1_M_MOVES, RecordListKind)
    assert T1_M_MOVES.identifier == "ca/t1_m_moves"
    assert frozenset(field.identifier for field in T1_M_MOVES.fields) == t1_m.FORM_INPUTS
    assert len(T1_M_MOVES.fields) == len(t1_m.FORM_INPUTS) == 19


def test_the_catalog_registers_the_moves_kind_beside_the_other_record_lists() -> None:
    build_tax_computation()

    assert ArtifactRegistry.shared().kind("ca/t1_m_moves") is T1_M_MOVES


# --- the outputs and the node --------------------------------------------------------------------


def test_the_return_declares_no_output_for_line_30_which_nothing_reads() -> None:
    (default, *_) = manifest().forms
    exports = set(default.exports)

    assert t1_m.OUTPUTS <= exports
    assert "ca/moving_unused_expenses" not in exports
    assert not {export for export in exports if "." in export}


def test_the_form_set_runs_the_form_once_for_each_move_and_derives_its_two_kinds() -> None:
    found = composed()

    assert found.instances == T1_M_MOVES
    # The line 28 bound reads the profit lists of the summary form of Form T1139.
    assert found.imports == frozenset(
        {
            BUSINESS_PROFIT_ON_RETURN_LINES,
            PROFESSIONAL_PROFIT_ON_RETURN_LINES,
            COMMISSION_PROFIT_ON_RETURN_LINES,
            FARMING_PROFIT_ON_RETURN_LINES,
            FISHING_PROFIT_ON_RETURN_LINES,
        }
    )
    assert found.derived == (
        t1_m.MOVING_EXPENSES_CLAIM_PER_MOVE,
        t1_m.MOVING_UNUSED_EXPENSES_PER_MOVE,
    )


def test_the_claim_export_is_a_record_list_of_the_line_29_amount() -> None:
    (claim,) = (
        kind for kind in composed().derived if kind.identifier == "ca/t1_m.moving_expenses_claim"
    )

    assert claim == t1_m.MOVING_EXPENSES_CLAIM_PER_MOVE
    assert claim.fields == (MOVING_EXPENSES_CLAIM,)


def test_the_return_total_adds_the_claim_of_every_move_into_line_21900() -> None:
    # T1 line 21900 "Moving expenses (complete Form T1-M)": line 29 of each move, added.
    (step,) = t1_m.STEPS
    assert step.name == "core/record_total"
    assert step.consumes == {"records": "ca/t1_m.moving_expenses_claim"}
    assert step.produces == {"output": "ca/moving_expenses_deduction"}
    assert MOVING_EXPENSES_DEDUCTION.identifier == "ca/moving_expenses_deduction"


def test_the_selections_inside_the_form_are_wired_as_the_family_says() -> None:
    inner = {
        (type(capability), capability.consumes, capability.produces)
        for capability in composed().composition.order
    }

    assert inner == t1_m.FORM_WIRING
