"""事業所タイムゾーンでの日付・時刻。

勤務日・締め日・承認日時といった会計/労務上の日付は、**事業所の暦日**で判定しなければ
ならない。ところがサーバは通常UTCで動くため、`date.today()` や `datetime.now()` を
そのまま使うと日本（JST=UTC+9）の暦日とずれる。

具体的な実害（実測）:

    JST 07/01 08:00 の出勤打刻 → UTCでは 06/30 23:00
    → date.today() は 2026-06-30 を返し、**前日の勤務日として記録される**

JSTの 00:00〜09:00 に行われた打刻はすべて前日に付け替わるため、早番勤務は
勤務日を誤り、「本日はすでに出勤打刻済みです」の重複判定も誤った日境界で行われる。

またDBのDATETIME列はタイムゾーンを持たない（naive）ため、格納すべきなのは
**事業所の壁時計時刻**である。UTCの壁時計時刻を入れると表示が9時間ずれる。
そのため naive 列へ入れる際は `business_naive_now()` を用いる。

日本は1951年以降サマータイムを採用していないため固定オフセットで扱う。
別のタイムゾーンで運用する場合は BUSINESS_UTC_OFFSET_HOURS を変更する。
"""

from datetime import date, datetime, timedelta, timezone

# 事業所の標準時（既定: 日本標準時 UTC+9）。
BUSINESS_UTC_OFFSET_HOURS = 9
BUSINESS_TZ = timezone(timedelta(hours=BUSINESS_UTC_OFFSET_HOURS), "JST")


def business_now() -> datetime:
    """事業所タイムゾーンでの現在時刻（タイムゾーン付き）。"""
    return datetime.now(BUSINESS_TZ)


def business_today() -> date:
    """事業所タイムゾーンでの今日の日付。

    勤務日・締め日など「どの日の出来事か」を決める場面では必ずこちらを使う。
    """
    return business_now().date()


def business_naive_now() -> datetime:
    """事業所タイムゾーンの壁時計時刻を naive な datetime で返す。

    タイムゾーンを持たないDATETIME列へ格納する用途。UTCの時刻を入れると
    表示が事業所時刻から9時間ずれるため、格納前にこの関数で変換する。
    """
    return business_now().replace(tzinfo=None)
