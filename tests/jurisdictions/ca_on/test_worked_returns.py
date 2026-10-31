"""Every worked return in `returns/`, computed end to end and checked line by line.

One test runs per `*.yaml` file in `returns/` (the pytest id is the file stem): the file's inputs
go through the service the composition root builds, and each expected line must equal the
worksheet's artifact exactly. A line or input a file leaves out is blank: an absent line must
compute to zero. Adding a return is adding a file.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from tax_engine import build_tax_computation
from tax_engine.adapters.outbound.yaml_jurisdictions import YamlJurisdictionSource
from tax_engine.application.services.tax_computation import TaxComputationService
from tax_engine.domain.artifact import ArtifactRegistry
from tax_engine.domain.jurisdiction_code import JurisdictionCode
from tax_engine.domain.manifest import Manifest
from tax_engine.domain.parameters.rate import Rate
from tax_engine.jurisdictions.ca.catalog import (
    DEPENDANT_CARE_EXPENSES,
    DEPENDANT_CREDIT_AMOUNTS,
    DEPENDANT_NET_INCOME,
    DEPENDANT_TAXABLE_INCOME,
    DEPENDANT_UNDER_18,
    DISPOSITION_ADJUSTED_COST_BASE,
    DISPOSITION_OUTLAYS,
    DISPOSITION_PROCEEDS,
    OTHER_DEPENDANT_MEDICAL_EXPENSES,
    RESIDENCE_ADJUSTED_COST_BASE,
    RESIDENCE_COST_BASE_ADJUSTMENTS_AFTER_1981,
    RESIDENCE_FMV_DEC_31_1981,
    RESIDENCE_OUTLAYS,
    RESIDENCE_PART_2_APPLIES,
    RESIDENCE_PLUS_ONE_YEAR,
    RESIDENCE_PROCEEDS,
    RESIDENCE_YEARS_DESIGNATED_1972_TO_1981,
    RESIDENCE_YEARS_DESIGNATED_AFTER_1981,
    RESIDENCE_YEARS_OWNED_1972_TO_1981,
    RESIDENCE_YEARS_OWNED_AFTER_1981,
)
from tax_engine.jurisdictions.ca_on.catalog import (
    CLAIMED_AS_ELIGIBLE_DEPENDANT,
    DEPENDANT_ON428_LINE_28,
)
from tax_engine.registrations import JURISDICTIONS
from tests.application.services.test_tax_computation_forms import (
    COUNT_DOUBLED,
    artifact_registry,
    rental_manifest,
    service,
)
from tests.jurisdictions.ca_on.end_to_end.support import service as shared_service
from tests.jurisdictions.ca_on.worked_return import WorkedReturn, WorkedReturnError

RETURNS = Path(__file__).parent / "returns"


def load(
    path: Path,
    manifest: Manifest | None = None,
    artifacts: ArtifactRegistry | None = None,
) -> WorkedReturn:
    """The worked return at `path` with its blank lines and inputs filled in.

    Against the manifest of the file's jurisdiction and tax year and the shared registry, unless a
    `manifest` and `artifacts` are given. For the shared registry the manifest is composed first,
    which registers the kinds `<form>.<export>` of its forms, so the file may expect them.
    """
    if artifacts is None:
        artifacts = ArtifactRegistry.shared()
        head = yaml.safe_load(path.read_text())
        build_tax_computation().compose(JurisdictionCode(head["jurisdiction"]), head["tax_year"])
    worked = WorkedReturn.load(path, artifacts)
    if manifest is None:
        manifest = (
            YamlJurisdictionSource(JURISDICTIONS.roots())
            .get_jurisdiction(worked.jurisdiction)
            .manifest_for(worked.tax_year)
        )
    default = worked.jurisdiction.namespace.identifier("return")
    (default_form,) = (form for form in manifest.forms if form.name == default)
    worked = worked.with_blanks(
        frozenset(manifest.inputs), frozenset(default_form.exports), artifacts
    )
    worked.check_forms(manifest.forms, artifacts)
    return worked


def check(path: Path) -> None:
    """Load the worked return at `path`, compute it and assert every expected line."""
    service = shared_service()  # registers the catalogs the loader resolves through
    check_against(load(path), service)


def check_against(worked: WorkedReturn, service: TaxComputationService) -> None:
    """Compute `worked` with `service`; assert the lines each instance of each form is expected."""
    result = service.compute(worked.jurisdiction, worked.tax_year, *worked.inputs)

    for form in worked.form_expected:
        assert len(result[form.form]) == len(form.instances), f"{worked.path.name}: {form.form}"
        for position, lines in enumerate(form.instances, start=1):
            worksheet = result[form.form][position - 1]
            for expected in lines:
                where = f"{worked.path.name}: {form.form}, instance {position}"
                assert worksheet.get(expected.kind) == expected, (
                    f"{where}: {expected.kind.identifier}"
                )


@pytest.mark.parametrize("path", WorkedReturn.discover(RETURNS), ids=lambda path: path.stem)
def test_worked_return(path: Path) -> None:
    check(path)


# A made-up low-income return for the tests of the mechanism itself; the real returns are
# only ever read from `returns/`, so nothing here names one of them.
LOW_INCOME = """\
jurisdiction: CA-ON
tax_year: 2025
description: >-
  Employment income of 10000, no capital gain, no unused or new RRSP contributions, no union
  dues and no deductions from net income, among them no net capital losses of other years
  (T1 line 25300). The CPP contributions are computed from employment
  income by Schedule 8's tiers: base contributions 4.95% x (10000 - 3500) = 321.75, first
  additional 1% x 6500 = 65.00, no second additional below the 71300 ceiling, so enhanced
  contributions of 65.00. The EI premiums are Form T2204 line 16, from T4 insurable earnings of
  10000 and premiums deducted of 164.00 (= 1.64% x 10000): 164.00. The contributions available to
  deduct (Schedule 7 line 10) are the unused
  contributions (line 1) of 0 plus the contributions (line 4) of 0: 0. The most that may be
  deducted (line 17) is the lesser of them and the deduction limit (line 11) of 1800, a
  chosen limit: 0. The amount deducted (line 18) is that 0, so the RRSP deduction (line 20)
  is 0, the unused contributions carried forward (line 23) are 0 - 0 = 0. With no eligible
  child and no child care expenses paid, the child care expenses deduction (T778 line 7) is
  the least of the basic limit 0 x 8000 + 0 x 11000 + 0 x 5000 = 0, the 0 paid and
  two-thirds of the earned income of 10000, 6666.666..., rounded half-up to the cent:
  6666.67: 0. So the enhanced contributions are the only deduction from total income that
  is not zero.
  Net income and taxable income are 9935.00. The Canada employment amount is the
  lesser of 1471 and the employment income of 10000: 1471. The federal basic personal
  amount is computed from net income by the Federal Worksheet: 9935.00 is at or below
  its 177882 threshold, so it is the base amount 14538 plus the whole supplement
  amount 1591, 16129, rounded half-up to the cent. With no eligible dependant and
  no infirm child, the amount for an eligible dependant (16129 less a dependant's
  net income of 0 federally, 11905.00 less it at most 10823 for Ontario) is claimed
  for 0 eligible dependants and the amount for infirm children is 0 x 2687: each 0. Born
  in 1961 or later, the age amount (9028 less 15% of net income over 45522, nothing) is
  claimed for 0 filers born in 1960 or earlier: 0. With a spouse's net income of 0 and no
  spouse amount claimed, the spouse amount (16129 less 0) and the Canada caregiver amount
  for the spouse (28798 less 0, at most 8601, less the spouse amount) are each claimed
  for 0: 0.
  The federal total of credit amounts is its basic personal amount plus those two zeros,
  321.75, 164.00 and 1471; the Ontario total is its basic personal amount plus its zero,
  321.75 and 164.00 (ON428 has no Canada employment amount). Each form's non-refundable tax
  credits are its total times its rate (14.5% of 18085.75 = 2622.43375, rounded half-up to
  the cent: 2622.43; 5.05% of 13232.75 = 668.253875, rounded half-up to the cent: 668.25);
  each exceeds its tax (14.5% of 9935.00 = 1440.575, rounded half-up to the cent: 1440.58;
  5.05% of it = 501.7175, rounded half-up to the cent: 501.72), leaving zero. An Ontario tax
  of zero is below the first surtax threshold, so the surtax is zero and the Ontario tax
  with surtax is zero. With no dependent children and no dependants, the Ontario tax
  reduction amounts are the basic reduction of 294.00, and the reduction is twice them less
  the tax of zero: 588.00, which leaves an Ontario tax after the reduction of zero, not a
  refund. The LIFT credit (Schedule ON428-A) is 5.05% of the employment income,
  505, below its 875 maximum, less 5% of net income over 32500, nothing as 9935.00 is below
  it: 505, more than the Ontario tax after the reduction of zero, so the Ontario tax after
  the LIFT credit is zero. With chosen qualifying donations of 0, the community food program
  donation tax credit for farmers (line 87) is 25% x 0 = 0 and the Ontario tax after it (line
  88) is 0 less 0, zero. A taxable income of 9935.00 is at or below the health premium chart's
  first threshold of 20000, so the premium is zero and the Ontario tax is zero. The net
  federal tax is the federal tax after credits, zero, and the total payable is it plus the
  Ontario tax, zero. The Canada workers benefit (Schedule 6) with no eligible spouse or
  dependant is 27% of the working income, the employment income of 10000, over 3000: 1890,
  at most 1633, less 15% of the adjusted family net income, the net income, over 26855,
  nothing as 9935.00 is below it: 1633; with one it would be 1890, at most 2813, less
  nothing over 30639: 1890. With 0 Schedule 6 eligible dependants the first applies: 1633.
  With no fertility treatment expenses, no child care expenses deduction (so the Ontario CARE
  credit, Schedule ON479-A, has a family adjusted income of 9935.00 + 0 + 0 = 9935.00, which
  is at most 20000 and gives a rate of 75%, and line 8 is 0 x 75% = 0), no seniors' transit
  amount paid, no political contributions (federal or Ontario), no Form T1221 slips and no
  co-operative education work placements (a chosen payroll of 0), the Ontario credits (ON479
  lines 1, 2, 14, 16, 17, 18, 20 and 21) and the provincial credits (T1 line 47900) are 0, as
  is the federal political contribution tax credit (T1 line 41000). With no amount on line
  21500 and no medical claim (line 33200), the refundable medical expense supplement (T1 line
  45200, Federal Worksheet) is 0: its line 11 is 0, so its line 16 is 0, for a filer resident
  in Canada throughout 2025 and 18 or older at the end of 2025 (counts of 1) with working
  income of 10000, $4,390 or more.
  With no net business, professional, commission, farming or fishing income (T1 lines
  13500 to 14300), line 27 is 0; the CPP months (Schedule 8 box A) are 12, so Part 2's
  line C is 9900.00, and with Schedule 8 Part 4 not completed and no agreement for EI special
  benefits, lines 22200, 31000, 31217, 42100 and 42120 are 0, whatever Part 4 and Schedule 13
  work out.
  The income tax deducted is a chosen 500, so the total credits are 500 plus the benefit
  plus the provincial credits, 2133, and the refund or balance owing is 0 less 2133: -2133,
  a refund. Every amount computed from a rate, fraction, amount or chart on the forms is
  rounded half-up to the cent, each line being a dollars-and-cents box; here that changes
  Form T778 line 6, the federal and Ontario tax on taxable income and both forms'
  non-refundable tax credits. The lines that only add, subtract, compare or choose take
  amounts already in cents, so the refund or balance owing is in cents too.
