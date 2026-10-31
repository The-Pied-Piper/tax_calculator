"""Form ca/farm_loss in the CA-ON manifest: the restricted farm loss, once for the return.

Guide T4002 "Restricted farm losses (partly deductible)" (pp. 95-96; confirmed from the PDF, no
.txt published) speaks of "your net farm loss for the year", so the form runs once for the return
(one instance, no instances list) on the net of all the T2042 statements' line 9946, with the
filer's yes or no (`ca/farm_not_main_source_of_income`) a manifest input asked once. It exports the
amount of T1 line 14100 "Net", which T1 and the copies of line 14100 (Schedule 8, Form RC381 and
Form T929) read in place of `ca/t2042.farming_income`. The yes or no is declared in
`01e_farm_loss_inputs.yaml`.
"""

from __future__ import annotations

from pathlib import Path

import yaml

import tax_engine.jurisdictions.ca_on
import tax_engine.registrations
from tax_engine import build_tax_computation
from tax_engine.adapters.outbound.yaml_jurisdictions import YamlJurisdictionSource
from tax_engine.domain.capabilities.credit_amount import CreditAmount
from tax_engine.domain.capabilities.lesser_of import LesserOf
from tax_engine.domain.capabilities.record_total import RecordTotal
from tax_engine.domain.capabilities.subtract import Subtract
from tax_engine.domain.capabilities.sum import Sum
from tax_engine.domain.capabilities.times_count import TimesCount
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import Form, Manifest
from tax_engine.jurisdictions.ca.capabilities.apply_percentage import ApplyPercentage
from tax_engine.jurisdictions.ca.capabilities.choose_by_sign import ChooseBySign
from tax_engine.jurisdictions.ca.capabilities.positive_part_of_negation import (
    PositivePartOfNegation,
)
from tax_engine.jurisdictions.ca.capabilities.yes_or_no_count import YesOrNoCount
from tax_engine.jurisdictions.ca.catalog import (
    FARM_LOSS_DEDUCTIBLE,
    FARM_NET_INCOME_LINE_9946,
    FARM_NET_LOSS,
    FARM_NET_LOSS_LESS_BASE_AMOUNT,
    FARM_NET_LOSS_LESS_FULL_THRESHOLD,
    FARM_NOT_MAIN_SOURCE_OF_INCOME,
    FARM_NOT_MAIN_SOURCE_OF_INCOME_CHECKED,
    FARM_RESTRICTED_LOSS,
    FARM_RESTRICTED_LOSS_ADDED_BACK,
    FARM_RESTRICTED_LOSS_AMOUNT_B,
    FARM_RESTRICTED_LOSS_ANNUAL_MAXIMUM,
    FARM_RESTRICTED_LOSS_BASE_AMOUNT,
    FARM_RESTRICTED_LOSS_FULL_THRESHOLD,
    FARM_RESTRICTED_LOSS_HALF_OF_EXCESS,
    FARM_RESTRICTED_LOSS_LESSER_OF_A_AND_B,
    FARM_RESTRICTED_LOSS_PERCENTAGE,
    FARMING_INCOME,
)
from tests.jurisdictions.ca_on.end_to_end.support import run_a
from tests.jurisdictions.ca_on.manifest_support import inputs_text, required_entries

CA_ON = JurisdictionCode("CA-ON")
V1 = Path(tax_engine.jurisdictions.ca_on.__file__).parent / "manifests" / "v1"
PART = V1 / "03s_t2042_restricted_farm_loss.yaml"
INPUTS_PART = V1 / "01e_farm_loss_inputs.yaml"
# The parts that read line 14100 as the net of the statements with the restricted loss added back.
READERS = (
    "03_income.yaml",
    "05h_schedule_8_contributions.yaml",
    "05l_t929_copies_1.yaml",
    "08k_rc381_cpp_limits.yaml",
)
# The readers that count a loss as 0 and so are not changed by the restriction.
POSITIVE_READERS = ("05k_t929.yaml", "05k_t1_m.yaml", "13_refundable_credits.yaml")


def manifest() -> Manifest:
    (only,) = (
        YamlJurisdictionSource(tax_engine.registrations.JURISDICTIONS.roots())
        .get_jurisdiction(CA_ON)
        .manifests
    )
    return only


def form() -> Form:
    (found,) = (each for each in manifest().forms if each.name == "ca/farm_loss")
    return found


def test_the_form_runs_once_for_the_return_and_exports_line_14100() -> None:
    declared = yaml.safe_load(PART.read_text())

    assert set(declared) == {"form", "capabilities"}
    assert declared["form"] == {
        "name": "ca/farm_loss",
        "required": True,
        "exports": ["ca/farming_income"],
    }
    assert form().instances is None
    assert form().exports == ("ca/farming_income",)


def test_the_form_holds_the_16_steps_of_the_net_of_the_statements_and_the_restriction() -> None:
    declared = yaml.safe_load(PART.read_text())

    assert len(declared["capabilities"]) == len(form().capabilities) == 16
    assert declared["capabilities"][-1]["produces"] == {"output": "ca/farming_income"}


