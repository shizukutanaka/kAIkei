from datetime import date

import pytest

from app.schemas.schemas import QualificationLossGenerateResponse
from app.services.qualification_loss import LossEmployee, QualificationLossService


def _employee(**kwargs) -> LossEmployee:
    base = {
        "insured_number": "1",
        "name": "山田太郎",
        "event_date": date(2025, 3, 31),
        "reason": "retirement",
    }
    base.update(kwargs)
    return LossEmployee(**base)


def test_month_end_retirement_charges_retirement_month_premium():
    result = QualificationLossService.compute_employee(_employee())

    assert result.loss_date == date(2025, 4, 1)
    assert (result.final_premium_year, result.final_premium_month) == (2025, 3)
    assert result.event_month_premium_charged is True


def test_retirement_before_month_end_stops_at_previous_month():
    result = QualificationLossService.compute_employee(_employee(event_date=date(2025, 3, 30)))

    assert result.loss_date == date(2025, 3, 31)
    assert (result.final_premium_year, result.final_premium_month) == (2025, 2)
    assert result.event_month_premium_charged is False


def test_december_month_end_retirement_crosses_year():
    result = QualificationLossService.compute_employee(_employee(event_date=date(2025, 12, 31)))

    assert result.loss_date == date(2026, 1, 1)
    assert (result.final_premium_year, result.final_premium_month) == (2025, 12)


def test_january_retirement_final_month_is_previous_december():
    result = QualificationLossService.compute_employee(_employee(event_date=date(2025, 1, 15)))

    assert result.loss_date == date(2025, 1, 16)
    assert (result.final_premium_year, result.final_premium_month) == (2024, 12)


def test_death_loss_date_is_next_day():
    result = QualificationLossService.compute_employee(
        _employee(reason="death", event_date=date(2025, 6, 10)),
    )

    assert result.loss_date == date(2025, 6, 11)
    assert (result.final_premium_year, result.final_premium_month) == (2025, 5)


def test_age_70_loss_date_is_day_before_birthday():
    result = QualificationLossService.compute_employee(
        _employee(reason="age_70", event_date=date(2025, 8, 1)),
    )

    assert result.loss_date == date(2025, 7, 31)
    assert (result.final_premium_year, result.final_premium_month) == (2025, 6)


def test_age_75_loss_date_is_birthday_itself():
    result = QualificationLossService.compute_employee(
        _employee(reason="age_75", event_date=date(2025, 8, 1)),
    )

    assert result.loss_date == date(2025, 8, 1)
    assert (result.final_premium_year, result.final_premium_month) == (2025, 7)


def test_same_month_acquisition_and_loss_charges_that_month():
    result = QualificationLossService.compute_employee(
        _employee(
            event_date=date(2025, 5, 20),
            qualification_date=date(2025, 5, 1),
        ),
    )

    assert result.loss_date == date(2025, 5, 21)
    assert result.same_month_acquisition_loss is True
    assert (result.final_premium_year, result.final_premium_month) == (2025, 5)
    assert result.event_month_premium_charged is True


def test_month_end_retirement_is_not_same_month_loss():
    result = QualificationLossService.compute_employee(
        _employee(event_date=date(2025, 5, 31), qualification_date=date(2025, 5, 1)),
    )

    assert result.loss_date == date(2025, 6, 1)
    assert result.same_month_acquisition_loss is False
    assert (result.final_premium_year, result.final_premium_month) == (2025, 5)


def test_over_70_employee_requires_notification_only_for_separation():
    retirement = QualificationLossService.compute_employee(_employee(is_over_70_employee=True))
    age_75 = QualificationLossService.compute_employee(
        _employee(reason="age_75", event_date=date(2025, 8, 1), is_over_70_employee=True),
    )

    assert retirement.requires_over70_notification is True
    assert age_75.requires_over70_notification is False


def test_generate_aggregates_and_builds_csv():
    result = QualificationLossService.generate(
        [
            _employee(),
            _employee(
                insured_number="2",
                name="佐藤花子",
                event_date=date(2025, 5, 20),
                qualification_date=date(2025, 5, 1),
            ),
        ],
    )

    assert result.employee_count == 2
    assert result.same_month_numbers == ["2"]
    lines = result.csv_text.strip().split("\n")
    assert lines[0].startswith("insured_number,name,reason")
    assert lines[1].startswith("1,山田太郎,retirement,2025-03-31,2025-04-01,2025-03,1,0,0")
    assert lines[2].startswith("2,佐藤花子,retirement,2025-05-20,2025-05-21,2025-05,1,1,0")


def test_response_schema_validates_service_result():
    result = QualificationLossService.generate([_employee()])

    response = QualificationLossGenerateResponse.model_validate(result)

    assert response.employee_count == 1
    assert response.results[0].loss_date == date(2025, 4, 1)


def test_unknown_reason_rejected():
    with pytest.raises(ValueError, match="unknown loss reason"):
        QualificationLossService.compute_employee(_employee(reason="unknown"))


def test_qualification_date_after_loss_date_rejected():
    with pytest.raises(ValueError, match="qualification_date"):
        QualificationLossService.compute_employee(
            _employee(event_date=date(2025, 5, 1), qualification_date=date(2025, 6, 1)),
        )


def test_blank_insured_number_rejected():
    with pytest.raises(ValueError, match="insured_number"):
        QualificationLossService.compute_employee(_employee(insured_number="  "))


def test_empty_employees_rejected():
    with pytest.raises(ValueError, match="must not be empty"):
        QualificationLossService.generate([])
