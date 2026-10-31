"""Form T2205 "Amounts from a Spousal or Common-law Partner RRSP, RRIF, or SPP to Include in Income"
in the CA-ON manifest: the form `ca/t2205`, which runs once (no instances), and the twelve amounts
it takes.

The form is declared in `04e_t2205.yaml`, its starting inputs in `01p_t2205_inputs.yaml`. The
return reads its exports only in `03v_t2205_routing.yaml` (the form cannot read the age of the
filer, a figure of the return), which totals them and sends them to T1 lines 12900, 11500 and
13000; the sums of total income add those three amounts (`test_manifest.py` lists them with the
families). The entries of the form are listed in `manifest_families/t2205.py`.
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
from tax_engine.domain.composition import Composition
from tax_engine.domain.form import FormComposition
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import Form, Manifest
from tests.jurisdictions.ca_on.manifest_families import t2205 as family
from tests.jurisdictions.ca_on.manifest_support import input_names

CA_ON = JurisdictionCode("CA-ON")
MANIFESTS = Path(tax_engine.jurisdictions.ca_on.__file__).parent / "manifests" / "v1"
INPUTS_PART = MANIFESTS / "01p_t2205_inputs.yaml"
FORM_PART = MANIFESTS / "04e_t2205.yaml"
ROUTING_PART = MANIFESTS / "03v_t2205_routing.yaml"
T2205_PARTS = (INPUTS_PART, FORM_PART, ROUTING_PART)
LAYOUT = re.compile(r"^\d\d[a-z]?_[a-z0-9_]+\.yaml$")
# The sums of total income of the return, which add the three T1 amounts of the form in line order.
SUMS = ("03_income.yaml", "14a_income_before_losses.yaml")
# The part of the copies of Form T929, which totals the form's exports itself: the form cannot read
# the return's age figure, and the age does not change total income.
T929_COPIES = "05l_t929_copies_1.yaml"
T929_ROUTING_COPIES = "05y_t929_copies_4.yaml"


def manifest() -> Manifest:
    (only,) = (
        YamlJurisdictionSource(tax_engine.registrations.JURISDICTIONS.roots())
        .get_jurisdiction(CA_ON)
        .manifests
    )
    return only


def form(name: str) -> Form:
    (found,) = (each for each in manifest().forms if each.name == name)
    return found


def composed(name: str) -> FormComposition:
    return build_tax_computation().compose(CA_ON, 2025).form(name)


def wiring_of(composition: Composition) -> set[tuple[object, object, object]]:
    return {
        (type(capability), capability.consumes, capability.produces)
        for capability in composition.order
    }


def referenced(values: Iterable[object]) -> set[str]:
    """Every identifier named by the values of a selection's slots (a slot may hold a tuple)."""
    names: set[str] = set()
    for value in values:
        if isinstance(value, tuple):
            names |= set(value)
        else:
            names.add(str(value))
    return names


# --- the parts and the form ----------------------------------------------------------------------


def test_the_form_part_declares_the_form_once_with_its_exports() -> None:
    declared = yaml.safe_load(FORM_PART.read_text())["form"]

    assert declared["name"] == family.FORM
    assert "instances" not in declared
    assert set(declared["exports"]) == family.EXPORTS


def test_the_manifest_has_the_form_with_no_instances_and_its_exports() -> None:
    found = form(family.FORM)

    assert found.instances is None
    assert set(found.exports) == family.EXPORTS


def test_the_form_holds_the_selections_of_its_printed_lines() -> None:
    found = form(family.FORM)

    assert set(found.capabilities) == family.FORM_STEPS


def test_the_return_selects_none_of_the_steps_of_the_form() -> None:
    (default, *_) = manifest().forms
    selected = set(default.capabilities)

    assert selected.isdisjoint(family.FORM_STEPS)


def test_only_the_routing_part_and_the_t929_copies_read_the_exports_outside_the_form_s_parts() -> (
    None
):
    assert all(part.is_file() for part in T2205_PARTS)
    allowed = {path.name for path in T2205_PARTS} | {T929_COPIES, T929_ROUTING_COPIES}
    for path in MANIFESTS.glob("*.yaml"):
        if path.name in allowed:
            continue
        assert "ca/t2205." not in path.read_text(), path.name