sources:
  - >-
    T1, Federal Worksheet, Schedule 3, Schedule 5, Schedule 6, Schedule 7, Schedule 8, ON428,
    Schedule ON428-A, T778 and EI table arithmetic on the 2025 figures.
inputs:
  ca/employment_income: "10000"
  ca/t4_cpp_pensionable_earnings_outside_quebec: "10000"
  ca/t4_cpp_slip_count: "1"
  # T4 boxes 24 (= 14) and 18: the premium required on it, Form T2204 line 16 (line 31200).
  ca/t2204_insurable_earnings: "10000"
  ca/t2204_premiums_deducted: "164.00"
  ca/cpp_t4_base_and_first_additional_contributions: "386.75"
  ca/cpp_t4_second_additional_contributions: "0"
  ca/qsbcs_dispositions: []
  ca/qffp_dispositions: []
  ca/qffp_foreclosure_dispositions: []
  ca/share_dispositions: []
  ca/real_estate_dispositions: []
  ca/bond_dispositions: []
  ca/crypto_asset_dispositions: []
  ca/other_foreclosure_dispositions: []
  ca/personal_use_property_dispositions: []
  ca/listed_personal_property_dispositions: []
  ca/unapplied_listed_personal_property_losses: "0"
  ca/capital_gains_deferral: "0"
  ca/slip_capital_gains_or_losses: "0"
  ca/t3_capital_gains_or_losses: "0"
  ca/other_employment_income: "0"
  ca/old_age_security: "0"
  ca/cpp_or_qpp_benefits: "0"
  ca/other_pensions_and_superannuation: "0"
  ca/universal_child_care_benefit: "0"
  ca/ei_and_other_benefits: "0"
  ca/t3_taxable_dividends_other_than_eligible: "0"
  ca/t4ps_taxable_dividends_other_than_eligible: "0"
  ca/t5_taxable_dividends_other_than_eligible: "0"
  ca/t5013_taxable_dividends_other_than_eligible: "0"
  ca/t3_taxable_dividends: "0"
  ca/t4ps_taxable_dividends: "0"
  ca/t5_taxable_dividends: "0"
  ca/t5013_taxable_dividends: "0"
  ca/eligible_dividends_received_without_a_slip: "0"
  ca/other_dividends_received_without_a_slip: "0"
  ca/t3_dividend_tax_credit: "0"
  ca/t4ps_dividend_tax_credit: "0"
  ca/t5_dividend_tax_credit: "0"
  ca/t5013_dividend_tax_credit: "0"
  ca/t3_investment_income: "0"
  ca/t5_investment_income: "0"
  ca/t5013_investment_income: "0"
  ca/investment_income_credited_not_received: "0"
  ca/tax_refund_interest: "0"
  ca/foreign_investment_income: "0"
  ca/investment_income_without_a_slip: "0"
  ca/investment_royalties: "0"
  ca/investment_income_reported_in_previous_years: "0"
  ca/net_partnership_income: "0"
  ca/rdsp_income: "0"
  ca/t776_statements:
    - ca/rental_properties: []
      ca/rental_other_income: "0"
      ca/rental_advertising: "0"
      ca/rental_advertising_personal_portion: "0"
      ca/rental_advertising_short_term_portion: "0"
      ca/rental_insurance: "0"
      ca/rental_insurance_personal_portion: "0"
      ca/rental_insurance_short_term_portion: "0"
      ca/rental_interest_and_bank_charges: "0"
      ca/rental_interest_and_bank_charges_personal_portion: "0"
      ca/rental_interest_and_bank_charges_short_term_portion: "0"
      ca/rental_office_expenses: "0"
      ca/rental_office_expenses_personal_portion: "0"
      ca/rental_office_expenses_short_term_portion: "0"
      ca/rental_professional_fees: "0"
      ca/rental_professional_fees_personal_portion: "0"
      ca/rental_professional_fees_short_term_portion: "0"
      ca/rental_management_and_administration_fees: "0"
      ca/rental_management_and_administration_fees_personal_portion: "0"
      ca/rental_management_and_administration_fees_short_term_portion: "0"
      ca/rental_repairs_and_maintenance: "0"
      ca/rental_repairs_and_maintenance_personal_portion: "0"
      ca/rental_repairs_and_maintenance_short_term_portion: "0"
      ca/rental_salaries_wages_and_benefits: "0"
      ca/rental_salaries_wages_and_benefits_personal_portion: "0"
      ca/rental_salaries_wages_and_benefits_short_term_portion: "0"
      ca/rental_property_taxes: "0"
      ca/rental_property_taxes_personal_portion: "0"
      ca/rental_property_taxes_short_term_portion: "0"
      ca/rental_travel: "0"
      ca/rental_travel_personal_portion: "0"
      ca/rental_travel_short_term_portion: "0"
      ca/rental_utilities: "0"
      ca/rental_utilities_personal_portion: "0"
      ca/rental_utilities_short_term_portion: "0"
      ca/rental_motor_vehicle_expenses: "0"
      ca/rental_motor_vehicle_expenses_personal_portion: "0"
      ca/rental_motor_vehicle_expenses_short_term_portion: "0"
      ca/rental_other_expenses: "0"
      ca/rental_other_expenses_personal_portion: "0"
      ca/rental_other_expenses_short_term_portion: "0"
      ca/short_term_rental_units: []
      ca/short_term_rental_cca_units: []
      ca/rental_coowner: "0"
      ca/rental_coowner_share: "0"
      ca/rental_coowner_other_expenses: "0"
      ca/rental_vehicle_sales_tax_rate: "0"
      ca/rental_cca_classes: []
      ca/rental_equipment_additions: []
      ca/rental_building_additions: []
      ca/rental_coowner_recaptured_cca: "0"
      ca/rental_coowner_terminal_loss: "0"
      ca/rental_coowner_cca_claim: "0"
      ca/rental_cca_personal_part: "0"
      ca/rental_cca_business_use_of_home: "0"
      ca/rental_partner: "0"
      ca/rental_partner_t5013_slip: "0"
      ca/rental_partner_share: "0"
      ca/rental_partner_percentage: "0"
      ca/rental_partner_gst_hst_rebate: "0"
      ca/rental_partner_other_expenses: "0"
      ca/rental_epop_associated: "0"
      ca/rental_epop_agreement_filed: "0"
      ca/rental_epop_percentage: "0"
      ca/rental_epop_percentage_total: "0"
      ca/rental_minister_allocation_given: "0"
      ca/rental_minister_allocation: "0"
      ca/rental_land_additions: "0"
      ca/rental_land_dispositions: "0"
      ca/rental_fiscal_period_days_entered: "0"
  ca/taxable_support_payments: "0"
  ca/rrsp_income: "0"
  ca/fhsa_income: "0"
  ca/other_fhsa_income: "0"
  ca/other_income: "0"
  ca/taxable_scholarships: "0"
  ca/workers_compensation_benefits: "0"
  ca/social_assistance_payments: "0"
  ca/net_federal_supplements: "0"
  ca/uccb_repayment: "0"
  ca/rdsp_income_repayment: "0"
  ca/canadian_armed_forces_and_police_deduction: "0"
  ca/limited_partnership_losses_of_other_years: "0"
  ca/non_capital_losses_of_other_years: "0"
  ca/net_capital_losses_before_may_23_1985: "0"
  ca/pre_1986_deductions_before_1988: "0"
  ca/pre_1986_deductions_1988_and_1989: "0"
  ca/pre_1986_deductions_1990_to_1999: "0"
  ca/pre_1986_deductions_2000: "0"
  ca/pre_1986_deductions_2001_to_2024: "0"
  ca/unapplied_net_capital_losses_1985_to_1987: "0"
  ca/unapplied_net_capital_losses_1988_and_1989: "0"
  ca/unapplied_net_capital_losses_1990_to_1999: "0"
  ca/unapplied_net_capital_losses_2000: "0"
  ca/unapplied_net_capital_losses_2001_to_2024: "0"
  ca/net_capital_losses_claimed: "0"
  ca/additional_deductions: "0"
  ca/other_payments_deduction_above_limit: "0"
  ca/unused_rrsp_contributions: "0"
  ca/rrsp_contributions: "0"
  ca/rrsp_deduction_limit: "1800"
  ca/rrsp_amount_deducted: "0"
  ca/union_dues: "0"
  ca/rpp_deduction: "0"
  ca/support_payments_deduction: "0"
  ca/exploration_and_development_expenses: "0"
  ca/other_deductions: "0"
  ca/total_carrying_charges: "0"
  ca/total_interest_expenses: "0"
  ca/total_other_expenses: "0"
  ca/capital_gains_deductions_1985_to_1987: "0"
  ca/capital_gains_deductions_1988_and_1989_other_than_eligible_capital_property: "0"
  ca/capital_gains_deductions_1988_and_1989_eligible_capital_property: "0"
  ca/capital_gains_deductions_1990_to_1999: "0"
  ca/capital_gains_deductions_2000: "0"
  ca/capital_gains_deductions_2001_to_2024: "0"
  ca/other_business_investment_loss_reductions_1986_to_1994: "0"
  ca/other_business_investment_loss_reductions_1994_to_1996: "0"
  ca/other_business_investment_loss_reductions_1997_to_1999: "0"
  ca/other_business_investment_loss_reductions_2000: "0"
  ca/other_business_investment_loss_reductions_2001_to_2023: "0"
  ca/other_business_investment_loss_reductions_2024: "0"
  ca/business_investment_loss: "0"
  ca/fhsa_contributions_in_2025: "0"
  ca/fhsa_contributions_in_2025_after_first_qualifying_withdrawal: "0"
  ca/fhsa_variable_b_amount: "0"
  ca/fhsa_designated_withdrawals_in_2025: "0"
  ca/fhsa_contributions_in_2024: "0"
  ca/fhsa_contributions_in_2024_before_first_qualifying_withdrawal: "0"
  ca/fhsa_carryforward_for_2025: "0"
  ca/fhsa_rrsp_transfers_in_2024_and_prior_years: "0"
  ca/fhsa_rrsp_transfers_in_2025: "0"
  ca/fhsa_designated_transfers_in_2024_and_prior_years: "0"
  ca/fhsa_designated_transfers_in_2025: "0"
  ca/fhsa_variable_h_amount: "0"
  ca/fhsa_carryforward_for_2024: "0"
  ca/fhsa_variable_f_amount: "0"
  ca/fhsa_annual_limits_for_2024_and_prior_years: "0"
  ca/fhsa_deductions_for_2024_and_prior_years: "0"
  ca/fhsa_unused_contributions_brought_forward: "0"
  ca/fhsa_contributions_deducted: "0"
  ca/fhsa_maximum_participation_period_ended: "0"
  ca/cpp_months: "12"
  ca/qpp_months: "12"
  ca/cpt20_earnings: "0"
  ca/cpp_part_4_completed: "0"
  ca/ei_controlled_corporation_earnings: "0"
  ca/ei_exempt_self_employment_income: "0"
  ca/ei_insurable_earnings: "0"
  ca/ei_special_benefits_agreement: "0"
  ca-on/dependent_children: "0"
  ca-on/dependants: "0"
  ca/eligible_dependants: "0"
  ca/dependant_net_income: "0"
  ca/infirm_dependants: []
  ca/medical_expenses: "0"
  ca/other_dependants: []
  ca-on/caregiver_dependants: []
  ca/disability_dependants: []
  ca/infirm_children: "0"
  ca/born_in_1960_or_earlier: "0"
  ca/spouse_net_income: "0"
  ca/spouses_claimed: "0"
  ca/spouse_caregiver_eligible: "0"
  ca/child_care_expenses_paid: "0"
  ca/children_under_seven: "0"
  ca/children_with_disability: "0"
  ca/children_seven_to_sixteen: "0"
  ca/cwb_claiming_basic: "1"
  ca/cwb_eligible_dependants: "0"
  ca/income_tax_deducted: "500"
  ca/part_xii_2_tax_credit: "0"
  ca/employee_and_partner_gst_hst_rebate: "0"
  ca/educator_supplies_expenses: "0"
  ca/tax_paid_by_instalments: "0"
  ca/itc_recapture_expenditure_at_15_percent: "0"
  ca/itc_recapture_expenditure_at_20_percent: "0"
  ca/labour_sponsored_funds_net_cost: "0"
  ca/acwb_paid_to_you: "0"
  ca/acwb_paid_to_spouse: "0"
  ca/acwb_disability_supplement_paid: "0"
  ca/resp_aips_received_part_a: "0"
  ca/resp_aips_rrsp_contributions: "0"
  ca/resp_aips_reduction_used_in_previous_years: "0"
  ca/resp_aips_received_part_b: "0"
  ca/resp_aips_part_a_applies: "0"
  ca/rl_10_labour_sponsored_fund_amount: "0"
  ca-on/opportunities_fund_donation: "0"
  ca-on/fertility_expenses: "0"
  ca-on/claims_seniors_care_credit: "0"
  ca-on/applies_for_energy_and_property_tax_credit: "0"
  ca-on/applies_for_northern_energy_credit: "0"
  ca-on/chooses_single_benefit_payment: "0"
  ca-on/applies_for_senior_homeowners_grant: "0"
  ca-on/separate_residences_for_medical_reasons: "0"
  ca-on/lived_in_student_residence: "0"
  ca-on/rent_paid: "0"
  ca-on/property_tax_paid: "0"
  ca-on/reserve_home_energy_costs: "0"
  ca-on/public_long_term_care_paid: "0"
  ca-on/seniors_transit_paid: "0"
  ca-on/flow_through_share_slips: []
  ca-on/coop_education_payroll: "0"
  ca-on/coop_education_placements: []
  ca-on/community_food_program_donations: "0"
  ca/charitable_donations: "0"
  ca/government_donations: "0"
  ca/university_donations_outside_canada: "0"
  ca/foreign_charity_donations: "0"
  ca/ecological_and_cultural_gifts: "0"
  ca/ecological_gifts_before_2016: "0"
  ca/depreciable_gift_recaptured_depreciation: "0"
  ca/depreciable_gift_net_proceeds: "0"
  ca/depreciable_gift_capital_cost: "0"
  ca/capital_gift_taxable_gains: "0"
  ca/capital_gift_gains_deduction: "0"
  ca-on/political_contributions: "0"
  ca-on/care_supporting_persons_adjusted_income: "0"
  ca/political_contributions: "0"
  ca/t777_other_expenses: "0"
  ca/wage_loss_replacement_plan_income: "0"
  ca/resident_in_canada_throughout_2025: "1"
  ca/aged_18_or_older_at_end_of_2025: "1"
  ca/aged_19_or_older_at_end_of_2025: "1"
  ca/spouse_net_income_before_adjustments: "0"
  ca/spouse_uccb_repayment: "0"
  ca/spouse_rdsp_income_repayment: "0"
  ca/spouse_universal_child_care_benefit: "0"
  ca/spouse_rdsp_income: "0"
  ca/schedule_8_instances:
    - {}
