"""ruff の結果をテストとして扱う。

`.github/workflows/backend-ci.yml` の lint ステップは `ruff check app/ || true`
で終わっており、**失敗しても必ず成功扱い**になる。実際にこの経路で lint の
劣化が main に入ったことがある。またステップの対象は `app/` だけで、
`tests/` は見ていない。

ワークフロー側の修正案は docs/ci/backend-ci-db-tests.md にあるが、GitHub App に
`workflows` 権限が無く自動では適用できない。テストスイート側なら結果が
握り潰されないので、ここで lint を実行して結果を反映させる。

ワークフローの lint ステップが `|| true` を外して `tests/` も見るようになれば、
このファイルは不要になる。
"""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
TARGETS = ["app", "tests"]


@pytest.mark.skipif(importlib.util.find_spec("ruff") is None, reason="ruff がインストールされていない")
def test_ruff_reports_no_findings():
    # PATH 上の ruff ではなく `python -m ruff` を使う。requirements.txt で固定した
    # バージョンが動くので、手元とCIで指摘が食い違わない。
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", *TARGETS],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )

    assert result.returncode == 0, (
        "ruff の指摘が残っている（CIの lint ステップは `|| true` のため見逃す）:\n"
        f"{result.stdout}\n{result.stderr}"
    )
