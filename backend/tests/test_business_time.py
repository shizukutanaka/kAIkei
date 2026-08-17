"""事業所タイムゾーンの日付・時刻の回帰テスト。

サーバはUTCで動くため、`date.today()` をそのまま使うとJSTの暦日とずれる。
勤務日や締め日は事業所の暦日で決まるため、この差は実害になる（JST 00:00〜09:00 の
出勤打刻が前日の勤務日として記録されていた）。
"""

from datetime import datetime, timedelta, timezone

from app.core.business_time import (
    BUSINESS_TZ,
    BUSINESS_UTC_OFFSET_HOURS,
    business_naive_now,
    business_now,
    business_today,
)

UTC = timezone.utc


class TestBusinessTimezone:
    def test_offset_is_jst(self):
        assert BUSINESS_UTC_OFFSET_HOURS == 9
        assert BUSINESS_TZ.utcoffset(None) == timedelta(hours=9)

    def test_business_now_is_timezone_aware(self):
        assert business_now().tzinfo is not None

    def test_naive_now_has_no_tzinfo_but_is_business_wallclock(self):
        naive = business_naive_now()
        assert naive.tzinfo is None
        # UTCの壁時計ではなく事業所の壁時計であること（差は約9時間）。
        delta = naive - datetime.now(UTC).replace(tzinfo=None)
        assert timedelta(hours=8, minutes=55) < delta < timedelta(hours=9, minutes=5)

    def test_business_today_matches_business_now_date(self):
        assert business_today() == business_now().date()


class TestEarlyMorningDateBoundary:
    """回帰: JSTの早朝（00:00〜09:00）が前日に付け替わらないこと。"""

    def _utc_date(self, jst_dt: datetime):
        """従来実装（サーバUTCでの date.today()）が返していた日付。"""
        return jst_dt.astimezone(UTC).date()

    def _business_date(self, jst_dt: datetime):
        """事業所タイムゾーンでの暦日。"""
        return jst_dt.astimezone(BUSINESS_TZ).date()

    def test_early_morning_clock_in_would_have_been_previous_day(self):
        jst_8am = datetime(2026, 7, 1, 8, 0, tzinfo=BUSINESS_TZ)
        # 旧実装は前日を返していた（これがバグ）
        assert self._utc_date(jst_8am).isoformat() == "2026-06-30"
        # 事業所暦日では正しく当日
        assert self._business_date(jst_8am).isoformat() == "2026-07-01"

    def test_midnight_boundary(self):
        jst_midnight = datetime(2026, 7, 1, 0, 0, tzinfo=BUSINESS_TZ)
        assert self._utc_date(jst_midnight).isoformat() == "2026-06-30"
        assert self._business_date(jst_midnight).isoformat() == "2026-07-01"

    def test_after_nine_am_is_unaffected(self):
        # JST 09:00 以降はUTC日付と一致するため、従来も正しかった。
        for hour in (9, 12, 18, 23):
            jst = datetime(2026, 7, 1, hour, 0, tzinfo=BUSINESS_TZ)
            assert self._utc_date(jst) == self._business_date(jst)

    def test_month_end_boundary_shifts_fiscal_month(self):
        """月初の早朝打刻が前月末に付け替わらないこと（月次集計に影響する）。"""
        jst = datetime(2026, 8, 1, 7, 30, tzinfo=BUSINESS_TZ)
        assert self._utc_date(jst).month == 7      # 旧実装では前月
        assert self._business_date(jst).month == 8  # 事業所暦日では当月
