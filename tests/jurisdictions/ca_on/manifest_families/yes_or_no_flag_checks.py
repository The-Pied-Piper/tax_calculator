"""The CA-ON manifest entries of one family of lines (see `test_manifest.py`)."""

from __future__ import annotations

from tax_engine.domain.manifest import CapabilitySelection
from tax_engine.jurisdictions.ca.capabilities.yes_or_no_count import YesOrNoCount
from tax_engine.jurisdictions.ca.catalog import (
    AGED_18_OR_OLDER_AT_END_OF_2025,
    AGED_18_OR_OLDER_AT_END_OF_2025_CHECKED,
    BORN_IN_1960_OR_EARLIER,
    BORN_IN_1960_OR_EARLIER_CHECKED,
    CPP_PART_4_COMPLETED,
    CPP_PART_4_COMPLETED_YES_OR_NO_CHECKED,
    CPP_PART_5_COMPLETED,
    CPP_PART_5_COMPLETED_YES_OR_NO_CHECKED,
    DEPENDANT_CAREGIVER_AGED_18_OR_OLDER,
    DEPENDANT_CAREGIVER_AGED_18_OR_OLDER_CHECKED,
    DEPENDANT_CAREGIVER_ELIGIBLE,
    DEPENDANT_CAREGIVER_ELIGIBLE_CHECKED,
    EI_SPECIAL_BENEFITS_AGREEMENT,
    EI_SPECIAL_BENEFITS_AGREEMENT_CHECKED,
    ELIGIBLE_FOR_DISABILITY_AMOUNT,
    ELIGIBLE_FOR_DISABILITY_AMOUNT_CHECKED,
    FHSA_MAXIMUM_PARTICIPATION_PERIOD_ENDED,
    FHSA_MAXIMUM_PARTICIPATION_PERIOD_ENDED_CHECKED,
    PENSION_ANNUITY_CONDITIONS_MET,
    PENSION_ANNUITY_CONDITIONS_MET_CHECKED,
    RESIDENT_IN_CANADA_THROUGHOUT_2025,
    RESIDENT_IN_CANADA_THROUGHOUT_2025_CHECKED,
    RESP_AIPS_PART_A_APPLIES,
    RESP_AIPS_PART_A_APPLIES_CHECKED,
    SEARCH_AND_RESCUE_CONDITIONS_MET,
    SEARCH_AND_RESCUE_CONDITIONS_MET_CHECKED,
    SPOUSE_CAREGIVER_ELIGIBLE,
    SPOUSE_CAREGIVER_ELIGIBLE_CHECKED,
    SPOUSE_NOT_SEPARATED_90_DAYS,
    SPOUSE_NOT_SEPARATED_90_DAYS_CHECKED,
    SPOUSES_CLAIMED,
    SPOUSES_CLAIMED_CHECKED,
    T657_CHART_2016_USES_D_INSTEAD,
    T657_CHART_2016_USES_D_INSTEAD_CHECKED,
    T657_CHART_2017_USES_D_INSTEAD,
    T657_CHART_2017_USES_D_INSTEAD_CHECKED,
    T657_CHART_2018_USES_D_INSTEAD,
    T657_CHART_2018_USES_D_INSTEAD_CHECKED,
    T657_CHART_2019_USES_D_INSTEAD,
    T657_CHART_2019_USES_D_INSTEAD_CHECKED,
    T657_CHART_2020_USES_D_INSTEAD,
    T657_CHART_2020_USES_D_INSTEAD_CHECKED,
    T657_CHART_2021_USES_D_INSTEAD,
    T657_CHART_2021_USES_D_INSTEAD_CHECKED,
    T657_CHART_2022_USES_D_INSTEAD,
    T657_CHART_2022_USES_D_INSTEAD_CHECKED,
    T657_CHART_2023_USES_D_INSTEAD,
    T657_CHART_2023_USES_D_INSTEAD_CHECKED,
    UNDER_18_ON_DECEMBER_31,
    UNDER_18_ON_DECEMBER_31_CHECKED,
    VOLUNTEER_FIREFIGHTERS_CONDITIONS_MET,
    VOLUNTEER_FIREFIGHTERS_CONDITIONS_MET_CHECKED,
)
from tax_engine.jurisdictions.ca_on.catalog import (
    CLAIMS_SENIORS_CARE_CREDIT,
    CLAIMS_SENIORS_CARE_CREDIT_CHECKED,
)

