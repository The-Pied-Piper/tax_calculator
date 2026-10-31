"""Form T1436 lines 1 to 7 (the capital gains deductions claimed) in the CA-ON manifest.

Form T1436 (Capital Gains Worksheet), "Line 21700 - Allowable business investment loss", lines 1
to 6 are each the amount entered for an earlier year times the figure the line prints; line 2 and
line 3 also read the Schedule 3 lines 543 and 544 the filer enters (in `01d_t1436_inputs.yaml`);
line 7 adds the six lines after their multipliers. The steps are in
`05o_t1436_lines_1_to_7.yaml` for the return, and the same steps are copied into the form
`ca/t929` (`05p_t1436_lines_1_to_7_t929.yaml`, with the credit of the line 5 ratio's "1" copied
too, as the form has no copy of it) and into the form
`ca/t2048` (`06a_t1436_lines_1_to_7_t2048.yaml`). The line 7 sum leaves the three parts that held it
(`05_deductions.yaml`, `05m_t929_copies_2.yaml` and `06a_capital_gains_deduction_qbt_copies.yaml`).
The entries are listed in `manifest_families/deductions.py`, `t929.py` and `t2048.py`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

import tax_engine.jurisdictions.ca_on
from tests.jurisdictions.ca_on.manifest_support import inputs_text, lists, required_entries

PARTS = Path(tax_engine.jurisdictions.ca_on.__file__).parent / "manifests" / "v1"
INPUTS_PART = PARTS / "01d_t1436_inputs.yaml"
RETURN_PART = PARTS / "05o_t1436_lines_1_to_7.yaml"
T929_PART = PARTS / "05p_t1436_lines_1_to_7_t929.yaml"
T2048_PART = PARTS / "06a_t1436_lines_1_to_7_t2048.yaml"
LINE_7_SUM_PARTS = (
    PARTS / "05_deductions.yaml",
    PARTS / "05m_t929_copies_2.yaml",
    PARTS / "06a_capital_gains_deduction_qbt_copies.yaml",
)
LAYOUT = re.compile(r"^\d\d[a-z]?_[a-z0-9_]+\.yaml$")
LINE_7 = "ca/capital_gains_deductions_claimed_1985_to_2024"
SCHEDULE_3_INPUTS = ("ca/schedule_3_line_543", "ca/schedule_3_line_544")
# The outputs of the steps in their order on the form: Schedule 3 lines 543 and 544, amount (a),
# lines 1 to 6 with the cap of line 3, and line 7.
OUTPUTS_IN_ORDER = (
    "ca/schedule_3_lines_543_and_544_total",
    "ca/capital_gains_deductions_1988_and_1989_amount_a",
    "ca/capital_gains_deductions_line_1",
    "ca/capital_gains_deductions_line_2",
    "ca/capital_gains_deductions_1988_and_1989_after_amount_a",
    "ca/capital_gains_deductions_1988_and_1989_limited",
    "ca/capital_gains_deductions_line_3",
    "ca/capital_gains_deductions_line_4",
    "ca/capital_gains_deductions_line_5",
    "ca/capital_gains_deductions_line_6",
    LINE_7,
)
MULTIPLIER_DATASETS = (
    "ca/t1436_line_1_multiplier",
    "ca/t1436_line_2_multiplier",
    "ca/t1436_line_3_multiplier",
    "ca/t1436_line_4_multiplier",
    "ca/t1436_line_6_multiplier",
)


def steps(path: Path) -> list[dict[str, Any]]:
    capabilities: list[dict[str, Any]] = yaml.safe_load(path.read_text())["capabilities"]
    return capabilities


def outputs(path: Path) -> list[str]:
    return [output for step in steps(path) for output in step["produces"].values()]


def test_the_inputs_part_declares_the_two_schedule_3_inputs_in_t1436_order() -> None:
    declared = yaml.safe_load(INPUTS_PART.read_text())

    assert declared == {"inputs": required_entries(SCHEDULE_3_INPUTS)}


def test_the_schedule_3_inputs_are_not_in_the_full_inputs_part() -> None:
    # 01_inputs.yaml is at its size cap: the two new inputs live in their own part.
    text = inputs_text()

    for identifier in SCHEDULE_3_INPUTS:
        assert not lists(text, identifier, indent="  "), identifier


def test_the_six_capital_gains_deductions_inputs_stay_in_the_full_inputs_part() -> None:
    text = inputs_text()

    for identifier in (
        "ca/capital_gains_deductions_1985_to_1987",
        "ca/capital_gains_deductions_1988_and_1989_other_than_eligible_capital_property",
        "ca/capital_gains_deductions_1988_and_1989_eligible_capital_property",
        "ca/capital_gains_deductions_1990_to_1999",
        "ca/capital_gains_deductions_2000",
        "ca/capital_gains_deductions_2001_to_2024",
    ):
        assert f"  - name: {identifier}\n" in text, identifier


def test_the_return_part_is_the_default_form_with_the_steps_of_lines_1_to_7() -> None:
    declared = yaml.safe_load(RETURN_PART.read_text())

    assert "form" not in declared
    assert outputs(RETURN_PART) == list(OUTPUTS_IN_ORDER)


def test_the_return_part_multiplies_by_the_printed_figures_as_datasets() -> None:
    by_output = {step["produces"]["output"]: step for step in steps(RETURN_PART)}

    for line, dataset in zip((1, 2, 3, 4, 6), MULTIPLIER_DATASETS, strict=True):
        step = by_output[f"ca/capital_gains_deductions_line_{line}"]
        assert step["name"] == "core/apply_fraction", line
        assert step["params"] == {"fraction": dataset}, line
    assert by_output["ca/capital_gains_deductions_line_5"]["name"] == "ca/apply_ratio_or_zero"
    assert by_output["ca/capital_gains_deductions_line_5"]["params"] == {
        "rounding": "ca/t1436_line_5_rounding"
    }
    assert by_output["ca/capital_gains_deductions_line_5"]["consumes"] == {
        "amount": "ca/capital_gains_deductions_2000",
        "numerator": "ca/net_capital_loss_numerator_one_2000",
        "denominator": "ca/t657_inclusion_rate_2000",
    }


def test_the_line_3_cap_is_a_lesser_of_the_difference_and_the_schedule_3_sum() -> None:
    by_output = {step["produces"]["output"]: step for step in steps(RETURN_PART)}

    assert by_output["ca/capital_gains_deductions_1988_and_1989_limited"] == {
        "name": "core/lesser_of",
        "consumes": {
            "amounts": [
                "ca/capital_gains_deductions_1988_and_1989_after_amount_a",
                "ca/schedule_3_lines_543_and_544_total",
            ]
        },
        "produces": {"output": "ca/capital_gains_deductions_1988_and_1989_limited"},
    }
    assert by_output["ca/capital_gains_deductions_1988_and_1989_after_amount_a"]["name"] == (
        "core/subtract"
    )


def test_amount_a_is_the_line_2_amount_less_the_schedule_3_sum_not_below_zero() -> None:
    by_output = {step["produces"]["output"]: step for step in steps(RETURN_PART)}

    assert by_output["ca/capital_gains_deductions_1988_and_1989_amount_a"]["name"] == (
        "core/subtract_not_below_zero"
    )
    assert by_output["ca/capital_gains_deductions_1988_and_1989_amount_a"]["consumes"] == {
        "amount": "ca/capital_gains_deductions_1988_and_1989_other_than_eligible_capital_property",
        "less": "ca/schedule_3_lines_543_and_544_total",
    }


def test_line_7_sums_the_six_lines_after_their_multipliers() -> None:
    by_output = {step["produces"]["output"]: step for step in steps(RETURN_PART)}

    assert by_output[LINE_7] == {
        "name": "core/sum",
        "consumes": {
            "parts": [
                "ca/capital_gains_deductions_line_1",
                "ca/capital_gains_deductions_line_2",
                "ca/capital_gains_deductions_line_3",
                "ca/capital_gains_deductions_line_4",
                "ca/capital_gains_deductions_line_5",
                "ca/capital_gains_deductions_line_6",
            ]
        },
        "produces": {"output": LINE_7},
    }


def test_the_line_7_sum_is_in_one_part_only_and_the_three_copies_lose_it() -> None:
    for path in LINE_7_SUM_PARTS:
        assert LINE_7 not in outputs(path), path.name
    assert outputs(RETURN_PART).count(LINE_7) == 1
    assert outputs(T929_PART).count(LINE_7) == 1
    assert outputs(T2048_PART).count(LINE_7) == 1


def test_the_form_parts_declare_their_form_and_the_return_part_none() -> None:
    assert yaml.safe_load(T929_PART.read_text())["form"] == {"name": "ca/t929"}
    assert yaml.safe_load(T2048_PART.read_text())["form"] == {"name": "ca/t2048"}


def test_the_t929_part_copies_the_return_steps_and_the_line_5_credit() -> None:
    # The form ca/t929 has no copy of the Chart A "1/(IR x 2)" credit, which line 5's ratio reads,
    # so its part carries that step first, then the same steps as the return part.
    copied = steps(T929_PART)

    assert copied[0] == {
        "name": "core/credit_amount",
        "params": {"amount": "ca/net_capital_loss_numerator_one_2000"},
        "produces": {"output": "ca/net_capital_loss_numerator_one_2000"},
    }
    assert copied[1:] == steps(RETURN_PART)


def test_the_t2048_part_copies_the_return_steps() -> None:
    # The form ca/t2048 has its own copy of the line 5 credit in its copies part, so this part
    # holds the same steps as the return part.
    assert steps(T2048_PART) == steps(RETURN_PART)


def test_the_t1436_parts_are_named_by_the_layout_rule_and_not_over_30_kb() -> None:
    for part in (INPUTS_PART, RETURN_PART, T929_PART, T2048_PART):
        assert LAYOUT.match(part.name), part.name
        assert part.stat().st_size <= 30 * 1024, part.name