def test_the_routing_part_reads_the_three_exports_the_return_reports() -> None:
    text = ROUTING_PART.read_text()

    for export in family.READ_EXPORTS:
        assert f"ca/t2205.{export.removeprefix('ca/')}" in text, export
    assert "ca/t2205.t2205_line_10" not in text
    assert "ca/t2205.t2205_line_21" not in text


def test_the_t2205_parts_are_named_by_the_layout_rule_and_not_over_30_kb() -> None:
    for part in T2205_PARTS:
        assert LAYOUT.match(part.name), part.name
        assert part.stat().st_size <= 30 * 1024, part.name


def test_the_sums_of_total_income_add_the_three_amounts_beside_their_t1_lines() -> None:
    placed = {
        "ca/other_pensions_and_superannuation": "ca/t2205_on_line_11500",
        "ca/rrsp_income": "ca/t2205_on_line_12900",
        "ca/other_income": "ca/t2205_on_line_13000",
    }
    for name in SUMS:
        text = (MANIFESTS / name).read_text()
        for line, added in placed.items():
            assert f"- {line}\n        - {added}\n" in text, (name, line)


def test_the_t929_copies_route_the_exports_as_the_return_does_and_add_them_to_total_income() -> (
    None
):
    copies = yaml.safe_load((MANIFESTS / T929_ROUTING_COPIES).read_text())
    declared = copies["capabilities"]
    totals = {
        step["produces"]["output"]: step["consumes"]["records"]
        for step in declared
        if step["name"] == "core/record_total"
    }
    counts = {step["consumes"]["count"] for step in declared if step["name"] == "core/times_count"}
    total_income = yaml.safe_load((MANIFESTS / T929_COPIES).read_text())["capabilities"]
    (sum_step,) = [step for step in total_income if step["produces"]["output"] == "ca/total_income"]
    parts = sum_step["consumes"]["parts"]

    assert copies["form"] == {"name": "ca/t929"}
    assert totals == {
        "ca/t2205_on_line_12900": "ca/t2205.t2205_line_11_rrsp_part",
        "ca/t2205_spp_part_total": "ca/t2205.t2205_line_11_spp_part_checked",
        "ca/t2205_line_22_total": "ca/t2205.t2205_line_22",
    }
    assert counts == {"ca/born_in_1960_or_earlier"}
    assert {"ca/t2205_on_line_11500", "ca/t2205_on_line_12900", "ca/t2205_on_line_13000"} <= set(
        parts
    )


# --- the inputs ----------------------------------------------------------------------------------


def test_the_inputs_part_declares_the_twelve_amounts_of_the_form() -> None:
    declared = input_names(yaml.safe_load(INPUTS_PART.read_text()))

    assert set(declared) == family.INPUTS
    assert family.INPUTS <= manifest().inputs.keys()


def test_the_form_s_exports_are_not_inputs_of_the_return() -> None:
    assert family.EXPORTS.isdisjoint(manifest().inputs.keys())
    assert family.EXPORTS.isdisjoint(family.INPUTS)


# --- the selections ------------------------------------------------------------------------------


def test_the_return_holds_the_routing_selections() -> None:
    (default, *_) = manifest().forms

    assert family.STEPS <= set(default.capabilities)


def test_a_part_is_refused_above_its_whole_and_is_not_capped() -> None:
    checked = {
        each.produces["output"]: each for each in family.FORM_STEPS if each.name == "core/at_most"
    }

    assert {
        name: (each.consumes["amount"], each.consumes["bound"]) for name, each in checked.items()
    } == {
        "ca/t2205_line_4_checked": ("ca/t2205_line_4", "ca/t2205_line_1"),
        "ca/t2205_line_7_checked": ("ca/t2205_line_7", "ca/t2205_line_6"),
        "ca/t2205_line_11_spp_part_checked": (
            "ca/t2205_line_11_spp_part",
            "ca/t2205_line_11",
        ),
        "ca/t2205_line_14_checked": ("ca/t2205_line_14", "ca/t2205_line_13"),
        "ca/t2205_line_18_checked": ("ca/t2205_line_18_used", "ca/t2205_line_17_used"),
    }


