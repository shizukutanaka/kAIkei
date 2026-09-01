"""CORS の許可オリジン設定。

**この不具合は、実際に画面をブラウザで開くまで誰も気付かなかった。**
`allow_origins` が `["http://localhost:3000"]` にベタ書きされており、

- 本番のドメインに置いた画面からは、APIを**一切呼べない**
  （プリフライトが全て失敗する。サーバは正常に起動するので気付きにくい）
- `http://127.0.0.1:3000` は `http://localhost:3000` と**別オリジン**なので、
  ローカル開発でもホスト名の書き方次第で塞がれる

他の設定（DB・JWT・S3）は全て環境変数で差し替えられるのに、ここだけ固定だった。
起動時の安全確認も、秘密情報は見ていたが CORS は見ていなかった。

`allow_credentials=True` で運用しているため `*` は使えない（ブラウザが拒否する）。
"""
import pytest

from app.core.config import Settings
from app.core.secrets_check import check_cors_origins


def test_the_default_allows_both_localhost_spellings():
    """localhost と 127.0.0.1 は別オリジン。開発中どちらでも通ること。"""
    origins = Settings().cors_allow_origins

    assert "http://localhost:3000" in origins
    assert "http://127.0.0.1:3000" in origins


def test_origins_are_configurable():
    """本番ドメインを環境変数で差し替えられること。"""
    settings = Settings(CORS_ALLOW_ORIGINS="https://kaikei.example.com,https://www.example.com")

    assert settings.cors_allow_origins == [
        "https://kaikei.example.com",
        "https://www.example.com",
    ]


@pytest.mark.parametrize(
    "raw,expected",
    [
        (" https://a.example.com , https://b.example.com ", ["https://a.example.com", "https://b.example.com"]),
        ("https://a.example.com,", ["https://a.example.com"]),
        ("", []),
    ],
)
def test_whitespace_and_empty_entries_are_dropped(raw, expected):
    assert Settings(CORS_ALLOW_ORIGINS=raw).cors_allow_origins == expected


def test_leaving_the_local_default_is_reported():
    """本番でローカル既定のままなら問題として報告されること。

    これを報告しないと、起動は成功するのに画面から何も呼べないという
    最も気付きにくい壊れ方になる。
    """
    issues = check_cors_origins(["http://localhost:3000", "http://127.0.0.1:3000"])

    assert issues, "ローカル既定のままなのに何も報告されない"
    assert "production frontend would be blocked" in issues[0]


def test_a_real_domain_is_not_reported():
    """正しく設定されていれば何も報告しないこと（過検出しない）。"""
    assert check_cors_origins(["https://kaikei.example.com"]) == []


def test_a_real_domain_alongside_localhost_is_accepted():
    """本番ドメインが1つでも入っていれば設定済みとみなすこと。"""
    assert check_cors_origins(["http://localhost:3000", "https://kaikei.example.com"]) == []


def test_a_wildcard_is_reported():
    """`*` は allow_credentials=True と併用できない（ブラウザが拒否する）。"""
    issues = check_cors_origins(["*"])

    assert any("'*'" in i for i in issues)


def test_an_empty_list_is_reported():
    """空にすると全てのブラウザ経由の呼び出しが塞がる。"""
    assert check_cors_origins([]), "空なのに何も報告されない"


def test_the_app_uses_the_configured_origins():
    """設定値が実際に CORS ミドルウェアへ渡っていること。

    設定項目を足しても配線し忘れれば意味が無い。
    """
    from starlette.middleware.cors import CORSMiddleware

    from app.core.config import settings
    from app.main import app

    cors = [m for m in app.user_middleware if m.cls is CORSMiddleware]
    assert len(cors) == 1, "CORSミドルウェアが1つだけ設定されていること"
    assert cors[0].kwargs["allow_origins"] == settings.cors_allow_origins


# ---------------------------------------------------------------------------
# ミドルウェアの順序
#
# Starlette の `add_middleware` は先頭に挿入するので、**最後に足したものが最も外側**。
# CORS を内側に置くと、外側のミドルウェアが自分で返す応答（レート制限の429、
# IP制限の403、冪等性の409）に CORS ヘッダが付かない。ブラウザは状態コードを
# 読めず、不透明な CORS エラーとして扱う。
#
# 実際にこの状態だった。画面を35枚ブラウザで開いたところ、レート制限に達した
# 時点から「CORSでブロックされた」という表示に変わり、429であることが
# 一切分からなかった。フロントのエラー処理も状態コードを見られない。
# ---------------------------------------------------------------------------


def test_cors_is_the_outermost_middleware():
    """CORS が最も外側にあること。

    内側にあると、外側のミドルウェアが返すエラー応答に CORS ヘッダが付かない。
    """
    from starlette.middleware.cors import CORSMiddleware

    from app.main import app

    assert app.user_middleware[0].cls is CORSMiddleware, (
        "CORS が最も外側にない。現在の順序（外→内）: "
        f"{[m.cls.__name__ for m in app.user_middleware]}\n"
        "add_middleware は先頭に挿入するため、CORS は**最後に**追加すること。"
    )


@pytest.mark.asyncio
async def test_a_rate_limited_response_still_carries_cors_headers():
    """429 にも CORS ヘッダが付くこと。

    付かないと、ブラウザは 429 も retry-after も読めず、利用者には
    「なぜ動かないのか分からない」画面になる。
    """
    import httpx

    from app.main import app

    origin = "http://localhost:3000"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        last = None
        for _ in range(130):
            last = await client.get("/api/v1/companies", headers={"Origin": origin})
            if last.status_code == 429:
                break

    assert last.status_code == 429, "レート制限に到達しなかった（上限が変わった可能性）"
    assert last.headers.get("access-control-allow-origin") == origin, (
        "429 に CORS ヘッダが無い。ブラウザは状態コードを読めない。"
    )