def test_the_answer_is_a_manifest_input_declared_in_its_own_part() -> None:
    assert yaml.safe_load(INPUTS_PART.read_text()) == {
        "inputs": required_entries(
            [
                "ca/farm_not_main_source_of_income",
                "ca/restricted_farm_losses_of_other_years",
                "ca/unapplied_restricted_farm_loss_taxes_and_interest",
            ]
        )
    }
    assert "ca/farm_not_main_source_of_income" in manifest().inputs.keys()
    assert "ca/farm_not_main_source_of_income" not in inputs_text()
    assert "ca/unapplied_restricted_farm_loss_taxes_and_interest" in manifest().inputs.keys()
    assert "ca/unapplied_restricted_farm_loss_taxes_and_interest" not in inputs_text()


def test_the_steps_of_the_part() -> None:
    declared = yaml.safe_load(PART.read_text())

    assert declared["capabilities"] == [
        {
            "name": "core/record_total",
            "consumes": {"records": "ca/t2042.farming_income"},
            "produces": {"output": "ca/farm_net_income_line_9946"},
        },
        {
            "name": "ca/yes_or_no_count",
            "consumes": {"count": "ca/farm_not_main_source_of_income"},
            "produces": {"output": "ca/farm_not_main_source_of_income_checked"},
        },
        {
            "name": "ca/positive_part_of_negation",
            "consumes": {"amount": "ca/farm_net_income_line_9946"},
            "produces": {"output": "ca/farm_net_loss"},
        },
        {
            "name": "core/credit_amount",
            "params": {"amount": "ca/farm_restricted_loss_base_amount"},
            "produces": {"output": "ca/farm_restricted_loss_base_amount"},
        },
        {
            "name": "core/credit_amount",
            "params": {"amount": "ca/farm_restricted_loss_full_threshold"},
            "produces": {"output": "ca/farm_restricted_loss_full_threshold"},
        },
        {
            "name": "core/credit_amount",
            "params": {"amount": "ca/farm_restricted_loss_annual_maximum"},
            "produces": {"output": "ca/farm_restricted_loss_annual_maximum"},
        },
        {
            "name": "core/credit_amount",
            "params": {"amount": "ca/farm_restricted_loss_percentage"},
            "produces": {"output": "ca/farm_restricted_loss_percentage"},
        },
        {
            "name": "core/subtract",
            "consumes": {
                "amount": "ca/farm_net_loss",
                "less": "ca/farm_restricted_loss_base_amount",
            },
            "produces": {"output": "ca/farm_net_loss_less_base_amount"},
        },
        {
            "name": "ca/apply_percentage",
            "params": {"rounding": "ca/farm_restricted_loss_rounding"},
            "consumes": {
                "amount": "ca/farm_net_loss_less_base_amount",
                "percentage": "ca/farm_restricted_loss_percentage",
            },
            "produces": {"output": "ca/farm_restricted_loss_half_of_excess"},
        },
        {
            "name": "core/sum",
            "consumes": {
                "parts": [
                    "ca/farm_restricted_loss_base_amount",
                    "ca/farm_restricted_loss_half_of_excess",
                ]
            },
            "produces": {"output": "ca/farm_restricted_loss_amount_b"},
        },
        {
            "name": "core/lesser_of",
            "consumes": {"amounts": ["ca/farm_net_loss", "ca/farm_restricted_loss_amount_b"]},
            "produces": {"output": "ca/farm_restricted_loss_lesser_of_a_and_b"},
        },
        {
            "name": "core/subtract",
            "consumes": {
                "amount": "ca/farm_net_loss",
                "less": "ca/farm_restricted_loss_full_threshold",
            },
            "produces": {"output": "ca/farm_net_loss_less_full_threshold"},
        },
        {
            "name": "ca/choose_by_sign",
            "consumes": {
                "sign": "ca/farm_net_loss_less_full_threshold",
                "when_positive": [],
                "when_zero": [],
                "when_negative": ["ca/farm_restricted_loss_lesser_of_a_and_b"],
                "when_non_positive": [],
                "when_non_negative": ["ca/farm_restricted_loss_annual_maximum"],
            },
            "produces": {"output": "ca/farm_loss_deductible"},
        },
        {
            "name": "core/subtract",
            "consumes": {"amount": "ca/farm_net_loss", "less": "ca/farm_loss_deductible"},
            "produces": {"output": "ca/farm_restricted_loss"},
        },
        {
            "name": "core/times_count",
            "consumes": {
                "amount": "ca/farm_restricted_loss",
                "count": "ca/farm_not_main_source_of_income_checked",
            },
            "produces": {"output": "ca/farm_restricted_loss_added_back"},
        },
        {
            "name": "core/sum",
            "consumes": {
                "parts": ["ca/farm_net_income_line_9946", "ca/farm_restricted_loss_added_back"]
            },
            "produces": {"output": "ca/farming_income"},
        },
    ]


def test_the_return_and_the_copies_read_the_form_export_not_the_statements() -> None:
    for name in READERS:
        text = (V1 / name).read_text()

        assert "records: ca/t1139_return.t1139_farming_income_on_return" in text, name
        assert "records: ca/t2042.farming_income" not in text, name


