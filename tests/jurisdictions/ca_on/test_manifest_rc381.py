"""Form RC381 in the CA-ON manifest: a form of none or one copy, and what the return reads.

Form RC381, the inter-provincial calculation for CPP and QPP contributions and overpayments, is the
form `ca/rc381`, run once for the one copy of the form the return carries (none, with an empty
`ca/rc381_instances`), in the exclusive group `ca/cpp_calculation` with Schedule 8. Its selections
are in the parts `08a_rc381_part_2_and_3.yaml` to `08i_rc381_final_selection.yaml` and
`08k_rc381_cpp_limits.yaml` under the `form:` key; the record has no fields, because every figure
the form reads is a starting amount of the return; and the return reads the six results it gives
through the totals of `08j_rc381_totals.yaml`. The entries of the form are listed in
`manifest_families/rc381_cpp_qpp.py`.
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
from tax_engine.jurisdictions.ca.catalog import RC381_INSTANCES
from tests.jurisdictions.ca_on.manifest_families import rc381_cpp_qpp
from tests.jurisdictions.ca_on.manifest_support import instance_fields, required_entries

CA_ON = JurisdictionCode("CA-ON")
PARTS = Path(tax_engine.jurisdictions.ca_on.__file__).parent / "manifests" / "v1"
FORM_PARTS = (
    "08a_rc381_part_2_and_3.yaml",
    "08b_rc381_part_3_qpp_and_totals.yaml",
    "08c_rc381_part_3a_and_3b.yaml",
    "08d_rc381_part_4_lines_1_to_27.yaml",
    "08e_rc381_part_4_lines_31_to_56.yaml",
    "08f_rc381_part_4_lines_59_to_91.yaml",
    "08g_rc381_part_4_lines_92_to_110.yaml",
    "08h_rc381_part_4_lines_111_to_129.yaml",
    "08i_rc381_final_selection.yaml",
    "08k_rc381_cpp_limits.yaml",
)
# The steps the form copies from the return, which the return keeps: Part 2 lines C to F, Part 4
# line 1 and the net self-employment income it adds with the three totals it reads.
COPIED_PRODUCTS = {
    "ca/cpp_maximum_pensionable_earnings",
    "ca/cpp_second_additional_earnings_maximum",
    "ca/cpp_additional_maximum_pensionable_earnings",
    "ca/cpp_basic_exemption",
    "ca/pensionable_net_self_employment_earnings",
    "ca/business_income",
    "ca/professional_income",
    "ca/commission_income",
    "ca/farming_income",
    "ca/fishing_income",
    "ca/net_self_employment_income",
}


def manifest() -> Manifest:
    (only,) = (
        YamlJurisdictionSource(tax_engine.registrations.JURISDICTIONS.roots())
        .get_jurisdiction(CA_ON)
        .manifests
    )
    return only


def form(name: str) -> Form:
    (found,) = (found for found in manifest().forms if found.name == name)
    return found


def composed() -> FormComposition:
    return build_tax_computation().compose(CA_ON, 2025).form("ca/rc381")


# --- the parts and the form ----------------------------------------------------------------------


def test_the_first_part_declares_the_form_with_its_instances_limits_and_exports() -> None:
    declared = yaml.safe_load((PARTS / FORM_PARTS[0]).read_text())["form"]

    assert declared == {
        "name": "ca/rc381",
        "required": True,
        "fields": required_entries(instance_fields("ca/rc381")),
        "instances": "ca/rc381_instances",
        "max_instances": 1,
        "min_instances": 0,
        "exclusive_group": "ca/cpp_calculation",
        "exports": list(rc381_cpp_qpp.FORM_EXPORTS),
    }


def test_every_other_part_of_the_form_names_it_and_declares_nothing_else() -> None:
    for name in FORM_PARTS[1:]:
        assert yaml.safe_load((PARTS / name).read_text())["form"] == {"name": "ca/rc381"}, name


def test_the_manifest_has_the_form_rc381_beside_the_other_forms() -> None:
    found = form("ca/rc381")

    assert found.instances == "ca/rc381_instances"
    assert found.exports == rc381_cpp_qpp.FORM_EXPORTS
    assert (found.min_instances, found.max_instances, found.exclusive_group) == (
        0,
        1,
        "ca/cpp_calculation",
    )


def test_schedule_8_and_form_rc381_are_the_two_forms_of_the_exclusive_group() -> None:
    members = {
        found.name for found in manifest().forms if found.exclusive_group == "ca/cpp_calculation"
    }

    assert members == {"ca/schedule_8", "ca/rc381"}


def test_the_form_holds_the_201_rc381_selections() -> None:
    found = form("ca/rc381")

    assert len(found.capabilities) == 201
    assert set(found.capabilities) == rc381_cpp_qpp.FORM_STEPS


def test_the_return_keeps_only_the_copied_steps_of_the_form_and_totals_the_rest() -> None:
    (default, *_) = manifest().forms
    selected = set(default.capabilities)

    assert rc381_cpp_qpp.STEPS <= selected
    shared = selected & rc381_cpp_qpp.FORM_STEPS
    assert {output for step in shared for output in step.produces.values()} == COPIED_PRODUCTS
    assert len(shared) == len(COPIED_PRODUCTS)


def test_each_part_is_not_over_30_kb() -> None:
    for name in (*FORM_PARTS, "08j_rc381_totals.yaml"):
        assert (PARTS / name).stat().st_size <= 30 * 1024, name


def test_the_return_form_holds_no_rc381_line_but_the_six_totals() -> None:
    (default, *_) = manifest().forms
    produced = {output for step in default.capabilities for output in step.produces.values()}

    assert {kind for kind in produced if "rc381" in str(kind)} == set(rc381_cpp_qpp.FORM_EXPORTS)


# --- the instances input -------------------------------------------------------------------------


def test_the_instances_are_an_input_of_the_manifest_with_the_filers_entries_the_form_reads() -> (
    None
):
    assert rc381_cpp_qpp.INPUTS <= manifest().inputs.keys()


def test_the_instances_kind_is_a_record_list_with_no_fields() -> None:
    assert isinstance(RC381_INSTANCES, RecordListKind)
    assert RC381_INSTANCES.identifier == "ca/rc381_instances"
    assert RC381_INSTANCES.fields == ()


def test_the_catalog_registers_the_instances_kind_beside_the_other_record_lists() -> None:
    build_tax_computation()

    assert ArtifactRegistry.shared().kind("ca/rc381_instances") is RC381_INSTANCES


# --- the outputs and the node --------------------------------------------------------------------


def test_the_return_still_declares_the_six_results_as_outputs_and_no_form_kind() -> None:
    (default, *_) = manifest().forms
    exports = set(default.exports)

    assert rc381_cpp_qpp.OUTPUTS <= exports
    assert not {export for export in exports if "." in export}


def test_the_form_set_runs_the_form_on_the_instances_and_derives_its_six_kinds() -> None:
    found = composed()

    assert found.instances == RC381_INSTANCES
    assert {kind.identifier for kind in found.imports} == {
        "ca/t1139_return.t1139_business_income_on_return",
        "ca/t1139_return.t1139_professional_income_on_return",
        "ca/t1139_return.t1139_commission_income_on_return",
        "ca/t1139_return.t1139_farming_income_on_return",
        "ca/t1139_return.t1139_fishing_income_on_return",
    }
    assert [kind.identifier for kind in found.derived] == [
        f"ca/rc381.{export.removeprefix('ca/')}" for export in rc381_cpp_qpp.FORM_EXPORTS
    ]
    assert (found.min_instances, found.max_instances) == (0, 1)


def test_the_selections_inside_the_form_are_wired_as_they_were_on_the_return() -> None:
    inner = {
        (type(capability), capability.consumes, capability.produces)
        for capability in composed().composition.order
    }

    assert inner == rc381_cpp_qpp.FORM_WIRING
