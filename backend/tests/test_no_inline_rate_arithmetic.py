"""エンドポイント内で税率・保険料率を直書きしていないことの検証。

このリポジトリでは、検証済みのサービス（速算表・等級表・割増率）が揃っている
にもかかわらず、エンドポイントが自前の簡易計算を持っている箇所が繰り返し
見つかった。いずれも利用者の金額に直接影響した。

- 給与: 割増賃金が一律1.25倍 → 月60時間超が過少払い
- 給与: 社会保険料が総額の15% → 全員から過大控除
- 年末調整: 給与収入にそのまま課税 → 年税額が約5倍
- 賞与: 社会保険料が賞与額の15% → 上限が効かず過大控除

いずれも「サービスが無かった」のではなく「エンドポイントが使わなかった」。
自前計算はレビューを通り抜けやすく、法改正時にも取り残されるため、
率の直書きが増えないことを機械的に確認する。

新たに直書きが必要になった場合は、サービス側に置いてここの ALLOWED に
理由付きで登録すること。
"""
import ast
import pathlib
import re

import pytest

ENDPOINTS_DIR = pathlib.Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "endpoints"

# 率とみなす Decimal 定数。1.021（復興特別所得税）のような割増係数も対象にする。
# ちょうど 1 倍は「係数の既定値」なので率とはみなさない。
_RATE = re.compile(r'Decimal\(\s*"(0\.\d+|1\.\d+)"\s*\)')
_IDENTITY = {"1.0", "1.00", "1.000"}

# 意図的な例外。(ファイル名, 関数名) -> 理由。
ALLOWED: dict[tuple[str, str], str] = {
    # 概算であることを応答と画面で明示している。法定計算に必要な入力
    # （扶養親族等の数・税額表）が未実装のため、暫定的に残している。
    ("payroll.py", "_estimate_income_tax"): "源泉所得税の概算。estimate_notice で明示済み",
    ("bonus.py", "_estimate_bonus_tax"): "賞与源泉所得税の概算。estimate_notice で明示済み",
    # 仕訳の税区分から集計するのが本来。一律按分であることを estimate_notice で
    # 明示している。改善8（docs/ImprovementGuide.md）で解消する。
    ("tax_returns.py", "calculate_tax_return"): "消費税申告の一律按分。estimate_notice で明示済み",
}


def _inline_rate_functions(path: pathlib.Path) -> list[tuple[int, str, list[str]]]:
    source = path.read_text()
    tree = ast.parse(source)

    found = []
    for fn in ast.walk(tree):
        if not isinstance(fn, ast.AsyncFunctionDef | ast.FunctionDef):
            continue
        if (path.name, fn.name) in ALLOWED:
            continue
        body = ast.get_source_segment(source, fn) or ""
        rates = sorted(set(_RATE.findall(body)) - _IDENTITY)
        if rates:
            found.append((fn.lineno, fn.name, rates))
    return found


ENDPOINT_FILES = sorted(ENDPOINTS_DIR.glob("*.py"))


def test_endpoint_files_are_discovered():
    """走査対象が取れないまま「問題なし」になっていないこと。"""
    assert len(ENDPOINT_FILES) > 10


@pytest.mark.parametrize("path", ENDPOINT_FILES, ids=lambda p: p.name)
def test_no_inline_rate_constants(path: pathlib.Path):
    inline = _inline_rate_functions(path)
    detail = "\n".join(f"  {path.name}:{ln} {name}() -> {rates}" for ln, name, rates in inline)
    assert not inline, (
        "エンドポイントに率が直書きされている（検証済みサービスを使うこと）:\n"
        f"{detail}"
    )


def test_scanner_detects_an_inline_rate(tmp_path):
    """走査ロジック自体が機能していること。"""
    sample = tmp_path / "sample.py"
    sample.write_text(
        "from decimal import Decimal\n"
        "def calc(gross):\n"
        '    return gross * Decimal("0.15")\n'
    )
    assert _inline_rate_functions(sample) == [(2, "calc", ["0.15"])]


def test_scanner_ignores_non_rate_constants(tmp_path):
    """金額や単位（1000 など）を率と誤検出しないこと。"""
    sample = tmp_path / "sample.py"
    sample.write_text(
        "from decimal import Decimal\n"
        "def calc(gross):\n"
        '    return (gross // Decimal("1000")) * Decimal("1000")\n'
    )
    assert _inline_rate_functions(sample) == []
