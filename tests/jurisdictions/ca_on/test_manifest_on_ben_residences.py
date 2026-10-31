"""Form ON-BEN Part B in the CA-ON manifest: the form `ca-on/on_ben_residences`, one run for each
row of the table (any number), and what the return reads of it. The entries are listed in
`manifest_families/on_ben_residences.py`."""

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
from tax_engine.domain.record_list import RecordListKind
from tax_engine.jurisdictions.ca_on.catalog import ON_BEN_RESIDENCES
from tests.jurisdictions.ca_on.manifest_families import on_ben_residences
from tests.jurisdictions.ca_on.manifest_support import instance_fields, required_entries

CA_ON = JurisdictionCode("CA-ON")
FORM = "ca-on/on_ben_residences"
ROWS = "ca-on/on_ben_residence_rows"
PART = (
    Path(tax_engine.jurisdictions.ca_on.__file__).parent
    / "manifests"
    / "v1"
    / "28a_on_ben_residences.yaml"
)


def manifest() -> Manifest:
    (only,) = (
        YamlJurisdictionSource(tax_engine.registrations.JURISDICTIONS.roots())
        .get_jurisdiction(CA_ON)
        .manifests
    )
    return only


def form() -> Form:
    (found,) = (each for each in manifest().forms if each.name == FORM)
    return found


def composed() -> FormComposition:
    return build_tax_computation().compose(CA_ON, 2025).form(FORM)


def test_the_part_declares_the_form_with_its_instances_and_exports() -> None:
    declared = yaml.safe_load(PART.read_text())["form"]

    assert declared == {
        "name": FORM,
        "required": True,
        "fields": required_entries(instance_fields(FORM)),
        "instances": ROWS,
        "exports": list(on_ben_residences.FORM_EXPORTS),
    }


def test_the_manifest_has_the_form_with_the_row_list_as_instances_and_no_row_limit() -> None:
    found = form()

    assert found.instances == ROWS
    assert found.max_instances is None
    assert found.exports == on_ben_residences.FORM_EXPORTS
    assert set(found.capabilities) == on_ben_residences.FORM_STEPS


def test_the_rows_are_the_manifest_input_in_place_of_the_row_fields() -> None:
    inputs = manifest().inputs.keys()

    assert on_ben_residences.INPUTS <= inputs
    assert inputs.isdisjoint(on_ben_residences.FORM_INPUTS)


def test_the_rows_kind_is_a_record_list_of_the_three_figure_columns() -> None:
    assert isinstance(ON_BEN_RESIDENCES, RecordListKind)
    assert ON_BEN_RESIDENCES.identifier == ROWS
    assert (
        frozenset(f.identifier for f in ON_BEN_RESIDENCES.fields) == on_ben_residences.FORM_INPUTS
    )


def test_the_form_runs_once_for_each_row_and_derives_a_kind_for_each_export() -> None:
    found = composed()

    assert found.instances == ON_BEN_RESIDENCES
    assert tuple(kind.identifier for kind in found.derived) == tuple(
        f"{FORM}.{export.split('/')[1]}" for export in on_ben_residences.FORM_EXPORTS
    )


def test_the_return_reads_none_of_the_exports_so_the_amount_and_tick_are_unread_lines() -> None:
    (default, *_) = manifest().forms

    assert not {export for export in default.exports if export.startswith(FORM)}


def test_the_composed_form_has_the_wiring_of_the_family() -> None:
    wiring = {
        (type(capability), capability.consumes, capability.produces)
        for capability in composed().composition.order
    }

    assert on_ben_residences.FORM_WIRING <= wiring


def test_the_return_selects_none_of_the_forms_steps() -> None:
    (default, *_) = manifest().forms

    assert set(default.capabilities).isdisjoint(on_ben_residences.FORM_STEPS)
