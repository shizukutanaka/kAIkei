"""電子帳簿保存法「電子取引データ保存」の要件充足チェック。

電子取引(メール・EDI・Web等で授受した請求書/領収書等)のデータは、2024年1月以降
書面保存が認められず、以下の要件を満たしてデータ保存する必要がある(電帳法7条、
電帳法施行規則4条)。

真実性の確保(いずれか一つ):
  1. タイムスタンプが付された後に授受、または速やかにタイムスタンプを付与
  2. 訂正・削除の履歴が残る(または訂正・削除ができない)システムで授受・保存
  3. 正当な理由がない訂正・削除の防止に関する事務処理規程を備え付け

可視性の確保:
  - 見読可能装置(ディスプレイ・プリンタ等)の備付け
  - 検索機能(検索要件):
      (イ) 取引年月日・取引金額・取引先の3項目で検索できること
      (ロ) 日付または金額の範囲を指定して検索できること
      (ハ) 2以上の任意の記録項目を組み合わせて検索できること

検索要件の緩和(電帳法施行規則4条1項ただし書・国税庁一問一答):
  - 税務職員のダウンロードの求めに応じられる場合、(ロ)(ハ)は不要(3項目のみで可)
  - 基準期間の売上高が5,000万円以下、かつダウンロードの求めに応じられる場合は
    検索機能そのものが不要
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

SALES_WAIVER_THRESHOLD = Decimal("50000000")

SEARCH_LEVEL_WAIVED = "waived"
SEARCH_LEVEL_THREE_ITEMS_ONLY = "three_items_only"
SEARCH_LEVEL_FULL = "full"


@dataclass(frozen=True)
class DenchouElectronicCheckResult:
    authenticity_met: bool
    visibility_met: bool
    required_search_level: str
    search_requirement_met: bool
    compliant: bool
    missing_requirements: tuple[str, ...]


class DenchouElectronicService:
    """電子取引データ保存の要件充足を判定する純粋サービス。"""

    @classmethod
    def check(
        cls,
        *,
        has_timestamp: bool,
        has_correction_deletion_history: bool,
        has_operational_rules: bool,
        has_display_device: bool,
        can_search_by_date: bool,
        can_search_by_amount: bool,
        can_search_by_counterparty: bool,
        can_search_by_range: bool,
        can_search_by_combination: bool,
        base_period_sales: Decimal,
        can_provide_download: bool,
    ) -> DenchouElectronicCheckResult:
        if base_period_sales < 0:
            raise ValueError("base_period_sales must not be negative")

        missing: list[str] = []

        authenticity_met = has_timestamp or has_correction_deletion_history or has_operational_rules
        if not authenticity_met:
            missing.append("authenticity")

        if base_period_sales <= SALES_WAIVER_THRESHOLD and can_provide_download:
            required_search_level = SEARCH_LEVEL_WAIVED
        elif can_provide_download:
            required_search_level = SEARCH_LEVEL_THREE_ITEMS_ONLY
        else:
            required_search_level = SEARCH_LEVEL_FULL

        has_three_items = can_search_by_date and can_search_by_amount and can_search_by_counterparty

        if required_search_level == SEARCH_LEVEL_WAIVED:
            search_requirement_met = True
        elif required_search_level == SEARCH_LEVEL_THREE_ITEMS_ONLY:
            search_requirement_met = has_three_items
        else:
            search_requirement_met = has_three_items and can_search_by_range and can_search_by_combination

        if not search_requirement_met:
            missing.append("search")

        if not has_display_device:
            missing.append("display_device")

        visibility_met = has_display_device and search_requirement_met
        compliant = authenticity_met and visibility_met

        return DenchouElectronicCheckResult(
            authenticity_met=authenticity_met,
            visibility_met=visibility_met,
            required_search_level=required_search_level,
            search_requirement_met=search_requirement_met,
            compliant=compliant,
            missing_requirements=tuple(missing),
        )