def test_the_readers_that_count_a_loss_as_zero_still_read_the_statements() -> None:
    # They read the statements through the profit export of the summary form of Form T1139
    # (ca/t1139_return), which carries each statement's line 9946 with a loss counted as 0, not
    # through the restricted farm loss.
    for name in POSITIVE_READERS:
        text = (V1 / name).read_text()

        assert "records: ca/t1139_return.t1139_farming_profit_on_return" in text, name
        assert "records: ca/t2042.farming_income" not in text, name
        assert "ca/farm_loss." not in text, name


def test_the_t2042_form_exports_plain_line_9946_as_farming_income() -> None:
    (t2042,) = (each for each in manifest().forms if each.name == "ca/t2042")

    assert "ca/farming_income" in t2042.exports
    assert not any("restricted" in identifier for identifier in t2042.exports)
    assert (
        "ca/farm_not_main_source_of_income"
        not in (V1 / "03c_t2042.yaml").read_text() + (V1 / "03c_t2042_2.yaml").read_text()
    )


def test_each_capability_of_the_form_runs_after_what_it_consumes() -> None:
    order = build_tax_computation().compose(CA_ON, 2025).form("ca/farm_loss").composition.order
    assert len(order) == 16
    position = {kind: i for i, capability in enumerate(order) for kind in capability.produces}
    # Guide T4002 "Restricted farm losses (partly deductible)": the net of the statements, then
    # the net farm loss before amount B and the lesser of A and B, those before the deductible
    # loss, which is before the restricted loss, its add-back and line 14100.
    assert (
        position[FARM_NET_INCOME_LINE_9946]
        < position[FARM_NET_LOSS]
        < position[FARM_NET_LOSS_LESS_BASE_AMOUNT]
        < position[FARM_RESTRICTED_LOSS_HALF_OF_EXCESS]
        < position[FARM_RESTRICTED_LOSS_AMOUNT_B]
        < position[FARM_RESTRICTED_LOSS_LESSER_OF_A_AND_B]
        < position[FARM_LOSS_DEDUCTIBLE]
        < position[FARM_RESTRICTED_LOSS]
        < position[FARM_RESTRICTED_LOSS_ADDED_BACK]
        < position[FARMING_INCOME]
    )
    assert position[FARM_NET_LOSS_LESS_FULL_THRESHOLD] < position[FARM_LOSS_DEDUCTIBLE]
    assert (
        position[FARM_NOT_MAIN_SOURCE_OF_INCOME_CHECKED] < position[FARM_RESTRICTED_LOSS_ADDED_BACK]
    )


def test_each_amount_of_the_form_is_produced_by_its_capability() -> None:
    worksheet = run_a()["ca/farm_loss"][0]

    assert worksheet.producer_of(FARM_NOT_MAIN_SOURCE_OF_INCOME) is None
    assert isinstance(worksheet.producer_of(FARM_NET_INCOME_LINE_9946), RecordTotal)
    assert isinstance(worksheet.producer_of(FARM_NOT_MAIN_SOURCE_OF_INCOME_CHECKED), YesOrNoCount)
    assert isinstance(worksheet.producer_of(FARM_NET_LOSS), PositivePartOfNegation)
    for figure in (
        FARM_RESTRICTED_LOSS_BASE_AMOUNT,
        FARM_RESTRICTED_LOSS_FULL_THRESHOLD,
        FARM_RESTRICTED_LOSS_ANNUAL_MAXIMUM,
        FARM_RESTRICTED_LOSS_PERCENTAGE,
    ):
        assert isinstance(worksheet.producer_of(figure), CreditAmount), figure.identifier
    assert isinstance(worksheet.producer_of(FARM_NET_LOSS_LESS_BASE_AMOUNT), Subtract)
    assert isinstance(worksheet.producer_of(FARM_RESTRICTED_LOSS_HALF_OF_EXCESS), ApplyPercentage)
    assert isinstance(worksheet.producer_of(FARM_RESTRICTED_LOSS_AMOUNT_B), Sum)
    assert isinstance(worksheet.producer_of(FARM_RESTRICTED_LOSS_LESSER_OF_A_AND_B), LesserOf)
    assert isinstance(worksheet.producer_of(FARM_NET_LOSS_LESS_FULL_THRESHOLD), Subtract)
    assert isinstance(worksheet.producer_of(FARM_LOSS_DEDUCTIBLE), ChooseBySign)
    assert isinstance(worksheet.producer_of(FARM_RESTRICTED_LOSS), Subtract)
    assert isinstance(worksheet.producer_of(FARM_RESTRICTED_LOSS_ADDED_BACK), TimesCount)
    assert isinstance(worksheet.producer_of(FARMING_INCOME), Sum)


def test_return_a_gives_a_farm_loss_form_of_0() -> None:
    # Return A has no farm statement and gave no answer (0): nothing is restricted, 0 on line 14100.
    worksheet = run_a()["ca/farm_loss"][0]

    assert worksheet.get(FARMING_INCOME).value == 0
    assert worksheet.get(FARM_RESTRICTED_LOSS).value == 0
