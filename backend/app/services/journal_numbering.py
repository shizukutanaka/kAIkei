"""仕訳番号の採番。

同じ規則の実装が2つあった。`POST /journals` は既存番号の **MAX** から次を作り、
自動仕訳（請求書・給与などから起こす仕訳）は行数の **COUNT** から作る。どちらも
「読んでから書く」ので、同じ会社で同時に2件作ると**両方が同じ番号を読み**、
同じ番号の仕訳が2件できる。実測で3件同時に作ると3件とも JRN-00000001 になった。

仕訳番号は監査で仕訳を追う識別子なので、重複すると追跡できない。DBには一意制約が
無く、重複しても誰も気付かない。

そこで採番をここ1箇所に集約し、**DBの一意制約に守らせる**。制約違反は握り潰さず、
番号を採り直して入れ直す（`insert_with_number`）。読み取りの競合は避けられないが、
書き込みは制約が弾くので、重複した番号が帳簿に残ることはない。
"""
import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import JournalHeader

PREFIX = "JRN-"
_PATTERN = re.compile(rf"^{PREFIX}(\d+)$")

# 制約違反で採り直す回数の上限。同時に投入される件数より十分大きければよく、
# 無限に粘ると要求が返らなくなる。
MAX_ATTEMPTS = 8


async def next_journal_number(db: AsyncSession, company_id: UUID) -> str:
    """その会社で次に使う仕訳番号。

    `JRN-` で始まり数字が続く番号だけを見る。取り込んだ仕訳が別の体系の番号
    （`F-12345` など）を持っていても、採番の連番が飛ばされない。
    """
    numbers = await db.execute(
        select(JournalHeader.journal_number).where(
            JournalHeader.company_id == company_id,
            JournalHeader.journal_number.like(f"{PREFIX}%"),
        )
    )
    highest = 0
    for (number,) in numbers.all():
        matched = _PATTERN.match(number or "")
        if matched:
            highest = max(highest, int(matched.group(1)))
    return f"{PREFIX}{highest + 1:08d}"


async def insert_with_number(db: AsyncSession, company_id: UUID, build) -> JournalHeader:
    """採番して `build(number)` が返すヘッダを登録する。番号が衝突したら採り直す。

    Args:
        build: 採番した番号を受け取り、未登録の `JournalHeader` を返す関数。
               採り直しのたびに呼ばれるので、毎回新しいインスタンスを返すこと。

    Raises:
        IntegrityError: 上限まで採り直しても衝突が解消しなかった場合。
    """
    for attempt in range(MAX_ATTEMPTS):
        number = await next_journal_number(db, company_id)
        header = build(number)
        savepoint = await db.begin_nested()
        try:
            db.add(header)
            await db.flush()
        except IntegrityError:
            # savepoint のロールバックで header はセッションから外れる。
            # 明示的な expunge は「存在しない」エラーになるので呼ばない。
            await savepoint.rollback()
            if attempt == MAX_ATTEMPTS - 1:
                raise
            continue
        return header
    raise AssertionError("unreachable")  # pragma: no cover
