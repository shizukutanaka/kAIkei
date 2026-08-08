from datetime import date
from decimal import Decimal

import pytest

from app.services.audit_detection import (
    BENFORD_CHI2_CRITICAL,
    BENFORD_MAD_CLOSE,
    JournalSnapshot,
    benford_chi_squared,
    benford_mad,
    mad_conformity,
    detect_benford_deviation,
    detect_period_end_concentration,
    first_significant_digit,
    detect_backdated,
    detect_duplicate,
    detect_high_amount,
    detect_round_amount,
    detect_sod_conflict,
    detect_weekend_entry,
    highest_risk,
    run_rules,
)


def _snap(**kw):
    base = dict(
        journal_header_id="jh-1",
        transaction_date=date(2026, 4, 15),  # 水曜日
        created_on=date(2026, 4, 15),
        total_amount=Decimal("50000"),
        created_by="u1",
        approved_by="u2",
        summary="",
        counterparty="",
    )
    base.update(kw)
    return JournalSnapshot(**base)


class TestHighAmount:
    def test_flags_at_or_above_threshold(self):
        assert detect_high_amount(_snap(total_amount=Decimal("1000000"))) is not None

    def test_ignores_below_threshold(self):
        assert detect_high_amount(_snap(total_amount=Decimal("999999"))) is None

    def test_risk_is_high(self):
        f = detect_high_amount(_snap(total_amount=Decimal("2000000")))
        assert f.risk_level == "high"


class TestRoundAmount:
    def test_flags_multiple_of_modulus(self):
        assert detect_round_amount(_snap(total_amount=Decimal("300000"))) is not None

    def test_ignores_non_round(self):
        assert detect_round_amount(_snap(total_amount=Decimal("312500"))) is None

    def test_ignores_small_round(self):
        assert detect_round_amount(_snap(total_amount=Decimal("50000"))) is None


class TestWeekendEntry:
    def test_saturday_flagged(self):
        assert detect_weekend_entry(_snap(transaction_date=date(2026, 4, 18))) is not None  # 土

    def test_sunday_flagged(self):
        assert detect_weekend_entry(_snap(transaction_date=date(2026, 4, 19))) is not None  # 日

    def test_weekday_not_flagged(self):
        assert detect_weekend_entry(_snap(transaction_date=date(2026, 4, 15))) is None  # 水


class TestBackdated:
    def test_flags_beyond_lag(self):
        f = detect_backdated(
            _snap(transaction_date=date(2026, 1, 1), created_on=date(2026, 4, 15)),
            max_lag_days=30,
        )
        assert f is not None and f.details["lag_days"] > 30

    def test_within_lag_ok(self):
        assert detect_backdated(
            _snap(transaction_date=date(2026, 4, 1), created_on=date(2026, 4, 15)),
            max_lag_days=30,
        ) is None

    def test_future_transaction_not_backdated(self):
        assert detect_backdated(
            _snap(transaction_date=date(2026, 4, 20), created_on=date(2026, 4, 15))
        ) is None


class TestSodConflict:
    def test_same_creator_and_approver_flagged(self):
        assert detect_sod_conflict(_snap(created_by="u1", approved_by="u1")) is not None

    def test_different_ok(self):
        assert detect_sod_conflict(_snap(created_by="u1", approved_by="u2")) is None

    def test_no_approver_ok(self):
        assert detect_sod_conflict(_snap(created_by="u1", approved_by=None)) is None


class TestDuplicate:
    def test_detects_same_amount_date_counterparty(self):
        a = _snap(journal_header_id="a", total_amount=Decimal("10000"), counterparty="カイケイ")
        b = _snap(journal_header_id="b", total_amount=Decimal("10000"), counterparty="カイケイ")
        assert detect_duplicate(a, [a, b]) is not None

    def test_ignores_self(self):
        a = _snap(journal_header_id="a")
        assert detect_duplicate(a, [a]) is None

    def test_different_counterparty_not_duplicate(self):
        a = _snap(journal_header_id="a", counterparty="X")
        b = _snap(journal_header_id="b", counterparty="Y")
        assert detect_duplicate(a, [b]) is None


class TestRunRulesAndRisk:
    def test_clean_journal_no_findings(self):
        assert run_rules(_snap(created_by="u1", approved_by="u2")) == []

    def test_multiple_findings(self):
        # 高額 + 丸め + 休日 + SoD
        snap = _snap(
            total_amount=Decimal("2000000"),
            transaction_date=date(2026, 4, 18),  # 土
            created_by="u1",
            approved_by="u1",
        )
        cats = {f.category for f in run_rules(snap)}
        assert {"high_amount", "round_amount", "weekend_entry", "sod_conflict"} <= cats

    def test_highest_risk(self):
        snap = _snap(total_amount=Decimal("2000000"), created_by="u1", approved_by="u1")
        assert highest_risk(run_rules(snap)) == "high"

    def test_highest_risk_none_when_empty(self):
        assert highest_risk([]) is None

