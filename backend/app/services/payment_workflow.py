"""支払申請のステータス遷移（ワークフロー）。

draft（下書き）→ approved（承認済み）→ executed（実行済み）。draft/approved は
cancel で cancelled（取消）へ遷移可能。全銀エクスポートは approved/executed のみ対象。
遷移規則はDB非依存の純粋関数として定義し、不正な遷移は ValueError を送出する。
"""

PAYMENT_STATUSES = ("draft", "approved", "executed", "cancelled")

_TRANSITIONS: dict[tuple[str, str], str] = {
    ("draft", "approve"): "approved",
    ("approved", "execute"): "executed",
    ("draft", "cancel"): "cancelled",
    ("approved", "cancel"): "cancelled",
}


def next_payment_status(current_status: str, action: str) -> str:
    """現在ステータスとアクションから次ステータスを返す。不正な遷移は ValueError。

    action は "approve" / "execute" / "cancel"。
    """
    key = (current_status, action)
    if key not in _TRANSITIONS:
        raise ValueError(f"cannot {action} a payment request in status '{current_status}'")
    return _TRANSITIONS[key]