def test_line_9_is_line_3_and_has_no_step_of_its_own() -> None:
    produced = {each.produces["output"] for each in family.FORM_STEPS}

    assert not any("line_9" in name for name in produced)
    (line_11,) = [
        each for each in family.FORM_STEPS if each.produces == {"output": "ca/t2205_line_11"}
    ]
    assert line_11.consumes == {"amount": "ca/t2205_line_3", "less": "ca/t2205_line_10"}


def test_lines_10_and_21_are_the_lesser_of_their_two_amounts() -> None:
    selections = {each.produces["output"]: each for each in family.FORM_STEPS}

    assert selections["ca/t2205_line_10"].name == "core/lesser_of"
    assert selections["ca/t2205_line_10"].consumes == {
        "amounts": ("ca/t2205_line_5", "ca/t2205_line_8")
    }
    assert selections["ca/t2205_line_21"].name == "core/lesser_of"
    assert selections["ca/t2205_line_21"].consumes == {
        "amounts": ("ca/t2205_line_16", "ca/t2205_line_19")
    }


def test_lines_17_and_18_follow_part_1_by_the_sign_of_line_3() -> None:
    selections = {each.produces["output"]: each for each in family.FORM_STEPS}

    for used, filled, typed in (
        ("ca/t2205_line_17_used", "ca/t2205_line_6", "ca/t2205_line_17"),
        ("ca/t2205_line_18_used", "ca/t2205_line_18_from_part_1", "ca/t2205_line_18"),
    ):
        chosen = selections[used]
        assert chosen.name == "ca/choose_by_sign"
        assert chosen.consumes["sign"] == "ca/t2205_line_3"
        assert chosen.consumes["when_positive"] == (filled,)
        assert chosen.consumes["when_non_positive"] == (typed,)
    assert selections["ca/t2205_line_18_from_part_1"].consumes == {
        "parts": ("ca/t2205_line_7_checked", "ca/t2205_line_10")
    }


def test_line_22_subtracts_line_21_from_line_20_and_is_exported() -> None:
    (line_22,) = [
        each for each in family.FORM_STEPS if each.produces == {"output": "ca/t2205_line_22"}
    ]

    assert line_22.name == "core/subtract"
    assert line_22.consumes == {"amount": "ca/t2205_line_20", "less": "ca/t2205_line_21"}
    assert "ca/t2205_line_22" in family.EXPORTS


def test_the_routing_sends_the_amounts_by_the_age_count() -> None:
    times = [each for each in family.STEPS if each.name == "core/times_count"]

    assert {each.consumes["count"] for each in times} == {"ca/born_in_1960_or_earlier_checked"}
    assert {each.produces["output"] for each in times} == {
        "ca/t2205_spp_part_on_line_11500",
        "ca/t2205_line_22_on_line_11500",
    }


def test_every_input_of_the_form_is_read_by_some_step() -> None:
    read = referenced(value for each in family.FORM_STEPS for value in each.consumes.values())

    assert family.INPUTS <= read


# --- the composed form ---------------------------------------------------------------------------


def test_the_composed_form_runs_once() -> None:
    assert composed(family.FORM).instances is None


def test_the_composed_form_has_the_wiring_of_its_steps() -> None:
    assert family.FORM_WIRING <= wiring_of(composed(family.FORM).composition)


def test_the_composed_form_runs_the_lines_in_their_printed_order() -> None:
    order = composed(family.FORM).composition.order
    position = {
        kind.identifier: number for number, each in enumerate(order) for kind in each.produces
    }

    assert (
        position["ca/t2205_line_3"]
        < position["ca/t2205_line_5"]
        < position["ca/t2205_line_10"]
        < position["ca/t2205_line_11"]
        < position["ca/t2205_line_11_rrsp_part"]
    )
    assert (
        position["ca/t2205_line_16"] < position["ca/t2205_line_21"] < position["ca/t2205_line_22"]
    )
    assert position["ca/t2205_line_10"] < position["ca/t2205_line_18_from_part_1"]
    assert position["ca/t2205_line_19"] < position["ca/t2205_line_21"]