class TestFirstSignificantDigit:
    def test_basic(self):
        assert first_significant_digit(Decimal("532")) == 5
        assert first_significant_digit(Decimal("0.042")) == 4
        assert first_significant_digit(Decimal("-9100")) == 9

    def test_zero_is_none(self):
        assert first_significant_digit(Decimal("0")) is None


class TestBenford:
    def _benford_sample(self, n=100):
        """Benford分布に概ね従う金額列を生成する。"""
        import math
        amounts = []
        for d in range(1, 10):
            count = round(n * math.log10(1 + 1 / d))
            amounts.extend([Decimal(d) * 1000 + 17] * count)
        return amounts

    def test_insufficient_samples_returns_none(self):
        assert benford_chi_squared([Decimal("100")] * 10) is None
        assert detect_benford_deviation([Decimal("100")] * 10) is None

    def test_conforming_sample_not_flagged(self):
        assert detect_benford_deviation(self._benford_sample()) is None

    def test_uniform_digits_flagged(self):
        # 第1桁が1〜9に均等分布 → Benfordから大きく乖離
        amounts = [Decimal(d) * 1000 for d in range(1, 10)] * 12  # n=108
        finding = detect_benford_deviation(amounts)
        assert finding is not None
        assert finding.category == "benford_deviation"
        assert finding.details["chi_squared"] > BENFORD_CHI2_CRITICAL


class TestPeriodEndConcentration:
    def test_insufficient_samples_none(self):
        assert detect_period_end_concentration([date(2026, 4, 30)] * 10) is None

    def test_concentrated_flagged(self):
        # 20件中12件（60%）が月末3日間
        dates = [date(2026, 4, 29)] * 12 + [date(2026, 4, 10)] * 8
        finding = detect_period_end_concentration(dates)
        assert finding is not None
        assert finding.category == "period_end_concentration"

    def test_spread_not_flagged(self):
        dates = [date(2026, 4, 10)] * 15 + [date(2026, 4, 30)] * 5  # 25%
        assert detect_period_end_concentration(dates) is None

    def test_february_month_end(self):
        # 2月28日（平年月末）は月末3日間に含まれる
        dates = [date(2026, 2, 27)] * 15 + [date(2026, 2, 10)] * 5
        finding = detect_period_end_concentration(dates)
        assert finding is not None


class TestBenfordMad:
    """MAD（平均絶対偏差）による実務的有意性の判定（Nigrini 2012）。"""

    def _benford_amounts(self, n: int, shift: float = 0.0) -> list[Decimal]:
        """Benford分布に従う金額列。shift>0 で第1桁1→9へ比率をずらす。"""
        import math
        amounts: list[Decimal] = []
        for d in range(1, 10):
            ratio = math.log10(1 + 1 / d)
            if d == 1:
                ratio -= shift
            if d == 9:
                ratio += shift
            amounts.extend([Decimal(d) * 1000 + 17] * round(n * ratio))
        return amounts

    def test_mad_none_when_insufficient_samples(self):
        assert benford_mad([Decimal("100")] * 10) is None

    def test_conforming_sample_has_low_mad(self):
        mad, n = benford_mad(self._benford_amounts(900))
        assert mad < BENFORD_MAD_CLOSE
        assert mad_conformity(mad) == "close"

    def test_uniform_distribution_is_nonconformity(self):
        amounts = [Decimal(d) * 1000 for d in range(1, 10)] * 12
        mad, _ = benford_mad(amounts)
        assert mad_conformity(mad) == "nonconformity"

    def test_conformity_thresholds(self):
        assert mad_conformity(0.0) == "close"
        assert mad_conformity(0.0059) == "close"
        assert mad_conformity(0.006) == "acceptable"
        assert mad_conformity(0.0119) == "acceptable"
        assert mad_conformity(0.012) == "marginal"
        assert mad_conformity(0.0149) == "marginal"
        assert mad_conformity(0.015) == "nonconformity"

    def test_large_sample_tiny_deviation_is_not_flagged(self):
        """回帰: 大標本＋実務上無視できる乖離を誤検知しないこと。

        カイ二乗は標本サイズに比例するため、10万件規模では0.5ポイントの偏りでも
        χ²が閾値を大きく超える（excess power problem）。MAD併用で誤検知を防ぐ。
        """
        amounts = self._benford_amounts(100_000, shift=0.005)
        chi2, _ = benford_chi_squared(amounts)
        mad, _ = benford_mad(amounts)

        assert chi2 > BENFORD_CHI2_CRITICAL      # カイ二乗だけなら検知されてしまう
        assert mad_conformity(mad) == "close"    # 実務的には適合している
        assert detect_benford_deviation(amounts) is None  # 併用により検知されない

    def test_genuine_manipulation_still_flagged_at_large_sample(self):
        """大標本でも実務的に意味のある乖離は検知すること（見逃さない）。"""
        amounts = self._benford_amounts(100_000, shift=0.10)
        finding = detect_benford_deviation(amounts)
        assert finding is not None
        assert finding.details["mad_conformity"] == "nonconformity"
        assert finding.risk_level == "high"