expected:
  ca-on/return:
    - ca/taxable_capital_gains: "0"
      ca/t4_cpp_pensionable_earnings_slip_checked: "10000.00"
      ca/taxable_dividends_other_than_eligible: "0"
      ca/investment_income_before_prior_years: "0"
      ca/interest_and_other_investment_income: "0"
      ca/income_support_benefits: "0"
      ca/net_rental_income: "0"
      ca/total_income: "10000"
      ca/cpp_second_additional_earnings_maximum: "9900.00"
      ca/net_self_employment_income: "0"
      ca/cpp_payable_on_self_employment: "0"
      ca/cpp_base_contributions_on_self_employment: "0"
      ca/cpp_deduction_on_self_employment: "0"
      ca/ei_premiums_on_self_employment: "0"
      ca/ei_payable_on_self_employment: "0"
      ca/ei_premiums: "164.00"
      ca/rrsp_contributions_available: "0"
      ca/rrsp_deduction_maximum: "0"
      ca/rrsp_deduction: "0"
      ca/unused_rrsp_contributions_carried_forward: "0"
      ca/child_care_limit_for_children_under_seven: "0"
      ca/child_care_limit_for_children_with_disability: "0"
      ca/child_care_limit_for_children_seven_to_sixteen: "0"
      ca/child_care_basic_limit: "0"
      ca/child_care_earned_income: "10000"
      ca/child_care_earned_income_limit: "6666.67"
      ca/child_care_expenses: "0"
      ca/deductions_from_total_income: "65.00"
      ca/net_income: "9935.00"
      ca/amt_part_1_subtotal: "9935.00"
      ca/amt_applicable_rate_amount: "32.50"
      ca/amt_adjusted_income_with_gains: "9935.00"
      ca/net_income_before_adjustments: "9935.00"
      ca/fhsa_unused_contributions_carried_forward: "0"
      ca/other_payments_limit_income: "9935.00"
      ca/total_adjusted_net_capital_losses: "0.00"
      ca/net_capital_losses_available_to_claim: "0.00"
      ca/net_capital_losses_of_other_years: "0"
      ca/net_capital_loss_balance_before_may_23_1985: "0.00"
      ca/net_capital_loss_balance_1985_to_1987: "0.00"
      ca/net_capital_loss_balance_1988_and_1989: "0.00"
      ca/net_capital_loss_balance_1990_to_1999: "0.00"
      ca/net_capital_loss_balance_2000: "0.00"
      ca/net_capital_loss_balance_2001_to_2024: "0.00"
      ca/deductions_from_net_income: "0"
      ca/taxable_income: "9935.00"
      ca/federal_basic_tax: "1440.58"
      ca/basic_personal_amount: "16129"
      ca/age_maximum: "9028.00"
      ca/age_income_threshold: "45522.00"
      ca/age_income_over_threshold: "0"
      ca/age_reduction: "0"
      ca/age_amount_before_count: "9028.00"
      ca/age_amount: "0"
      ca/spouse_infirmity_supplement: "0"
      ca/spouse_amount_basis: "16129"
      ca/spouse_amount_before_count: "16129"
      ca/spouse_amount: "0"
      ca/eligible_dependant_amount_before_count: "16129"
      ca/eligible_dependant_amount: "0"
      ca/spouse_caregiver_base: "28798.00"
      ca/spouse_caregiver_before_maximum: "28798.00"
      ca/spouse_caregiver_limit: "8601.00"
      ca/spouse_caregiver_amount_before_count: "8601.00"
      ca/spouse_caregiver_amount: "0"
      ca/infirm_children_amount: "0"
      ca/canada_employment_amount: "1471"
      ca/non_refundable_credit_amounts: "18085.75"
      ca/non_refundable_tax_credits: "2622.43"
      ca/federal_tax_after_credits: "0"
      ca-on/ontario_basic_tax: "501.72"
      ca-on/basic_personal_amount: "12747"
      ca-on/eligible_dependant_base: "11905.00"
      ca-on/eligible_dependant_amount_before_maximum: "11905.00"
      ca-on/eligible_dependant_amount_before_count: "10823"
      ca-on/eligible_dependant_amount: "0"
      ca-on/non_refundable_credit_amounts: "13232.75"
      ca-on/non_refundable_tax_credits: "668.25"
      ca-on/ontario_tax_after_credits: "0"
      ca-on/ontario_surtax: "0"
      ca-on/ontario_tax_with_surtax: "0"
      ca-on/dividends_amount_a: "0"
      ca-on/dividends_amount_b: "0"
      ca-on/other_dividends_credit: "0"
      ca-on/dividends_amount_a_less_b: "0"
      ca-on/eligible_dividends_credit: "0"
      ca-on/dividend_tax_credit: "0"
      ca-on/ontario_tax_before_dividend_credit: "0"
      ca-on/ontario_tax_less_dividend_credit: "0"
      ca-on/dividend_credit_from_line_57: "0"
      ca-on/ontario_tax_after_dividend_credit: "0"
      ca-on/tax_reduction_basic: "294.00"
      ca-on/tax_reduction_for_children: "0"
      ca-on/tax_reduction_for_dependants: "0"
      ca-on/tax_reduction_amounts: "294.00"
      ca-on/ontario_tax_reduction: "588.00"
      ca-on/ontario_tax_after_reduction: "0"
      ca-on/lift_credit_before_maximum: "505"
      ca-on/lift_maximum_credit: "505"
      ca-on/lift_reduction: "0"
      ca-on/lift_credit: "505"
      ca-on/ontario_tax_after_lift_credit: "0"
      ca-on/community_food_program_credit: "0"
      ca-on/ontario_tax_after_food_credit: "0"
      ca-on/ontario_health_premium: "0"
      ca-on/ontario_tax: "0"
      ca/itc_recapture_at_15_percent: "0"
      ca/itc_recapture_at_20_percent: "0"
      ca/itc_recapture: "0"
      ca/federal_tax_with_itc_recapture: "0"
      ca/political_credit_before_maximum: "0"
      ca/political_credit: "0"
      ca/labour_sponsored_funds_credit_before_maximum: "0"
      ca/labour_sponsored_funds_credit: "0"
      ca/credits_against_federal_tax: "0"
      ca/federal_tax_less_credits: "0"
      ca/resp_aips_contributions_counted: "0"
      ca/resp_aips_lifetime_limit: "50000"
      ca/resp_aips_limit_remaining: "50000"
      ca/resp_aips_reduction: "0"
      ca/resp_aips_subject_to_tax: "0"
      ca/resp_aips_part_a_tax: "0"
      ca/resp_aips_part_b_tax: "0"
      ca/resp_aips_additional_tax: "0"
      ca/special_taxes: "0"
      ca/net_federal_tax: "0"
      ca/total_payable: "0"
      ca/working_income: "10000"
      ca/adjusted_family_net_income: "9935.00"
      ca/cwb_before_reduction_without_dependant: "1633"
      ca/cwb_reduction_without_dependant: "0"
      ca/canada_workers_benefit_without_dependant: "1633"
      ca/cwb_before_reduction_with_dependant: "1890.00"
      ca/cwb_reduction_with_dependant: "0"
      ca/canada_workers_benefit_with_dependant: "1890.00"
      ca/canada_workers_benefit: "1633"
      ca-on/fertility_credit_before_maximum: "0"
      ca-on/fertility_credit: "0"
      ca-on/care_adjusted_income: "9935.00"
      ca-on/care_family_adjusted_income: "9935.00"
      ca-on/care_credit_percentage: "0.75"
      ca-on/care_credit: "0"
      ca-on/seniors_care_before_maximum: "0.00"
      ca-on/seniors_care_amount: "0.00"
      ca-on/seniors_care_family_net_income: "9935.00"
      ca-on/seniors_care_base_amount: "35000.00"
      ca-on/seniors_care_income_over_base: "0"
      ca-on/seniors_care_reduction: "0.00"
      ca-on/seniors_care_before_claim: "0"
      ca-on/seniors_care_credit: "0"
      ca-on/applies_for_energy_and_property_tax_credit: "0"
      ca-on/applies_for_northern_energy_credit: "0"
      ca-on/chooses_single_benefit_payment: "0"
      ca-on/applies_for_senior_homeowners_grant: "0"
      ca-on/separate_residences_for_medical_reasons: "0"
      ca-on/lived_in_student_residence: "0"
      ca-on/rent_paid: "0"
      ca-on/property_tax_paid: "0"
      ca-on/reserve_home_energy_costs: "0"
      ca-on/public_long_term_care_paid: "0"
      ca-on/seniors_transit_amount_paid_checked: "0"
      ca-on/seniors_transit_credit: "0"
      ca-on/political_credit_before_maximum: "0"
      ca-on/political_credit: "0"
      ca-on/flow_through_share_expenses: "0"
      ca-on/flow_through_share_credit: "0"
      ca-on/ontario_credits_subtotal: "0"
      ca-on/coop_education_payroll_threshold: "400000.00"
      ca-on/coop_education_payroll_over_threshold: "0"
      ca-on/coop_education_payroll_range: "200000.00"
      ca-on/coop_education_phase_out_share: "0"
      ca-on/coop_education_full_share: "1.00"
      ca-on/coop_education_remaining_share: "1.00"
      ca-on/coop_education_placement_count: "0"
      ca-on/coop_education_credit: "0"
      ca-on/ontario_credits: "0"
      ca/provincial_credits: "0"
      ca/medical_supplement_working_income: "10000"
      ca/medical_supplement_line_6: "9935.00"
      ca/medical_supplement_line_8: "0"
      ca/medical_supplement_line_16: "0"
      ca/refundable_medical_expense_supplement: "0"
      ca/total_credits: "2133"
      ca/refund_or_balance_owing: "-2133"
      ca/educator_supplies_expenses_at_most_maximum: "0"
      ca/educator_school_supply_credit: "0"
      ca/refund: "2133"
      ca-on/refund_before_donation: "2133"
      ca-on/net_refund: "2133"
      ca/amt_basic_federal_tax: "-1181.85"
      ca/amt_federal_surtax_at_48_percent: "-567.29"
      ca/amt_regular_net_federal_tax_payable: "0"
      ca/amt_special_foreign_tax_credit: "0"
      ca/amt_alternative_minimum_tax_payable: "0"
      ca/amt_federal_tax_payable_under_minimum_tax: "0"
      ca/amt_carryover_available_for_2026: "0"
  ca/schedule_8:
    - ca/cpp_base_contributions: "321.75"
      ca/cpp_first_additional_contributions: "65.00"
      ca/cpp_second_additional_contributions: "0"
      ca/cpp_enhanced_contributions: "65.00"
      ca/cpp_required_base_and_first_additional_contributions: "386.75"
      ca/cpp_part_5_line_57: "321.75"
      ca/cpp_part_5_line_69: "65.00"
  ca/t776:
    - ca/short_term_rental_gross_rents: "0"
      ca/rental_gross_rents: "0"
      ca/gross_rental_income: "0"
      ca/rental_total_expenses: "0"
      ca/rental_personal_portion: "0"
      ca/rental_short_term_portion: "0"
      ca/rental_non_compliant_expenses: "0"
      ca/rental_expenses_less_personal_portion: "0"
      ca/rental_deductible_expenses: "0"
      ca/rental_net_income_before_adjustments: "0"
      ca/rental_net_income_share: "0"
      ca/rental_net_income_after_coowner_expenses: "0"
      ca/rental_net_income_with_recapture: "0"
      ca/rental_net_income_after_terminal_loss: "0"
      ca/rental_net_income_after_cca: "0"
      ca/rental_partner_share_with_rebate: "0"
      ca/rental_partnership_net_income: "0"
      ca/rental_closing_ucc: []
      ca/rental_non_compliant_cca: "0"
      ca/short_term_rental_non_compliant_cca_by_class: []
