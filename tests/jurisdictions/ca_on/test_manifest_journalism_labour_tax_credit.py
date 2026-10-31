"""The Canadian journalism labour tax credit in the CA-ON manifest: entered once, on the T2125
statements, and totalled onto T1 line 162 (47555).

The credit is box 236 of the T5013 slip, and the T1 guide says to include that amount in business
income in the same year. So the statement's amount 5B is the one entry of the fact: the form
`ca/t2125` exports it as the record list `ca/t2125.business_journalism_labour_tax_credit`, and the
return totals that list with `core/record_total` (in `14_refund.yaml`) into
`ca/journalism_labour_tax_credit`, placed before the line 48200 sum. The return takes no input for
line 162, and a return with no statement has a credit of 0. The entries are listed in
`manifest_families/t2125.py` (the export and the total).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

import tax_engine.jurisdictions.ca_on

# lists the packages; build_tax_computation registers their catalogs
import tax_engine.registrations
from tax_engine import build_tax_computation
from tax_engine.adapters.outbound.yaml_jurisdictions import YamlJurisdictionSource
from tax_engine.domain.capabilities.record_total import RecordTotal
from tax_engine.domain.form import FormComposition
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import Manifest
from tests.jurisdictions.ca_on.manifest_families import t2125
from tests.jurisdictions.ca_on.manifest_support import all_input_names

CA_ON = JurisdictionCode("CA-ON")
MANIFESTS = Path(tax_engine.jurisdictions.ca_on.__file__).parent / "manifests" / "v1"
T2125_PART = MANIFESTS / "03b_t2125.yaml"
REFUND_PART = MANIFESTS / "14_refund.yaml"
INPUTS_PART = MANIFESTS / "01_inputs.yaml"
STATEMENT_AMOUNT = "ca/business_journalism_labour_tax_credit"
STATEMENT_RECORDS = "ca/t2125.business_journalism_labour_tax_credit"
CREDIT = "ca/journalism_labour_tax_credit"
TOTAL_CREDITS = "ca/total_credits"


def manifest() -> Manifest:
    (only,) = (
        YamlJurisdictionSource(tax_engine.registrations.JURISDICTIONS.roots())
        .get_jurisdiction(CA_ON)
        .manifests
    )
    return only


def composed_form() -> FormComposition:
    return build_tax_computation().compose(CA_ON, 2025).form("ca/t2125")


def composed_return() -> FormComposition:
    return build_tax_computation().compose(CA_ON, 2025).form("ca-on/return")


def part_capabilities(path: Path) -> list[dict[str, Any]]:
    capabilities: list[dict[str, Any]] = yaml.safe_load(path.read_text())["capabilities"]
    return capabilities


# --- the form T2125 exports amount 5B ----------------------------------------------------------


def test_the_t2125_part_exports_amount_5b_as_the_statements_record_of_the_fact() -> None:
    declared = yaml.safe_load(T2125_PART.read_text())["form"]["exports"]

    assert STATEMENT_AMOUNT in declared
    assert declared == list(t2125.FORM_EXPORTS)


def test_the_t2125_manifest_form_exports_amount_5b() -> None:
    (found,) = (each for each in manifest().forms if each.name == "ca/t2125")

    assert STATEMENT_AMOUNT in found.exports


def test_the_form_t2125_derives_the_record_kind_of_amount_5b() -> None:
    derived = {kind.identifier for kind in composed_form().derived}

    assert STATEMENT_RECORDS in derived


def test_amount_5b_stays_an_input_of_each_statement_as_the_form_asks_it() -> None:
    # The entry is once, on the statement; amount 5C still adds it, so the guard is the input.
    assert STATEMENT_AMOUNT in t2125.FORM_INPUTS


# --- the return's line 162 is a total of the statements, not an input ---------------------------


def test_the_return_takes_no_input_for_the_line_162_credit() -> None:
    assert CREDIT not in manifest().inputs.keys()
    assert CREDIT not in all_input_names()


def test_the_return_totals_the_statements_into_the_credit_by_record_total_in_14_refund() -> None:
    (default, *_) = manifest().forms
    totals = [each for each in default.capabilities if each.produces == {"output": CREDIT}]

    assert len(totals) == 1, totals
    (total,) = totals
    assert total.name == "core/record_total"
    assert total.consumes == {"records": STATEMENT_RECORDS}


def test_the_credit_total_is_declared_in_the_refund_part_before_the_line_48200_sum() -> None:
    parts = part_capabilities(REFUND_PART)
    totals = [
        index for index, each in enumerate(parts) if each.get("produces") == {"output": CREDIT}
    ]
    sums = [
        index
        for index, each in enumerate(parts)
        if each.get("produces") == {"output": TOTAL_CREDITS}
    ]

    assert len(totals) == 1, totals
    assert parts[totals[0]]["name"] == "core/record_total"
    assert parts[totals[0]]["consumes"] == {"records": STATEMENT_RECORDS}
    assert len(sums) == 1, sums
    assert totals[0] < sums[0]


def test_the_return_reads_the_statements_export_through_a_record_total_wired_once() -> None:
    returned = composed_return()

    assert STATEMENT_RECORDS in {kind.identifier for kind in returned.imports}
    totals = [
        each
        for each in returned.composition.order
        if {kind.identifier for kind in each.produces} == {CREDIT}
    ]
    assert len(totals) == 1, totals
    (total,) = totals
    assert type(total) is RecordTotal
    assert {kind.identifier for kind in total.consumes} == {STATEMENT_RECORDS}