INPUTS = frozenset[str]()

OUTPUTS = frozenset[str]()

# One check per yes or no flag: a count of 1 or 0, a count of 2 or more refused.
STEPS = {
    CapabilitySelection(
        name="ca/yes_or_no_count",
        params={},
        consumes={"count": "ca-on/claims_seniors_care_credit"},
        produces={"output": "ca-on/claims_seniors_care_credit_checked"},
    ),
    CapabilitySelection(
        name="ca/yes_or_no_count",
        params={},
        consumes={"count": "ca/aged_18_or_older_at_end_of_2025"},
        produces={"output": "ca/aged_18_or_older_at_end_of_2025_checked"},
    ),
    CapabilitySelection(
        name="ca/yes_or_no_count",
        params={},
        consumes={"count": "ca/resident_in_canada_throughout_2025"},
        produces={"output": "ca/resident_in_canada_throughout_2025_checked"},
    ),
    CapabilitySelection(
        name="ca/yes_or_no_count",
        params={},
        consumes={"count": "ca/born_in_1960_or_earlier"},
        produces={"output": "ca/born_in_1960_or_earlier_checked"},
    ),
    CapabilitySelection(
        name="ca/yes_or_no_count",
        params={},
        consumes={"count": "ca/under_18_on_december_31"},
        produces={"output": "ca/under_18_on_december_31_checked"},
    ),
    CapabilitySelection(
        name="ca/yes_or_no_count",
        params={},
        consumes={"count": "ca/eligible_for_disability_amount"},
        produces={"output": "ca/eligible_for_disability_amount_checked"},
    ),
    CapabilitySelection(
        name="ca/yes_or_no_count",
        params={},
        consumes={"count": "ca/spouses_claimed"},
        produces={"output": "ca/spouses_claimed_checked"},
    ),
    CapabilitySelection(
        name="ca/yes_or_no_count",
        params={},
        consumes={"count": "ca/spouse_caregiver_eligible"},
        produces={"output": "ca/spouse_caregiver_eligible_checked"},
    ),
    CapabilitySelection(
        name="ca/yes_or_no_count",
        params={},
        consumes={"count": "ca/dependant_caregiver_eligible"},
        produces={"output": "ca/dependant_caregiver_eligible_checked"},
    ),
    CapabilitySelection(
        name="ca/yes_or_no_count",
        params={},
        consumes={"count": "ca/dependant_caregiver_aged_18_or_older"},
        produces={"output": "ca/dependant_caregiver_aged_18_or_older_checked"},
    ),
    CapabilitySelection(
        name="ca/yes_or_no_count",
        params={},
        consumes={"count": "ca/spouse_not_separated_90_days"},
        produces={"output": "ca/spouse_not_separated_90_days_checked"},
    ),
    CapabilitySelection(
        name="ca/yes_or_no_count",
        params={},
        consumes={"count": "ca/ei_special_benefits_agreement"},
        produces={"output": "ca/ei_special_benefits_agreement_checked"},
    ),
    CapabilitySelection(
        name="ca/yes_or_no_count",
        params={},
        consumes={"count": "ca/pension_annuity_conditions_met"},
        produces={"output": "ca/pension_annuity_conditions_met_checked"},
    ),
    CapabilitySelection(
        name="ca/yes_or_no_count",
        params={},
        consumes={"count": "ca/resp_aips_part_a_applies"},
        produces={"output": "ca/resp_aips_part_a_applies_checked"},
    ),
    CapabilitySelection(
        name="ca/yes_or_no_count",
        params={},
        consumes={"count": "ca/search_and_rescue_conditions_met"},
        produces={"output": "ca/search_and_rescue_conditions_met_checked"},
    ),
    CapabilitySelection(
        name="ca/yes_or_no_count",
        params={},
        consumes={"count": "ca/volunteer_firefighters_conditions_met"},
        produces={"output": "ca/volunteer_firefighters_conditions_met_checked"},
    ),
    CapabilitySelection(
        name="ca/yes_or_no_count",
        params={},
        consumes={"count": "ca/t657_chart_2016_uses_d_instead"},
        produces={"output": "ca/t657_chart_2016_uses_d_instead_checked"},
    ),
    CapabilitySelection(
        name="ca/yes_or_no_count",
        params={},
        consumes={"count": "ca/t657_chart_2017_uses_d_instead"},
        produces={"output": "ca/t657_chart_2017_uses_d_instead_checked"},
    ),
    CapabilitySelection(
        name="ca/yes_or_no_count",
        params={},
        consumes={"count": "ca/t657_chart_2018_uses_d_instead"},
        produces={"output": "ca/t657_chart_2018_uses_d_instead_checked"},
    ),
    CapabilitySelection(
        name="ca/yes_or_no_count",
        params={},
        consumes={"count": "ca/t657_chart_2019_uses_d_instead"},
        produces={"output": "ca/t657_chart_2019_uses_d_instead_checked"},
    ),
    CapabilitySelection(
        name="ca/yes_or_no_count",
        params={},
        consumes={"count": "ca/t657_chart_2020_uses_d_instead"},
        produces={"output": "ca/t657_chart_2020_uses_d_instead_checked"},
    ),
    CapabilitySelection(
        name="ca/yes_or_no_count",
        params={},
        consumes={"count": "ca/t657_chart_2021_uses_d_instead"},
        produces={"output": "ca/t657_chart_2021_uses_d_instead_checked"},
    ),
    CapabilitySelection(
        name="ca/yes_or_no_count",
        params={},
        consumes={"count": "ca/t657_chart_2022_uses_d_instead"},
        produces={"output": "ca/t657_chart_2022_uses_d_instead_checked"},
    ),
    CapabilitySelection(
        name="ca/yes_or_no_count",
        params={},
        consumes={"count": "ca/t657_chart_2023_uses_d_instead"},
        produces={"output": "ca/t657_chart_2023_uses_d_instead_checked"},
    ),
    CapabilitySelection(
        name="ca/yes_or_no_count",
        params={},
        consumes={"count": "ca/fhsa_maximum_participation_period_ended"},
        produces={"output": "ca/fhsa_maximum_participation_period_ended_checked"},
    ),
    # Schedule 8 Part 4 completed, the answer to a yes or no question, a count of 1 or 0,
    # checked before the steps that read it. A count of 2 or more is refused, not capped.
    CapabilitySelection(
        name="ca/yes_or_no_count",
        params={},
        consumes={"count": "ca/cpp_part_4_completed"},
        blank={"count": "pass_on"},
        produces={"output": "ca/cpp_part_4_completed_yes_or_no_checked"},
    ),
    # Schedule 8 Part 5 completed, the answer to a yes or no question, a count of 1 or 0,
    # checked before the steps that read it. A count of 2 or more is refused, not capped.
    CapabilitySelection(
        name="ca/yes_or_no_count",
        params={},
        consumes={"count": "ca/cpp_part_5_completed"},
        blank={"count": "pass_on"},
        produces={"output": "ca/cpp_part_5_completed_yes_or_no_checked"},
    ),
}

