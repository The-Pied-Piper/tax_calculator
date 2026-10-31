"""Schedule 3 Part 1 in the CA-ON manifest: a form of its own, with no instances, and what the
return reads.

Schedule 3 Part 1, flipped property, is the form `ca/schedule_3`, run once (it has no instances
list) on the answer to line 17905 and the nine tick boxes of line 17906, which are the return's
inputs. Its selections are in the part `03h_schedule_3_flipped_property.yaml` under the `form:` key,
and the checks of the life events ticked without a "Yes" are in the part
`27_schedule_3_life_event_checks.yaml`, which declares the same form. The form exports the flag
`ca/flipped_property` and the checked life event count, which the return does not read. The entries
of the form are listed in `manifest_families/schedule_3.py`.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import yaml

import tax_engine.jurisdictions.ca_on

# lists the packages; build_tax_computation registers their catalogs
import tax_engine.registrations
from tax_engine import build_tax_computation
from tax_engine.adapters.outbound.yaml_jurisdictions import YamlJurisdictionSource
from tax_engine.domain.form import FormComposition
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import CapabilitySelection, Form, Manifest
from tests.jurisdictions.ca_on.manifest_families import schedule_3

CA_ON = JurisdictionCode("CA-ON")
PART = (
    Path(tax_engine.jurisdictions.ca_on.__file__).parent
    / "manifests"
    / "v1"
    / "03h_schedule_3_flipped_property.yaml"
)
PART_LIFE_EVENT_CHECKS = (
    Path(tax_engine.jurisdictions.ca_on.__file__).parent
    / "manifests"
    / "v1"
    / "27_schedule_3_life_event_checks.yaml"
)


def manifest() -> Manifest:
    (only,) = (
        YamlJurisdictionSource(tax_engine.registrations.JURISDICTIONS.roots())
        .get_jurisdiction(CA_ON)
        .manifests
    )
    return only


def form() -> Form:
    (found,) = (found for found in manifest().forms if found.name == "ca/schedule_3")
    return found


def composed() -> FormComposition:
    return build_tax_computation().compose(CA_ON, 2025).form("ca/schedule_3")


# The ten checked answers in the order of the conditions: line 17905, then boxes 1 to 9.
_TEN_CHECKED = (
    "ca/flipped_property_disposed_checked",
    *(f"ca/flipped_property_life_event_{box}_checked" for box in range(1, 10)),
)


def _selection(selections: Iterable[CapabilitySelection], output: str) -> CapabilitySelection:
    """The one selection of the form whose output is `output`."""
    (found,) = (step for step in selections if dict(step.produces) == {"output": output})
    return found


# --- the part and the form -----------------------------------------------------------------------


def test_the_part_declares_the_form_ca_schedule_3_with_its_exports_and_no_instances() -> None:
    declared = yaml.safe_load(PART.read_text())["form"]

    assert declared == {
        "name": "ca/schedule_3",
        "required": True,
        "exports": list(schedule_3.FORM_EXPORTS),
    }


def test_the_life_event_checks_part_declares_the_form_ca_schedule_3_and_no_exports() -> None:
    # Its exports stay in the part 03h: this part only adds the steps of the form.
    declared = yaml.safe_load(PART_LIFE_EVENT_CHECKS.read_text())["form"]

    assert declared == {"name": "ca/schedule_3"}


def test_the_manifest_has_the_form_schedule_3_with_no_instances_and_its_exports() -> None:
    found = form()

    assert found.instances is None
    assert found.exports == schedule_3.FORM_EXPORTS


def test_the_form_holds_the_fourteen_selections_of_its_answers_flag_box_and_checks() -> None:
    found = form()

    assert len(found.capabilities) == 14
    assert set(found.capabilities) == schedule_3.FORM_STEPS


def test_the_return_selects_no_step_of_the_form() -> None:
    (default, *_) = manifest().forms

    assert set(default.capabilities).isdisjoint(schedule_3.FORM_STEPS)


def test_the_form_runs_once_with_the_ten_inputs_and_derives_the_flag_kind() -> None:
    found = composed()

    assert found.instances is None
    assert {kind.identifier for kind in found.imports} == set()
    assert [kind.identifier for kind in found.derived] == [
        "ca/schedule_3.flipped_property",
        "ca/schedule_3.principal_residence_designation_box",
        "ca/schedule_3.flipped_property_life_event_without_yes_checked",
    ]


def test_the_ten_inputs_are_the_manifest_inputs() -> None:
    assert schedule_3.INPUTS <= manifest().inputs.keys()
    assert len(schedule_3.INPUTS) == 10


# --- the flag and the answers it reads -----------------------------------------------------------


def test_the_flag_counts_the_ten_checked_answers_in_the_order_of_the_form() -> None:
    # Position 1 is line 17905 and positions 2 to 10 are boxes 1 to 9 of line 17906: the order the
    # conditions dataset reads them in.
    flag = _selection(schedule_3.FORM_STEPS, "ca/flipped_property")

    assert flag.name == "ca/count_by_conditions"
    assert flag.consumes["counts"] == _TEN_CHECKED
    assert flag.consumes["amounts"] == ()
    assert dict(flag.params) == {"conditions": "ca/schedule_3_flipped_property_conditions"}
    assert dict(flag.produces) == {"output": "ca/flipped_property"}


# --- the checks of a life event ticked without a "Yes" ------------------------------------------


def test_the_life_event_count_takes_the_ten_checked_answers_in_the_flags_order() -> None:
    # The same ten answers in the same order as the flag, and its own conditions dataset.
    step = _selection(form().capabilities, "ca/flipped_property_life_event_without_yes")

    assert step.name == "ca/count_by_conditions"
    assert step.consumes["counts"] == _TEN_CHECKED
    assert step.consumes["amounts"] == ()
    assert dict(step.params) == {"conditions": "ca/schedule_3_life_event_without_yes"}


def test_the_checked_life_event_count_is_refused_when_1_by_its_own_refused_conditions() -> None:
    step = _selection(form().capabilities, "ca/flipped_property_life_event_without_yes_checked")

    assert step.name == "ca/count_refused_by_conditions"
    assert step.consumes["count"] == "ca/flipped_property_life_event_without_yes"
    assert dict(step.params) == {"conditions": "ca/schedule_3_life_event_without_yes_refused"}
    assert dict(step.produces) == {"output": "ca/flipped_property_life_event_without_yes_checked"}


def test_the_composed_form_has_the_wiring_of_the_family() -> None:
    wiring = {
        (type(capability), capability.consumes, capability.produces)
        for capability in composed().composition.order
    }

    assert schedule_3.FORM_WIRING <= wiring