"""


def test_the_returns_directory_holds_at_least_one_return() -> None:
    assert WorkedReturn.discover(RETURNS)


def test_return_q_claims_two_infirm_dependants_on_line_30450() -> None:
    path = RETURNS / "2025_return_q.yaml"
    build_tax_computation()  # registers the catalogs the loader resolves through
    worked = WorkedReturn.load(path, ArtifactRegistry.shared())

    (dependants,) = [a for a in worked.inputs if a.kind.identifier == "ca/infirm_dependants"]
    assert [record[DEPENDANT_NET_INCOME] for record in dependants.value.records] == [
        Decimal("5000"),
        Decimal("25000"),
    ]
    (caregiver,) = [a for a in worked.expected if a.kind.identifier == "ca/caregiver_amount"]
    assert caregiver.value == Decimal("12399.00")
    check(path)


def test_return_w_claims_two_ontario_caregiver_dependants_on_line_58185() -> None:
    path = RETURNS / "2025_return_w.yaml"
    build_tax_computation()  # registers the catalogs the loader resolves through
    worked = WorkedReturn.load(path, ArtifactRegistry.shared())

    (dependants,) = [a for a in worked.inputs if a.kind.identifier == "ca-on/caregiver_dependants"]
    assert [
        (record[DEPENDANT_NET_INCOME], record[CLAIMED_AS_ELIGIBLE_DEPENDANT])
        for record in dependants.value.records
    ] == [(Decimal("5000"), 0), (Decimal("25000"), 0)]
    (caregiver,) = [a for a in worked.expected if a.kind.identifier == "ca-on/caregiver_amount"]
    assert caregiver.value == Decimal("7570.00")
    check(path)


def test_return_x_claims_one_dependant_with_a_disability_on_line_31800() -> None:
    path = RETURNS / "2025_return_ab.yaml"
    build_tax_computation()  # registers the catalogs the loader resolves through
    worked = WorkedReturn.load(path, ArtifactRegistry.shared())

    (dependants,) = [a for a in worked.inputs if a.kind.identifier == "ca/disability_dependants"]
    (dependant,) = dependants.value.records
    assert dependant[DEPENDANT_UNDER_18] == 0
    assert dependant[DEPENDANT_CARE_EXPENSES] == Decimal("0")
    assert dependant[DEPENDANT_CREDIT_AMOUNTS] == Decimal("16129")
    assert dependant[DEPENDANT_TAXABLE_INCOME] == Decimal("20000")
    (transferred,) = [
        a for a in worked.expected if a.kind.identifier == "ca/disability_transferred_amount"
    ]
    assert transferred.value == Decimal("6267.00")
    check(path)


def test_return_ab_claims_the_same_dependant_on_line_58480() -> None:
    path = RETURNS / "2025_return_ab.yaml"
    build_tax_computation()  # registers the catalogs the loader resolves through
    worked = WorkedReturn.load(path, ArtifactRegistry.shared())

    (dependants,) = [a for a in worked.inputs if a.kind.identifier == "ca-on/disability_dependants"]
    (dependant,) = dependants.value.records
    assert dependant[DEPENDANT_UNDER_18] == 0
    assert dependant[DEPENDANT_CARE_EXPENSES] == Decimal("0")
    assert dependant[DEPENDANT_ON428_LINE_28] == Decimal("15000")
    assert dependant[DEPENDANT_TAXABLE_INCOME] == Decimal("20000")
    (transferred,) = [
        a for a in worked.expected if a.kind.identifier == "ca-on/disability_transferred_amount"
    ]
    assert transferred.value == Decimal("5298.00")
    check(path)


def test_return_aa_has_a_spouse_at_year_end_and_takes_the_lift_credit_from_part_b() -> None:
    path = RETURNS / "2025_return_aa.yaml"
    build_tax_computation()  # registers the catalogs the loader resolves through
    worked = WorkedReturn.load(path, ArtifactRegistry.shared())

    (at_year_end,) = [
        a
        for a in worked.inputs
        if a.kind.identifier == "ca/spouse_or_common_law_partner_on_december_31"
    ]
    assert at_year_end.value == 1
    (spouse_income,) = [
        a for a in worked.inputs if a.kind.identifier == "ca/spouse_net_income_before_adjustments"
    ]
    assert spouse_income.value == Decimal("50000")
    (credit,) = [a for a in worked.expected if a.kind.identifier == "ca-on/lift_credit"]
    assert credit.value == Decimal("375.00")
    check(path)


def test_return_ae_claims_the_federal_political_contribution_credit_on_line_41000() -> None:
    path = RETURNS / "2025_return_ae.yaml"
    build_tax_computation()  # registers the catalogs the loader resolves through
    worked = WorkedReturn.load(path, ArtifactRegistry.shared())

    (contributions,) = [
        a for a in worked.inputs if a.kind.identifier == "ca/political_contributions"
    ]
    assert contributions.value == Decimal("1000")
    (credit,) = [a for a in worked.expected if a.kind.identifier == "ca/political_credit"]
    assert credit.value == Decimal("558.33")
    check(path)


def test_return_x_claims_two_other_dependants_medical_expenses_on_line_33199() -> None:
    path = RETURNS / "2025_return_x.yaml"
    build_tax_computation()  # registers the catalogs the loader resolves through
    worked = WorkedReturn.load(path, ArtifactRegistry.shared())

    (dependants,) = [a for a in worked.inputs if a.kind.identifier == "ca/other_dependants"]
    assert [
        (record[OTHER_DEPENDANT_MEDICAL_EXPENSES], record[DEPENDANT_NET_INCOME])
        for record in dependants.value.records
    ] == [(Decimal("3000"), Decimal("10000")), (Decimal("1000"), Decimal("40000"))]
    (own,) = [a for a in worked.inputs if a.kind.identifier == "ca/medical_expenses"]
    assert own.value == Decimal("4500")
    (other,) = [a for a in worked.expected if a.kind.identifier == "ca/other_dependants_medical"]
    assert other.value == Decimal("2700.00")
    (claim,) = [a for a in worked.expected if a.kind.identifier == "ca/medical_claim"]
    assert claim.value == Decimal("5773.35")
    # ON428 line 42 (line 58729) and line 43 (line 58769), over the same list and expenses.
    (ontario_other,) = [
        a for a in worked.expected if a.kind.identifier == "ca-on/other_dependants_medical"
    ]
    assert ontario_other.value == Decimal("2700.00")
    (ontario_claim,) = [a for a in worked.expected if a.kind.identifier == "ca-on/medical_claim"]
    assert ontario_claim.value == Decimal("5773.35")
    (ontario_amounts,) = [
        a for a in worked.expected if a.kind.identifier == "ca-on/non_refundable_credit_amounts"
    ]
    assert ontario_amounts.value == Decimal("21510.30")
    (refund,) = [a for a in worked.expected if a.kind.identifier == "ca/refund_or_balance_owing"]
    assert refund.value == Decimal("-814.48")
    # T1 line 154 (line 45200): the Federal Worksheet's line 16 over the medical claim above.
    (supplement,) = [
        a
        for a in worked.expected
        if a.kind.identifier == "ca/refundable_medical_expense_supplement"
    ]
    assert supplement.value == Decimal("730.29")


def test_return_af_claims_net_capital_losses_of_other_years_on_line_25300() -> None:
    path = RETURNS / "2025_return_af.yaml"
    build_tax_computation()  # registers the catalogs the loader resolves through
    worked = load(path)

    inputs = {a.kind.identifier: a.value for a in worked.inputs}
    (shares,) = [a for a in worked.inputs if a.kind.identifier == "ca/share_dispositions"]
    (row,) = shares.value.records
    assert row[DISPOSITION_PROCEEDS] == Decimal("5000")
    assert row[DISPOSITION_ADJUSTED_COST_BASE] == Decimal("0")
    assert row[DISPOSITION_OUTLAYS] == Decimal("0")
    assert "ca/capital_gain" not in inputs
    assert inputs["ca/unapplied_net_capital_losses_1985_to_1987"] == Decimal("0")
    assert inputs["ca/unapplied_net_capital_losses_1988_and_1989"] == Decimal("0")
    assert inputs["ca/unapplied_net_capital_losses_1990_to_1999"] == Decimal("3000")
    assert inputs["ca/unapplied_net_capital_losses_2001_to_2024"] == Decimal("1000")
    assert inputs["ca/net_capital_losses_claimed"] == Decimal("2500")
    expected = {a.kind.identifier: a.value for a in worked.expected}
    assert expected["ca/taxable_capital_gains"] == Decimal("2500.00")
    assert expected["ca/adjusted_gross_capital_losses_1990_to_1999"] == Decimal("2000.00")
    assert expected["ca/adjusted_gross_capital_losses_2001_to_2024"] == Decimal("1000.00")
    assert expected["ca/total_adjusted_net_capital_losses"] == Decimal("3000.00")
    assert expected["ca/net_capital_losses_available_to_claim"] == Decimal("2500.00")
    assert expected["ca/net_capital_losses_of_other_years"] == Decimal("2500")
    assert expected["ca/adjusted_losses_applied_1990_to_1999"] == Decimal("2000.00")
    assert expected["ca/adjusted_losses_applied_2001_to_2024"] == Decimal("500.00")
    assert expected["ca/net_capital_loss_balance_1990_to_1999"] == Decimal("0.00")
    assert expected["ca/net_capital_loss_balance_2001_to_2024"] == Decimal("500.00")
    assert expected["ca/deductions_from_net_income"] == Decimal("2500")
    assert expected["ca/net_income"] == Decimal("50055.00")
    assert expected["ca/taxable_income"] == Decimal("47555.00")
    check(path)


def test_return_ag_claims_the_ontario_seniors_care_at_home_credit_on_line_63095() -> None:
    path = RETURNS / "2025_return_ag.yaml"
    build_tax_computation()  # registers the catalogs the loader resolves through
    worked = WorkedReturn.load(path, ArtifactRegistry.shared())

    (claims,) = [
        a for a in worked.inputs if a.kind.identifier == "ca-on/claims_seniors_care_credit"
    ]
    assert claims.value == 1
    (spouse,) = [a for a in worked.inputs if a.kind.identifier == "ca/spouse_net_income"]
    assert spouse.value == Decimal("10000")
    # ON479 line 3 is ON428 line 58769, 4000.00; lines 5, 8, 10, 12 and 13 follow from it.
    (medical,) = [a for a in worked.expected if a.kind.identifier == "ca-on/medical_claim"]
    assert medical.value == Decimal("4000.00")
    (line_5,) = [a for a in worked.expected if a.kind.identifier == "ca-on/seniors_care_amount"]
    assert line_5.value == Decimal("1000.00")
    (line_8,) = [
        a for a in worked.expected if a.kind.identifier == "ca-on/seniors_care_family_net_income"
    ]
    assert line_8.value == Decimal("40000.00")
    (line_12,) = [a for a in worked.expected if a.kind.identifier == "ca-on/seniors_care_reduction"]
    assert line_12.value == Decimal("250.00")
    (line_13,) = [a for a in worked.expected if a.kind.identifier == "ca-on/seniors_care_credit"]
    assert line_13.value == Decimal("750.00")
    (credits,) = [a for a in worked.expected if a.kind.identifier == "ca-on/ontario_credits"]
    assert credits.value == Decimal("750.00")
    (refund,) = [a for a in worked.expected if a.kind.identifier == "ca/refund_or_balance_owing"]
    assert refund.value == Decimal("-3450.00")
    check(path)


def test_return_y_claims_the_care_credit_with_a_supporting_person_on_line_63050() -> None:
    path = RETURNS / "2025_return_y.yaml"
    build_tax_computation()  # registers the catalogs the loader resolves through
    worked = WorkedReturn.load(path, ArtifactRegistry.shared())

    inputs = {a.kind.identifier: a.value for a in worked.inputs}
    assert inputs["ca-on/care_supporting_persons_adjusted_income"] == Decimal("30000")
    expected = {a.kind.identifier: a.value for a in worked.expected}
    # Schedule ON479-A: line 4 is 54,435.00 + 5,000, line 5 adds the supporting person's 30,000,
    # line 7 is the 33% row, and line 8 is 5,000 x 33%.
    assert expected["ca-on/care_adjusted_income"] == Decimal("59435.00")
    assert expected["ca-on/care_family_adjusted_income"] == Decimal("89435.00")
    assert expected["ca-on/care_credit_percentage"] == Rate(Decimal("0.33"))
    assert expected["ca-on/care_credit"] == Decimal("1650.00")
    assert expected["ca/refund_or_balance_owing"] == Decimal("-5409.31")
    check(path)


def test_return_ah_claims_the_refundable_medical_expense_supplement_on_line_45200() -> None:
    path = RETURNS / "2025_return_ah.yaml"
    build_tax_computation()  # registers the catalogs the loader resolves through
    worked = WorkedReturn.load(path, ArtifactRegistry.shared())

    inputs = {a.kind.identifier: a.value for a in worked.inputs}
    assert inputs["ca/employment_income"] == Decimal("4390")
    assert inputs["ca/medical_expenses"] == Decimal("6600")
    expected = {a.kind.identifier: a.value for a in worked.expected}
    # The working income is exactly the $4,390 the line asks for, so the gate passes line 16.
    assert expected["ca/medical_supplement_working_income"] == Decimal("4390")
    assert expected["ca/medical_supplement_line_8"] == Decimal("0")
    assert expected["ca/medical_supplement_line_14"] == Decimal("1500.00")
    assert expected["ca/medical_supplement_line_16"] == Decimal("1500.00")
    assert expected["ca/refundable_medical_expense_supplement"] == Decimal("1500.00")


def test_return_aj_applies_for_the_energy_and_property_tax_credit_on_form_on_ben() -> None:
    path = RETURNS / "2025_return_aj.yaml"
    build_tax_computation()  # registers the catalogs the loader resolves through
    worked = load(path)

    # Form ON-BEN line 61020 is ticked and line 61100 is the rent paid; the other tick boxes are
    # not ticked and the other Part A lines are $0. Each line is an input and, as entered, an
    # expected line.
    entered = {
        "ca-on/applies_for_energy_and_property_tax_credit": 1,
        "ca-on/applies_for_northern_energy_credit": 0,
        "ca-on/chooses_single_benefit_payment": 0,
        "ca-on/applies_for_senior_homeowners_grant": 0,
        "ca-on/separate_residences_for_medical_reasons": 0,
        "ca-on/lived_in_student_residence": 0,
        "ca-on/rent_paid": Decimal("14400.00"),
        "ca-on/property_tax_paid": Decimal("0"),
        "ca-on/reserve_home_energy_costs": Decimal("0"),
        "ca-on/public_long_term_care_paid": Decimal("0"),
    }
    for identifier, value in entered.items():
        (given,) = [a for a in worked.inputs if a.kind.identifier == identifier]
        assert given.value == value, identifier
        assert type(given.value) is type(value), identifier
        (carried,) = [a for a in worked.expected if a.kind.identifier == identifier]
        assert carried.value == value, identifier
    # Every other figure is Return B's: the application changes no computed line.
    (refund,) = [a for a in worked.expected if a.kind.identifier == "ca/refund_or_balance_owing"]
    assert refund.value == Decimal("-2402.96")
    (net_income,) = [a for a in worked.expected if a.kind.identifier == "ca/net_income"]
    assert net_income.value == Decimal("29735.00")

    check(path)


def test_return_ad_reports_rental_income_on_lines_12599_and_12600() -> None:
    path = RETURNS / "2025_return_ad.yaml"
    build_tax_computation()  # registers the catalogs the loader resolves through
    worked = WorkedReturn.load(path, ArtifactRegistry.shared())

    (statements,) = [a for a in worked.inputs if a.kind.identifier == "ca/t776_statements"]
    (statement,) = statements.value.records
    (properties,) = [
        value for kind, value in statement.items() if kind.identifier == "ca/rental_properties"
    ]
    assert len(properties.records) == 1
    expected = {a.kind.identifier: a.value for a in worked.expected}
    (worksheet,) = next(f for f in worked.form_expected if f.form == "ca/t776").instances
    lines = {a.kind.identifier: a.value for a in worksheet}
    # T776 line 8299 (on the statement's worksheet) is T1 line 12599 and line 9946 is T1 line
    # 12600.
    assert lines["ca/gross_rental_income"] == Decimal("24000.00")
    assert expected["ca/gross_rental_income"] == Decimal("24000")
    assert expected["ca/net_rental_income"] == Decimal("12000.00")
    assert expected["ca/total_income"] == Decimal("12000.00")
    check(path)


def test_return_ai_enters_the_taxable_gains_of_two_properties_on_line_15800() -> None:
    path = RETURNS / "2025_return_ai.yaml"
    build_tax_computation()  # registers the catalogs the loader resolves through
    worked = WorkedReturn.load(path, ArtifactRegistry.shared())

    (properties,) = [
        a for a in worked.inputs if a.kind.identifier == "ca/principal_residence_properties"
    ]
    first, second = properties.value.records
    assert first[RESIDENCE_YEARS_DESIGNATED_AFTER_1981] == 6
    assert first[RESIDENCE_YEARS_DESIGNATED_1972_TO_1981] == 0
    assert first[RESIDENCE_YEARS_OWNED_AFTER_1981] == 10
    assert first[RESIDENCE_YEARS_OWNED_1972_TO_1981] == 0
    assert first[RESIDENCE_PROCEEDS] == Decimal("400000.00")
    assert first[RESIDENCE_OUTLAYS] == Decimal("5000.00")
    assert first[RESIDENCE_ADJUSTED_COST_BASE] == Decimal("95000.00")
    assert first[RESIDENCE_PLUS_ONE_YEAR] == 1
    assert second[RESIDENCE_YEARS_DESIGNATED_AFTER_1981] == 1
    assert second[RESIDENCE_YEARS_OWNED_AFTER_1981] == 6
    assert second[RESIDENCE_PROCEEDS] == Decimal("250000.00")
    assert second[RESIDENCE_OUTLAYS] == Decimal("0.00")
    assert second[RESIDENCE_ADJUSTED_COST_BASE] == Decimal("180000.00")
    assert second[RESIDENCE_PLUS_ONE_YEAR] == 1
    assert first[RESIDENCE_PART_2_APPLIES] == 0
    assert second[RESIDENCE_PART_2_APPLIES] == 0
    assert first[RESIDENCE_FMV_DEC_31_1981] == Decimal("0.00")
    assert second[RESIDENCE_COST_BASE_ADJUSTMENTS_AFTER_1981] == Decimal("0.00")
    expected = {a.kind.identifier: a.value for a in worked.expected}
    # T2091(IND) line 54 of each form: 90000.00 and 46666.67, entered on Schedule 3 line 15800.
    assert expected["ca/principal_residence_gain"] == Decimal("136666.67")
    assert expected["ca/personal_use_property_gain"] == Decimal("136666.67")
    assert expected["ca/taxable_capital_gains"] == Decimal("68333.34")
    check(path)


def test_a_new_file_is_a_new_worked_return_without_a_test_change(tmp_path: Path) -> None:
    (tmp_path / "2025_low_income.yaml").write_text(LOW_INCOME)
    (tmp_path / "2025_low_income_cents.yaml").write_text(
        LOW_INCOME.replace('"10000"', '"10000.00"')
    )

    found = WorkedReturn.discover(tmp_path)

    assert [path.stem for path in found] == ["2025_low_income", "2025_low_income_cents"]
    for path in found:
        check(path)


def test_a_wrong_expected_amount_fails_naming_the_file_and_line(tmp_path: Path) -> None:
    path = tmp_path / "wrong.yaml"
    path.write_text(LOW_INCOME.replace('"501.72"', '"501.73"'))

    with pytest.raises(
        AssertionError, match=r"wrong\.yaml: ca-on/return, instance 1: ca-on/ontario_basic_tax"
    ):
        check(path)


def test_a_line_and_an_input_left_out_that_are_blank_pass(tmp_path: Path) -> None:
    text = LOW_INCOME.replace("  ca/share_dispositions: []\n", "").replace(
        '      ca/taxable_dividends_other_than_eligible: "0"\n', ""
    )
    assert text != LOW_INCOME
    path = tmp_path / "blank.yaml"
    path.write_text(text)

    check(path)


def test_a_line_left_out_that_fires_fails_naming_the_file_and_line(tmp_path: Path) -> None:
    path = tmp_path / "partial.yaml"
    path.write_text(LOW_INCOME.replace('      ca/refund_or_balance_owing: "-2133"\n', ""))

    with pytest.raises(
        AssertionError, match=r"partial\.yaml: ca-on/return, instance 1: ca/refund_or_balance_owing"
    ):
        check(path)


# A made-up return with a form: two rentals, each with its own lines to check. A form's name under
# `expected` lists, per instance in order, the lines of that instance's worksheet; the return's own
# form has the one. Nothing here is a real figure.
RENTALS_RETURN = """\
jurisdiction: EX-ON
tax_year: 2025
description: Two made-up rentals, a net income of 10000 and of 4000.
sources:
  - Made up for the tests of the mechanism.
