"""介護保険（第2号被保険者）の年齢判定。

40歳以上65歳未満が対象だが、満年齢に達するのは**誕生日の前日**
（年齢計算ニ関スル法律・民法143条）。そのため1日生まれの人は前月から
対象になる。この境界を間違えると1ヶ月分の徴収漏れ・過徴収になる。
"""
from datetime import date

import pytest

from app.services.social_insurance import care_insurance_applicable


@pytest.mark.parametrize(
    ("birth", "as_of", "expected", "why"),
    [
        # 4/1生まれは3/31に40歳に達する → 3月分から対象
        (date(1986, 4, 1), date(2026, 3, 31), True, "1日生まれは前月から対象"),
        (date(1986, 4, 2), date(2026, 3, 31), False, "2日生まれはまだ39歳"),
        (date(1986, 4, 2), date(2026, 4, 30), True, "翌月には40歳"),
        # 65歳到達で対象外
        (date(1961, 4, 1), date(2026, 3, 31), False, "65歳に達したら対象外"),
        (date(1961, 4, 2), date(2026, 3, 31), True, "まだ64歳"),
        # 明らかな範囲内/外
        (date(2000, 1, 1), date(2026, 4, 30), False, "26歳"),
        (date(1980, 1, 1), date(2026, 4, 30), True, "46歳"),
        (date(1940, 1, 1), date(2026, 4, 30), False, "86歳"),
    ],
)
def test_care_insurance_boundaries(birth, as_of, expected, why):
    assert care_insurance_applicable(birth, as_of) is expected, why


def test_unknown_birth_date_is_not_charged():
    """生年月日が無ければ徴収しない（誤徴収より徴収漏れを選ぶ）。"""
    assert care_insurance_applicable(None, date(2026, 4, 30)) is False
