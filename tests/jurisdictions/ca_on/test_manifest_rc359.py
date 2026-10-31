"""Form RC359 in the CA-ON manifest: one copy for each employer, and the line 9 total on T1 41800.

RC359 is the form `ca/rc359`, one instance for each employer (`ca/rc359_employers`; any number, none
included). Its selections live in the part `11a_rc359.yaml` under the `form:` key; the form exports
its line 7 and line 9, and the return totals line 9 over the copies as `ca/rc359_tax_total`, the
last part of the `ca/special_taxes` sum of T1 line 41800 (the sum is in `11_net_tax.yaml`). The
entries of the form are listed in `manifest_families/rc359.py`.
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
from tax_engine.domain.capabilities.record_total import RecordTotal
from tax_engine.domain.capabilities.sum import Sum
from tax_engine.domain.form import FormComposition
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import Form, Manifest
from tax_engine.domain.record_list import RecordListKind
from tax_engine.jurisdictions.ca.catalog import (
    RC359_EMPLOYERS,
    RC359_TAX_ON_EXCESS_EPSP,
    RC359_TAX_TOTAL,
    SPECIAL_TAXES,
)
from tests.jurisdictions.ca_on.manifest_families import rc359
from tests.jurisdictions.ca_on.manifest_support import (
    inputs_text,
    instance_fields,
    lists,
    required_entries,
)

CA_ON = JurisdictionCode("CA-ON")
PART = Path(tax_engine.jurisdictions.ca_on.__file__).parent / "manifests" / "v1" / "11a_rc359.yaml"
NET_TAX_PART = PART.with_name("11_net_tax.yaml")
INPUTS_PART = PART.with_name("01_inputs.yaml")


def manifest() -> Manifest:
    (only,) = (
        YamlJurisdictionSource(tax_engine.registrations.JURISDICTIONS.roots())
        .get_jurisdiction(CA_ON)
        .manifests
    )
    return only


def form() -> Form:
    (found,) = (each for each in manifest().forms if each.name == "ca/rc359")
    return found


def composed() -> FormComposition:
    return build_tax_computation().compose(CA_ON, 2025).form("ca/rc359")


# --- the part and the form -----------------------------------------------------------------------


def test_the_rc359_part_declares_the_form_ca_rc359_with_its_instances_and_exports() -> None:
    declared = yaml.safe_load(PART.read_text())["form"]

    assert declared == {
        "name": "ca/rc359",
        "required": True,
        "fields": required_entries(instance_fields("ca/rc359")),
        "instances": "ca/rc359_employers",
        "exports": list(rc359.FORM_EXPORTS),
    }


def test_the_manifest_has_the_form_rc359_with_its_instances_and_exports() -> None:
    found = form()

    assert found.name == "ca/rc359"
    assert found.instances == "ca/rc359_employers"
    assert found.exports == rc359.FORM_EXPORTS


def test_the_form_holds_the_five_rc359_selections_for_lines_4_to_9() -> None:
    # Line 4 (subtract), lines 5 and 6 (apply the rate), line 7 (not below zero), line 8 (the
    # province's printed rate) and line 9 (the percentage of line 7): one selection for each line
    # that computes.
    found = form()

    assert len(found.capabilities) == 5
    assert set(found.capabilities) == rc359.FORM_STEPS


def test_the_return_selects_the_line_9_total_and_none_of_the_form_steps() -> None:
    (default, *_) = manifest().forms
    selected = set(default.capabilities)

    assert rc359.STEPS <= selected
    assert not selected & rc359.FORM_STEPS


def test_the_return_reads_line_9_of_each_copy_through_the_record_total() -> None:
    (step,) = [each for each in rc359.STEPS]

    assert step.name == "core/record_total"
    assert step.consumes == {"records": "ca/rc359.rc359_tax_on_excess_epsp"}
    assert step.produces == {"output": "ca/rc359_tax_total"}


def test_the_special_taxes_sum_takes_the_rc359_total_as_its_last_part() -> None:
    (special,) = [
        each
        for each in manifest().forms[0].capabilities
        if each.produces == {"output": "ca/special_taxes"}
    ]

    assert special.name == "core/sum"
    assert tuple(special.consumes["parts"]) == (
        "ca/resp_aips_additional_tax",
        "ca/rl_10_labour_sponsored_fund_amount",
        "ca/rc359_tax_total",
    )
    assert "ca/rc359_tax_total" in NET_TAX_PART.read_text()


def test_the_rc359_part_is_not_over_30_kb_and_the_other_parts_hold_no_rc359_input() -> None:
    assert PART.stat().st_size <= 30 * 1024
    text = inputs_text()
    for identifier in rc359.FORM_INPUTS:
        assert not lists(text, identifier), identifier


# --- the instances input -------------------------------------------------------------------------


def test_the_employers_are_the_one_input_of_the_manifest_in_place_of_the_rc359_inputs() -> None:
    inputs = manifest().inputs.keys()

    assert rc359.INPUTS <= inputs
    assert inputs.isdisjoint(rc359.FORM_INPUTS)


def test_the_employers_kind_is_a_record_list_of_the_four_form_inputs_in_order() -> None:
    assert isinstance(RC359_EMPLOYERS, RecordListKind)
    assert RC359_EMPLOYERS.identifier == "ca/rc359_employers"
    assert frozenset(field.identifier for field in RC359_EMPLOYERS.fields) == rc359.FORM_INPUTS
    assert len(RC359_EMPLOYERS.fields) == len(rc359.FORM_INPUTS) == 4


def test_the_catalog_registers_the_employers_kind_beside_the_other_record_lists() -> None:
    build_tax_computation()

    assert ArtifactRegistry.shared().kind("ca/rc359_employers") is RC359_EMPLOYERS


# --- the outputs and the node --------------------------------------------------------------------


def test_the_return_declares_no_output_for_the_form_exports() -> None:
    (default, *_) = manifest().forms
    exports = set(default.exports)

    assert rc359.OUTPUTS <= exports
    assert not {"ca/rc359_excess_epsp_amount", "ca/rc359_tax_on_excess_epsp"} & exports
    assert not {export for export in exports if "." in export}


def test_the_form_set_runs_the_form_on_the_employers_and_derives_its_two_export_records() -> None:
    found = composed()

    assert found.instances == RC359_EMPLOYERS
    assert found.imports == frozenset()
    assert found.derived == (
        rc359.EXCESS_EPSP_AMOUNT_PER_EMPLOYER,
        rc359.TAX_ON_EXCESS_EPSP_PER_EMPLOYER,
    )


def test_the_line_9_record_list_is_the_export_of_the_form_as_its_one_decimal_field() -> None:
    assert rc359.TAX_ON_EXCESS_EPSP_PER_EMPLOYER.identifier == "ca/rc359.rc359_tax_on_excess_epsp"
    assert rc359.TAX_ON_EXCESS_EPSP_PER_EMPLOYER.fields == (RC359_TAX_ON_EXCESS_EPSP,)


def test_the_return_total_is_a_record_total_over_the_copies_and_the_sum_is_the_special_taxes() -> (
    None
):
    order = build_tax_computation().compose(CA_ON, 2025).form("ca-on/return").composition.order
    totals = [each for each in order if isinstance(each, RecordTotal)]
    sums = [each for each in order if isinstance(each, Sum) and SPECIAL_TAXES in each.produces]

    assert [each.produces for each in totals if RC359_TAX_TOTAL in each.produces]
    assert len(sums) == 1
    assert RC359_TAX_TOTAL in sums[0].consumes


def test_the_selections_inside_the_form_are_wired_as_declared() -> None:
    inner = {
        (type(capability), capability.consumes, capability.produces)
        for capability in composed().composition.order
    }

    assert inner == rc359.FORM_WIRING
