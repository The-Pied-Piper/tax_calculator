"""Which yes or no answers of the CA-ON manifest may be left blank, and what a blank does there.

`30_yes_or_no_flag_checks.yaml` checks each yes or no answer with `ca/yes_or_no_count`. Two answers
are ones the form lets the filer leave unanswered, and a blank there is passed on as a blank checked
count: Schedule 8 Part 4 and Part 5 ("If not, leave this part blank"). Every other yes or no answer
refuses a blank, including the eight T657 "use the (YYYY-1) calculation instead" answers, where the
form text says nothing about a blank (held for the owner's call, ticket #95).
"""

from __future__ import annotations

from pathlib import Path

import yaml

import tax_engine.jurisdictions.ca_on

PART = (
    Path(tax_engine.jurisdictions.ca_on.__file__).parent
    / "manifests"
    / "v1"
    / "30_yes_or_no_flag_checks.yaml"
)
PASSED_ON = {"ca/cpp_part_4_completed", "ca/cpp_part_5_completed"}


def steps() -> list[dict[str, object]]:
    document = yaml.safe_load(PART.read_text(encoding="utf-8"))
    return [step for step in document["capabilities"] if step["name"] == "ca/yes_or_no_count"]


def count_of(step: dict[str, object]) -> object:
    consumes = step["consumes"]
    assert isinstance(consumes, dict)
    return consumes["count"]


def test_the_two_answers_the_form_lets_the_filer_leave_blank_pass_a_blank_on() -> None:
    passing = {count_of(step) for step in steps() if step.get("blank") == {"count": "pass_on"}}

    assert passing == PASSED_ON


def test_every_other_yes_or_no_answer_refuses_a_blank() -> None:
    others = [step for step in steps() if count_of(step) not in PASSED_ON]

    assert len(others) > 20
    assert all("blank" not in step for step in others)
