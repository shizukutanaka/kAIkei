"""自動仕訳学習（app/services/journal_learning.py）の振る舞い。

製品の軸である「過去の仕訳から学んで候補を出す」について、会計ソフトとして
最も大事な性質を固定する:

- 繰り返し現れるパターンは、同じ候補として再提示されること
- 学習データが少ない初期状態では、候補を出さないこと（推測で埋めない）
- 過去に無いパターンには、自信ありげな誤答を返さないこと
- 支持の薄い候補は「信頼できない」と正直に印が付くこと
- 同じ入力には必ず同じ結果が返ること（決定的であること）

DB は使わない（学習器の純粋ロジックのみ）。
"""
import uuid
from decimal import Decimal

from app.models.models import Account, JournalHeader, JournalLine
from app.services.journal_learning import (
    JournalExample,
    JournalPatternLearner,
    _example_from_rows,
    extract_features,
    normalize_text,
    pattern_key,
)


def _example(text: str, debit: str, credit: str, amount: str = "10000") -> JournalExample:
    return JournalExample(
        text=text,
        amount=Decimal(amount),
        debit_codes=(debit,),
        credit_codes=(credit,),
    )


def _trained_with_cloud_invoices() -> JournalPatternLearner:
    """「クラウド利用料 → (借)通信費 / (貸)未払金」を6件学習した状態。"""
    learner = JournalPatternLearner()
    for month in range(1, 7):
        learner.add_example(
            _example(
                f"クラウド利用料 請求書 2026-{month:03d} サーバ費用",
                "5201",  # 通信費
                "2102",  # 未払金
                amount="13200",
            )
        )
    return learner


def test_a_repeated_pattern_is_suggested_back():
    """繰り返し取引は、同じ仕訳候補として再提示される。"""
    learner = _trained_with_cloud_invoices()

    result = learner.suggest(text="クラウド利用料 請求書 2026-099 サーバ費用", amount=Decimal("13200"))

    assert result.status == "ok"
    assert result.trained_examples == 6
    top = result.candidates[0]
    assert top.debit_codes == ("5201",)
    assert top.credit_codes == ("2102",)
    assert top.exact_matches == 6  # 数字を潰せば6件とも完全一致
    assert top.confidence == 1.0
    assert top.reliable is True


def test_too_little_history_suggests_nothing():
    """学習データが下限未満の初期状態では、候補を出さない。

    数件の偶然を「学習した」と言って候補を出すのが、会計では一番危ない。
    """
    learner = JournalPatternLearner()
    for i in range(JournalPatternLearner.MIN_EXAMPLES - 1):
        learner.add_example(_example(f"事務所 家賃 {i}月分", "5202", "1101"))

    result = learner.suggest(text="事務所 家賃 9月分")

    assert result.status == "insufficient_data"
    assert result.candidates == []


def test_an_empty_learner_suggests_nothing():
    learner = JournalPatternLearner()
    result = learner.suggest(text="事務所 家賃")
    assert result.status == "insufficient_data"
    assert result.candidates == []


def test_an_unknown_pattern_is_not_guessed():
    """過去に無い取引には候補を返さない（誤答を自信ありげに出さない）。"""
    learner = _trained_with_cloud_invoices()
    for i in range(6):
        learner.add_example(_example(f"事務所 家賃 {i}月分 支払", "5202", "1101", amount="180000"))

    result = learner.suggest(text="ソフトウェア ライセンス 更新")

    assert result.status == "no_matching_history"
    assert result.candidates == []


def test_mixed_evidence_ranks_by_support():
    """同じ摘要で2通りの仕訳がある場合、多い方が首位になり、割合も正直に出る。"""
    learner = JournalPatternLearner()
    for _ in range(5):
        learner.add_example(_example("コピー用紙 購入", "5203", "1101", amount="3000"))  # 事務用品費
    for _ in range(2):
        learner.add_example(_example("コピー用紙 購入", "5204", "1101", amount="3000"))  # 消耗品費

    result = learner.suggest(text="コピー用紙 購入", amount=Decimal("3000"))

    assert result.status == "ok"
    assert [c.debit_codes for c in result.candidates] == [("5203",), ("5204",)]
    assert result.candidates[0].confidence > result.candidates[1].confidence
    assert result.candidates[0].reliable is True
    assert result.candidates[1].reliable is False  # 少数派は「信頼できる」とは言わない


def test_a_single_occurrence_is_never_marked_reliable():
    """1回しか無いパターンは、完全一致で拾えても `reliable` にはならない。"""
    learner = _trained_with_cloud_invoices()
    learner.add_example(_example("新聞 広告 掲載料", "5205", "1101", amount="55000"))

    result = learner.suggest(text="新聞 広告 掲載料", amount=Decimal("55000"))

    assert result.status == "ok"
    top = result.candidates[0]
    assert top.debit_codes == ("5205",)
    assert top.support == 1
    assert top.reliable is False


