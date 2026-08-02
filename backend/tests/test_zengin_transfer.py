"""全銀協 総合振込フォーマット生成のテスト。"""

from datetime import date
from decimal import Decimal

import pytest

from app.schemas.schemas import ZenginTransferResponse
from app.services.zengin_transfer import (
    ACCOUNT_TYPE_ORDINARY,
    ENCODING,
    RECORD_LENGTH,
    TransferLine,
    TransferRequest,
    ZenginTransferService,
)


def _line(**overrides) -> TransferLine:
    params = {
        "bank_code": "0005",
        "bank_name": "ミツビシUFJ",
        "branch_code": "001",
        "branch_name": "ホンテン",
        "account_type": ACCOUNT_TYPE_ORDINARY,
        "account_number": "1234567",
        "recipient_name": "カブシキガイシャカイケイ",
        "amount": Decimal("100000"),
    }
    params.update(overrides)
    return TransferLine(**params)


def _request(lines: list[TransferLine] | None = None) -> TransferRequest:
    return TransferRequest(
        consignor_code="1234567890",
        consignor_name="カイケイショウジ(カ",
        transfer_date=date(2025, 8, 25),
        bank_code="0009",
        bank_name="ミツイスミトモ",
        branch_code="123",
        branch_name="シンジュク",
        account_type=ACCOUNT_TYPE_ORDINARY,
        account_number="7654321",
        lines=lines if lines is not None else [_line()],
    )


def test_record_structure_and_totals():
    result = ZenginTransferService.generate(
        _request([_line(), _line(recipient_name="ヤマダタロウ", amount=Decimal("250000"))]),
    )
    header, data1, data2, trailer, end = result.records
    assert len(result.records) == 5
    for record in result.records:
        assert len(record.encode(ENCODING)) == RECORD_LENGTH
    assert header.startswith("1210")
    assert data1.startswith("2")
    assert data2.startswith("2")
    assert trailer.startswith("8")
    assert end.startswith("9")
    assert result.detail_count == 2
    assert result.total_amount == Decimal("350000")
    # トレーラ: 区分1桁 + 件数6桁 + 金額12桁
    assert trailer[1:7] == "000002"
    assert trailer[7:19] == "000000350000"


def test_header_contains_transfer_date_as_mmdd():
    result = ZenginTransferService.generate(_request())
    header = result.records[0]
    # 区分1 + 種別2 + コード区分1 + 委託者コード10 + 委託者名40 = 54文字目から取組日
    assert header[54:58] == "0825"
    assert header[4:14] == "1234567890"


def test_amount_is_right_aligned_zero_padded():
    result = ZenginTransferService.generate(_request([_line(amount=Decimal("100000"))]))
    data = result.records[1]
    # 区分1 + 銀行4 + 銀行名15 + 支店3 + 支店名15 + 交換所4 + 種目1 + 口座7 + 名義30 = 80
    assert data[80:90] == "0000100000"


def test_full_width_kana_is_converted_to_half_width():
    # 小書きカナは大文字化、全角スペースは半角スペースになる。
    converted = ZenginTransferService.to_zengin_charset("カブシキガイシャ　カイケイ")
    assert converted == "ｶﾌﾞｼｷｶﾞｲｼﾔ ｶｲｹｲ"


def test_hiragana_and_full_width_alnum_are_converted():
    assert ZenginTransferService.to_zengin_charset("かぶしき") == "ｶﾌﾞｼｷ"
    assert ZenginTransferService.to_zengin_charset("ＡＢＣ１２３") == "ABC123"
    assert ZenginTransferService.to_zengin_charset("abc") == "ABC"


def test_kanji_recipient_name_is_rejected():
    with pytest.raises(ValueError, match="zengin charset"):
        ZenginTransferService.generate(_request([_line(recipient_name="株式会社会計")]))


def test_recipient_fee_is_deducted_from_transfer_amount():
    result = ZenginTransferService.generate(
        _request(
            [
                _line(
                    amount=Decimal("100000"),
                    transfer_fee=Decimal("660"),
                    fee_borne_by_recipient=True,
                ),
            ],
        ),
    )
    assert result.total_amount == Decimal("99340")
    assert result.total_fee_deducted == Decimal("660")
    assert result.lines[0].transfer_amount == Decimal("99340")
    assert result.records[1][80:90] == "0000099340"


def test_company_borne_fee_does_not_change_transfer_amount():
    result = ZenginTransferService.generate(
        _request([_line(amount=Decimal("100000"), transfer_fee=Decimal("660"))]),
    )
    assert result.total_amount == Decimal("100000")
    assert result.total_fee_deducted == Decimal("0")


def test_fee_exceeding_amount_is_rejected():
    with pytest.raises(ValueError, match="transfer_fee exceeds amount"):
        ZenginTransferService.generate(
            _request(
                [
                    _line(
                        amount=Decimal("500"),
                        transfer_fee=Decimal("660"),
                        fee_borne_by_recipient=True,
                    ),
                ],
            ),
        )


def test_empty_lines_rejected():
    with pytest.raises(ValueError, match="at least one transfer line"):
        ZenginTransferService.generate(_request([]))


def test_non_positive_amount_rejected():
    with pytest.raises(ValueError, match="amount must be positive"):
        ZenginTransferService.generate(_request([_line(amount=Decimal("0"))]))


def test_fractional_amount_rejected():
    with pytest.raises(ValueError, match="integer yen"):
        ZenginTransferService.generate(_request([_line(amount=Decimal("100.5"))]))


def test_non_numeric_bank_code_rejected():
    with pytest.raises(ValueError, match="bank_code must be digits"):
        ZenginTransferService.generate(_request([_line(bank_code="00A5")]))


def test_unknown_account_type_rejected():
    with pytest.raises(ValueError, match="unknown account_type"):
        ZenginTransferService.generate(_request([_line(account_type="9")]))


def test_long_recipient_name_is_truncated_to_field_width():
    result = ZenginTransferService.generate(_request([_line(recipient_name="ア" * 40)]))
    data = result.records[1]
    assert data[50:80] == "ｱ" * 30
    assert len(data.encode(ENCODING)) == RECORD_LENGTH


def test_encode_produces_crlf_delimited_shift_jis():
    result = ZenginTransferService.generate(_request())
    body = ZenginTransferService.encode(result)
    assert body.endswith(b"\r\n")
    assert len(body) == (RECORD_LENGTH + 2) * len(result.records)
    assert body.decode(ENCODING)[0] == "1"


def test_response_schema_serializes_dataclass():
    result = ZenginTransferService.generate(_request())
    response = ZenginTransferResponse.model_validate(result)
    assert response.detail_count == 1
    assert response.record_length == RECORD_LENGTH
    assert response.encoding == ENCODING
    assert response.lines[0].transfer_amount == Decimal("100000")