inputs:
  ex/rentals:
    - ex/gross_rent: "12000"
      ex/expenses: "2000"
      ex/units: []
    - ex/gross_rent: "5000"
      ex/expenses: "1000"
      ex/units:
        - ex/unit_amount: "1"
expected:
  ex-on/return:
    - ex/total_net_income: "14000"
  ex/rental:
    - ex/net_income: "10000"
      ex/units_doubled: []
    - ex/net_income: "4000"
      ex/units_doubled:
        - ex/unit_amount: "2"
"""


def with_outputs(manifest: Manifest, outputs: tuple[str, ...]) -> Manifest:
    """`manifest` with the default form (the first) exporting only `outputs`, and no count."""
    default, *others = manifest.forms
    kept = tuple(selection for selection in default.capabilities if selection != COUNT_DOUBLED)
    return replace(manifest, forms=(replace(default, exports=outputs, capabilities=kept), *others))


def check_rentals(tmp_path: Path, text: str) -> None:
    """Load `text` as a worked return of the made-up rental manifest and check it."""
    artifacts = artifact_registry()
    manifest = with_outputs(rental_manifest(), ("ex/total_net_income",))
    path = tmp_path / "rentals.yaml"
    path.write_text(text)
    worked = load(path, manifest, artifacts)

    check_against(worked, service(manifest, artifacts))


def test_the_lines_of_each_instance_are_checked_on_that_instances_worksheet(
    tmp_path: Path,
) -> None:
    check_rentals(tmp_path, RENTALS_RETURN)


def test_a_wrong_line_in_the_second_instance_fails_naming_the_file_form_instance_and_line(
    tmp_path: Path,
) -> None:
    text = RENTALS_RETURN.replace('ex/net_income: "4000"', 'ex/net_income: "4001"')

    with pytest.raises(
        AssertionError, match=r"rentals\.yaml: ex/rental, instance 2: ex/net_income"
    ):
        check_rentals(tmp_path, text)


def test_the_first_instances_figure_is_not_accepted_for_the_second(tmp_path: Path) -> None:
    text = RENTALS_RETURN.replace('ex/net_income: "4000"', 'ex/net_income: "10000"')

    with pytest.raises(AssertionError, match=r"instance 2: ex/net_income"):
        check_rentals(tmp_path, text)


def test_a_wrong_nested_list_in_an_instance_fails_naming_the_line(tmp_path: Path) -> None:
    text = RENTALS_RETURN.replace('ex/unit_amount: "2"', 'ex/unit_amount: "3"')

    with pytest.raises(AssertionError, match=r"instance 2: ex/units_doubled"):
        check_rentals(tmp_path, text)


def test_the_returns_own_lines_are_checked_when_a_form_has_lines_too(tmp_path: Path) -> None:
    text = RENTALS_RETURN.replace('ex/total_net_income: "14000"', 'ex/total_net_income: "13999"')

    with pytest.raises(
        AssertionError, match=r"rentals\.yaml: ex-on/return, instance 1: ex/total_net_income"
    ):
        check_rentals(tmp_path, text)


def test_an_entry_for_each_instance_is_required(tmp_path: Path) -> None:
    text = RENTALS_RETURN.replace(
        '    - ex/net_income: "4000"\n      ex/units_doubled:\n        - ex/unit_amount: "2"\n', ""
    )
    assert text != RENTALS_RETURN

    with pytest.raises(
        WorkedReturnError, match=r"rentals\.yaml: expected: 'ex/rental' has 1 entry"
    ):
        check_rentals(tmp_path, text)


RENTAL_RETURN = """\
jurisdiction: EX-ON
tax_year: 2025
description: One made-up rental, given as the one instance of the rental form.
sources:
  - Made up for the tests of the mechanism.
inputs:
  ex/rentals:
    - ex/gross_rent: "12000"
      ex/expenses: "2000"
      ex/units:
        - ex/unit_amount: "1"
expected:
  ex-on/return:
    - ex/total_net_income: "10000"
  ex/rental:
    - ex/net_income: "10000"
      ex/units_doubled:
        - ex/unit_amount: "2"
"""


def test_a_return_with_one_instance_loads_after_the_blanks_are_filled(tmp_path: Path) -> None:
    artifacts = artifact_registry()
    manifest = with_outputs(rental_manifest(), ("ex/total_net_income",))
    path = tmp_path / "rental.yaml"
    path.write_text(RENTAL_RETURN)

    worked = load(path, manifest, artifacts)

    (instances,) = (a for a in worked.inputs if a.kind.identifier == "ex/rentals")
    assert len(instances.value.records) == 1
    assert [a.kind.identifier for a in worked.inputs] == ["ex/rentals"]
    check_against(worked, service(manifest, artifacts))
