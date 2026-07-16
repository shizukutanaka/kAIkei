"""電子帳簿保存法「スキャナ保存」の要件充足チェック。

紙で受領・作成した国税関係書類(請求書・領収書・契約書等)をスキャナ(スマホ・
デジカメ含む)で読み取り電子保存する場合の要件(電帳法4条3項、電帳法施行規則2条)。

入力期間の制限(次のいずれか):
  - 速やかに行う:       受領等からおおむね7営業日以内
  - 業務処理サイクル後: 最長2か月+おおむね7営業日以内(事務処理規程の備付けが前提)

解像度・階調:
  - 解像度200dpi以上(一般書類・重要書類とも)
  - 赤・緑・青それぞれ256階調(24ビットカラー)以上
    ※一般書類はグレースケール(白黒)保存も可

真実性:
  - 入力期間内にタイムスタンプ付与、または訂正・削除履歴が残る(訂正削除できない)
    クラウド等で入力期間内に保存

可視性:
  - 見読可能装置(14インチ以上カラー等)の備付け
  - 検索機能(取引年月日・取引金額・取引先の3項目、範囲指定、複合条件)
"""

from __future__ import annotations

from dataclasses import dataclass

MIN_RESOLUTION_DPI = 200
MIN_COLOR_GRADATION = 256

INPUT_PERIOD_PROMPT = "prompt"
INPUT_PERIOD_BUSINESS_CYCLE = "business_cycle"
PROMPT_LIMIT_BUSINESS_DAYS = 7
BUSINESS_CYCLE_LIMIT_DAYS = 67  # 最長2か月(約60日)+おおむね7営業日の目安


@dataclass(frozen=True)
class DenchouScannerCheckResult:
    resolution_met: bool
    color_met: bool
    input_period_met: bool
    authenticity_met: bool
    visibility_met: bool
    compliant: bool
    missing_requirements: tuple[str, ...]


class DenchouScannerService:
    """スキャナ保存の要件充足を判定する純粋サービス。"""

    @classmethod
    def check(
        cls,
        *,
        resolution_dpi: int,
        is_color: bool,
        is_general_document: bool,
        input_period_type: str,
        days_until_input: int,
        has_operational_rules: bool,
        has_timestamp: bool,
        has_correction_deletion_history: bool,
        has_display_device: bool,
        can_search_by_date: bool,
        can_search_by_amount: bool,
        can_search_by_counterparty: bool,
        can_search_by_range: bool,
        can_search_by_combination: bool,
    ) -> DenchouScannerCheckResult:
        if resolution_dpi <= 0:
            raise ValueError("resolution_dpi must be positive")
        if days_until_input < 0:
            raise ValueError("days_until_input must not be negative")
        if input_period_type not in (INPUT_PERIOD_PROMPT, INPUT_PERIOD_BUSINESS_CYCLE):
            raise ValueError(f"unsupported input_period_type: {input_period_type}")

        missing: list[str] = []

        resolution_met = resolution_dpi >= MIN_RESOLUTION_DPI
        if not resolution_met:
            missing.append("resolution")

        # 重要書類はカラー必須。一般書類はグレースケール可。
        color_met = is_color or is_general_document
        if not color_met:
            missing.append("color")

        if input_period_type == INPUT_PERIOD_PROMPT:
            input_period_met = days_until_input <= PROMPT_LIMIT_BUSINESS_DAYS
        else:
            # 業務処理サイクル後の方式は事務処理規程の備付けが前提。
            input_period_met = has_operational_rules and days_until_input <= BUSINESS_CYCLE_LIMIT_DAYS
        if not input_period_met:
            missing.append("input_period")

        authenticity_met = has_timestamp or has_correction_deletion_history
        if not authenticity_met:
            missing.append("authenticity")

        has_three_items = can_search_by_date and can_search_by_amount and can_search_by_counterparty
        search_met = has_three_items and can_search_by_range and can_search_by_combination
        if not search_met:
            missing.append("search")
        if not has_display_device:
            missing.append("display_device")

        visibility_met = has_display_device and search_met
        compliant = resolution_met and color_met and input_period_met and authenticity_met and visibility_met

        return DenchouScannerCheckResult(
            resolution_met=resolution_met,
            color_met=color_met,
            input_period_met=input_period_met,
            authenticity_met=authenticity_met,
            visibility_met=visibility_met,
            compliant=compliant,
            missing_requirements=tuple(missing),
        )
