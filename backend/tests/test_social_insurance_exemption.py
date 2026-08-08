import pytest

from app.services.social_insurance_exemption import SocialInsuranceExemptionService


def test_maternity_month_end_exempt():
    result = SocialInsuranceExemptionService.check(
        leave_type="maternity", target="monthly", month_last_day_on_leave=True
    )
    assert result.exempt is True
    assert result.reason == "maternity_month_end_on_leave"


def test_maternity_not_month_end():
    result = SocialInsuranceExemptionService.check(
        leave_type="maternity", target="monthly", month_last_day_on_leave=False
    )
    assert result.exempt is False
    assert result.reason == "maternity_not_on_month_end"


def test_maternity_bonus_month_end_exempt():
    result = SocialInsuranceExemptionService.check(
        leave_type="maternity", target="bonus", month_last_day_on_leave=True
    )
    assert result.exempt is True


def test_childcare_monthly_month_end_exempt():
    result = SocialInsuranceExemptionService.check(
        leave_type="childcare", target="monthly", month_last_day_on_leave=True
    )
    assert result.exempt is True
    assert result.reason == "childcare_month_end_on_leave"


def test_childcare_monthly_14_days_exempt():
    result = SocialInsuranceExemptionService.check(
        leave_type="childcare", target="monthly", month_last_day_on_leave=False, days_on_leave_in_month=14
    )
    assert result.exempt is True
    assert result.reason == "childcare_14_days_or_more"


def test_childcare_monthly_13_days_not_exempt():
    result = SocialInsuranceExemptionService.check(
        leave_type="childcare", target="monthly", month_last_day_on_leave=False, days_on_leave_in_month=13
    )
    assert result.exempt is False
    assert result.reason == "childcare_monthly_not_exempt"


def test_childcare_bonus_over_one_month_exempt():
    result = SocialInsuranceExemptionService.check(
        leave_type="childcare", target="bonus", continuous_leave_over_one_month=True
    )
    assert result.exempt is True
    assert result.reason == "childcare_continuous_over_one_month"


def test_childcare_bonus_not_over_one_month():
    result = SocialInsuranceExemptionService.check(
        leave_type="childcare", target="bonus", continuous_leave_over_one_month=False
    )
    assert result.exempt is False
    assert result.reason == "childcare_bonus_not_over_one_month"


def test_unsupported_leave_type_raises():
    with pytest.raises(ValueError):
        SocialInsuranceExemptionService.check(leave_type="sick", target="monthly")


def test_negative_days_raises():
    with pytest.raises(ValueError):
        SocialInsuranceExemptionService.check(
            leave_type="childcare", target="monthly", days_on_leave_in_month=-1
        )