WIRING = {
    (
        YesOrNoCount,
        frozenset({CLAIMS_SENIORS_CARE_CREDIT}),
        frozenset({CLAIMS_SENIORS_CARE_CREDIT_CHECKED}),
    ),
    (
        YesOrNoCount,
        frozenset({AGED_18_OR_OLDER_AT_END_OF_2025}),
        frozenset({AGED_18_OR_OLDER_AT_END_OF_2025_CHECKED}),
    ),
    (
        YesOrNoCount,
        frozenset({RESIDENT_IN_CANADA_THROUGHOUT_2025}),
        frozenset({RESIDENT_IN_CANADA_THROUGHOUT_2025_CHECKED}),
    ),
    (
        YesOrNoCount,
        frozenset({BORN_IN_1960_OR_EARLIER}),
        frozenset({BORN_IN_1960_OR_EARLIER_CHECKED}),
    ),
    (
        YesOrNoCount,
        frozenset({UNDER_18_ON_DECEMBER_31}),
        frozenset({UNDER_18_ON_DECEMBER_31_CHECKED}),
    ),
    (
        YesOrNoCount,
        frozenset({ELIGIBLE_FOR_DISABILITY_AMOUNT}),
        frozenset({ELIGIBLE_FOR_DISABILITY_AMOUNT_CHECKED}),
    ),
    (
        YesOrNoCount,
        frozenset({SPOUSES_CLAIMED}),
        frozenset({SPOUSES_CLAIMED_CHECKED}),
    ),
    (
        YesOrNoCount,
        frozenset({SPOUSE_CAREGIVER_ELIGIBLE}),
        frozenset({SPOUSE_CAREGIVER_ELIGIBLE_CHECKED}),
    ),
    (
        YesOrNoCount,
        frozenset({DEPENDANT_CAREGIVER_ELIGIBLE}),
        frozenset({DEPENDANT_CAREGIVER_ELIGIBLE_CHECKED}),
    ),
    (
        YesOrNoCount,
        frozenset({DEPENDANT_CAREGIVER_AGED_18_OR_OLDER}),
        frozenset({DEPENDANT_CAREGIVER_AGED_18_OR_OLDER_CHECKED}),
    ),
    (
        YesOrNoCount,
        frozenset({SPOUSE_NOT_SEPARATED_90_DAYS}),
        frozenset({SPOUSE_NOT_SEPARATED_90_DAYS_CHECKED}),
    ),
    (
        YesOrNoCount,
        frozenset({EI_SPECIAL_BENEFITS_AGREEMENT}),
        frozenset({EI_SPECIAL_BENEFITS_AGREEMENT_CHECKED}),
    ),
    (
        YesOrNoCount,
        frozenset({PENSION_ANNUITY_CONDITIONS_MET}),
        frozenset({PENSION_ANNUITY_CONDITIONS_MET_CHECKED}),
    ),
    (
        YesOrNoCount,
        frozenset({RESP_AIPS_PART_A_APPLIES}),
        frozenset({RESP_AIPS_PART_A_APPLIES_CHECKED}),
    ),
    (
        YesOrNoCount,
        frozenset({SEARCH_AND_RESCUE_CONDITIONS_MET}),
        frozenset({SEARCH_AND_RESCUE_CONDITIONS_MET_CHECKED}),
    ),
    (
        YesOrNoCount,
        frozenset({VOLUNTEER_FIREFIGHTERS_CONDITIONS_MET}),
        frozenset({VOLUNTEER_FIREFIGHTERS_CONDITIONS_MET_CHECKED}),
    ),
    (
        YesOrNoCount,
        frozenset({T657_CHART_2016_USES_D_INSTEAD}),
        frozenset({T657_CHART_2016_USES_D_INSTEAD_CHECKED}),
    ),
    (
        YesOrNoCount,
        frozenset({T657_CHART_2017_USES_D_INSTEAD}),
        frozenset({T657_CHART_2017_USES_D_INSTEAD_CHECKED}),
    ),
    (
        YesOrNoCount,
        frozenset({T657_CHART_2018_USES_D_INSTEAD}),
        frozenset({T657_CHART_2018_USES_D_INSTEAD_CHECKED}),
    ),
    (
        YesOrNoCount,
        frozenset({T657_CHART_2019_USES_D_INSTEAD}),
        frozenset({T657_CHART_2019_USES_D_INSTEAD_CHECKED}),
    ),
    (
        YesOrNoCount,
        frozenset({T657_CHART_2020_USES_D_INSTEAD}),
        frozenset({T657_CHART_2020_USES_D_INSTEAD_CHECKED}),
    ),
    (
        YesOrNoCount,
        frozenset({T657_CHART_2021_USES_D_INSTEAD}),
        frozenset({T657_CHART_2021_USES_D_INSTEAD_CHECKED}),
    ),
    (
        YesOrNoCount,
        frozenset({T657_CHART_2022_USES_D_INSTEAD}),
        frozenset({T657_CHART_2022_USES_D_INSTEAD_CHECKED}),
    ),
    (
        YesOrNoCount,
        frozenset({T657_CHART_2023_USES_D_INSTEAD}),
        frozenset({T657_CHART_2023_USES_D_INSTEAD_CHECKED}),
    ),
    (
        YesOrNoCount,
        frozenset({FHSA_MAXIMUM_PARTICIPATION_PERIOD_ENDED}),
        frozenset({FHSA_MAXIMUM_PARTICIPATION_PERIOD_ENDED_CHECKED}),
    ),
    (
        YesOrNoCount,
        frozenset({CPP_PART_4_COMPLETED}),
        frozenset({CPP_PART_4_COMPLETED_YES_OR_NO_CHECKED}),
    ),
    (
        YesOrNoCount,
        frozenset({CPP_PART_5_COMPLETED}),
        frozenset({CPP_PART_5_COMPLETED_YES_OR_NO_CHECKED}),
    ),
}