def test_a_single_occurrence_without_exact_match_is_dropped():
    """1回しか無いパターンに「少し似ている」だけでは、候補にすらならない。"""
    learner = _trained_with_cloud_invoices()
    learner.add_example(_example("新聞 広告 掲載料", "5205", "1101", amount="55000"))

    result = learner.suggest(text="新聞 購読料")

    assert result.status == "no_matching_history"
    assert result.candidates == []


def test_numbers_do_not_split_a_pattern():
    """請求書番号や日付の違いは、パターンの同一性を壊さない。"""
    assert pattern_key("請求書 2026-001 支払") == pattern_key("請求書 2026-002 支払")
    assert pattern_key("ＡＢＣ商事 支払") == pattern_key("abc商事 支払")
    assert normalize_text("２０２６年１月") == "#年#月"


def test_amount_bucket_is_a_feature():
    features = extract_features("家賃 支払", Decimal("150000"))
    assert "amt:5" in features
    # 金額が無ければ桁帯の特徴は付かない
    assert not any(f.startswith("amt:") for f in extract_features("家賃 支払"))


def test_suggestions_are_deterministic():
    """同じ学習・同じ入力では、候補の並びと値が完全に一致する。"""
    examples = [
        _example("コピー用紙 購入", "5203", "1101", amount="3000"),
        _example("コピー用紙 購入", "5204", "1101", amount="3000"),
        _example("事務所 家賃 支払", "5202", "1101", amount="180000"),
        _example("事務所 家賃 支払", "5202", "1101", amount="180000"),
        _example("電気料金 支払", "5206", "1101", amount="21000"),
        _example("電気料金 支払", "5206", "1101", amount="20500"),
    ]
    first = JournalPatternLearner()
    first.train(examples)
    second = JournalPatternLearner()
    second.train(list(reversed(examples)))  # 学習順が違っても結果は同じ

    result_first = first.suggest(text="コピー用紙 購入", amount=Decimal("3000"))
    result_second = second.suggest(text="コピー用紙 購入", amount=Decimal("3000"))
    assert result_first == result_second
    # 同じ学習器に2回聞いても同じ
    assert first.suggest(text="コピー用紙 購入", amount=Decimal("3000")) == result_first


def _orm_rows(summary: str, lines_spec: list[tuple[str, str, str]]):
    """DB を介さずに (header, lines, accounts) を組み立てる。

    lines_spec: (借貸, 科目コード, 金額) の並び。
    """
    accounts: dict[uuid.UUID, Account] = {}
    lines: list[JournalLine] = []
    header_id = uuid.uuid4()
    for i, (debit_credit, code, amount) in enumerate(lines_spec, start=1):
        account = accounts.setdefault(
            uuid.uuid5(uuid.NAMESPACE_DNS, code),
            Account(
                account_id=uuid.uuid5(uuid.NAMESPACE_DNS, code),
                account_code=code,
                account_name=code,
                account_type="expense",
                debit_credit="debit",
            ),
        )
        lines.append(
            JournalLine(
                journal_header_id=header_id,
                line_number=i,
                debit_credit=debit_credit,
                account_id=account.account_id,
                amount=Decimal(amount),
                description=f"{summary} 明細{i}",
            )
        )
    header = JournalHeader(summary=summary)
    return header, lines, accounts


def test_example_building_sorts_codes_and_sums_debits():
    """DBの行→学習データ変換: 科目コードは並びを揃え、金額は借方合計になる。"""
    header, lines, accounts = _orm_rows(
        "サーバ費用",
        [
            ("debit", "5209", "3000"),
            ("credit", "2102", "13200"),
            ("debit", "5201", "10200"),
        ],
    )

    example = _example_from_rows(header, lines, accounts)

    assert example is not None
    assert example.debit_codes == ("5201", "5209")  # 投入順でなくコード順
    assert example.credit_codes == ("2102",)
    assert example.amount == Decimal("13200")
    assert "サーバ費用" in example.text
    assert "サーバ費用 明細1" in example.text  # 明細説明も学習テキストに入る


def test_example_building_skips_one_sided_journals():
    """借方だけ・貸方だけの行は学習データにしない（壊れた正解を学ばせない）。"""
    header, lines, accounts = _orm_rows("片側だけ", [("debit", "5201", "1000")])
    assert _example_from_rows(header, lines, accounts) is None


def test_the_model_survives_a_serialization_round_trip():
    """学習結果を dict にして戻しても、候補が変わらない。"""
    learner = _trained_with_cloud_invoices()

    restored = JournalPatternLearner.from_dict(learner.to_dict())

    assert restored.example_count == learner.example_count
    assert restored.suggest(text="クラウド利用料 請求書 2026-100 サーバ費用") == learner.suggest(
        text="クラウド利用料 請求書 2026-100 サーバ費用"
    )
