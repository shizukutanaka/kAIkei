---
name: testing-kaikei-backend-api
description: Runtime-test kAIkei backend APIs end-to-end (start Postgres, migrate, seed a user, mint a JWT, call endpoints over HTTP). Use when verifying new/changed FastAPI endpoints — payroll, tax, social insurance, documents — rather than relying only on unit tests.
---

# Runtime-testing the kAIkei backend API

Most kAIkei business logic lives in pure services under `backend/app/services/` with unit tests, and
endpoints in `backend/app/api/v1/endpoints/` are thin wrappers. **Unit tests do not cover the endpoint
layer**, so serialization/DI bugs reach production silently. Always exercise changed endpoints over real
HTTP before claiming a slice works.

## Why this matters (real bug this caught)
`POST /tax/sales-return-tax` returned **HTTP 500** while all its unit tests passed: the endpoint called
`SomeResponse.model_validate(result)` on a frozen dataclass, but the response schema lacked
`model_config = {"from_attributes": True}`. Pydantic rejects a dataclass without it.

**Convention:** any response schema in `app/schemas/schemas.py` that is built via
`XxxResponse.model_validate(service_result)` MUST declare `model_config = {"from_attributes": True}` —
**including nested schemas** (a list of nested dataclasses needs it on the nested model too).
When adding an endpoint, either follow that convention or construct the response explicitly.
A cheap regression guard that catches this without a DB/HTTP harness:

```python
def test_response_schema_validates_service_result():
    result = SomeService.compute(...)
    response = SomeResponse.model_validate(result)   # fails if from_attributes is missing
    assert response.total == Decimal("...")
```

## Setup (run once per session)

Postgres may not be running (and in older snapshots not installed). Install/start it, then migrate:

```bash
pg_isready || sudo pg_ctlcluster 14 main start        # install first if missing:
# sudo apt-get update -y && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y postgresql postgresql-contrib

sudo -u postgres psql -c "CREATE USER kaikei WITH PASSWORD 'kaikei_dev' CREATEDB;"
sudo -u postgres psql -c "CREATE DATABASE kaikei OWNER kaikei;"

cd backend && source .venv/bin/activate
PYTHONPATH=. alembic upgrade head     # PYTHONPATH=. is REQUIRED (env.py imports `app`)
```

Defaults in `app/core/config.py` already match (`postgresql+asyncpg://kaikei:kaikei_dev@localhost:5432/kaikei`,
dev `JWT_SECRET_KEY`), so **no secrets are needed for local runtime testing**.

Start the server in a **persistent/background shell** (`nohup`/`setsid` from a one-shot shell tends to die
with the shell; use a dedicated long-lived shell session instead):

```bash
cd backend && source .venv/bin/activate && PYTHONPATH=. uvicorn app.main:app --host 127.0.0.1 --port 8080
# verify: curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/docs   -> 200
```

## Authentication

Protected endpoints use `Depends(require_permission(Permission.X))` → `get_current_user` requires a JWT
whose `sub` is an **active, non-deleted `User` row**, so a token alone is not enough — seed the user.
`role="admin"` has every permission (`app/core/rbac.py`). Script it:

```python
# backend/_seed_test_user.py  (throwaway; delete before committing)
import asyncio
from app.core.database import engine
from app.core.security import create_access_token
from app.models.models import Tenant, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

async def main() -> None:
    async with AsyncSession(engine) as db:
        user = (await db.execute(select(User).where(User.email == "tester@example.com"))).scalar_one_or_none()
        if user is None:
            tenant = Tenant(tenant_name="Test Tenant", tenant_code="TEST")
            db.add(tenant); await db.flush()
            user = User(tenant_id=tenant.tenant_id, email="tester@example.com",
                        password_hash="x", display_name="Tester", role="admin")
            db.add(user); await db.flush()
            uid = user.user_id          # read BEFORE commit (see gotcha below)
            await db.commit()
        else:
            uid = user.user_id
    print(create_access_token(str(uid), extra_claims={"type": "access"}))

asyncio.run(main())
```

Run with `PYTHONPATH=. python _seed_test_user.py` and use the printed token as `Authorization: Bearer <token>`.

**Gotcha:** reading an ORM attribute *after* `await db.commit()` raises
`sqlalchemy.exc.MissingGreenlet` (expired attribute triggers lazy IO). Capture the id after `flush()`,
before `commit()` — or configure `expire_on_commit=False`.

## Calling endpoints

Router prefix is `/api/v1`; confirm the exact path in `app/api/v1/router.py` before testing
(e.g. tax endpoints live under `/api/v1/tax/...`, payroll under `/api/v1/payroll/...`).

```bash
T=$(PYTHONPATH=. python _seed_test_user.py | tail -1)
curl -s -H "Authorization: Bearer $T" "http://127.0.0.1:8080/api/v1/tax/corporate-tax?taxable_income=10000000"
curl -s -H "Authorization: Bearer $T" -H "Content-Type: application/json" \
     -X POST "http://127.0.0.1:8080/api/v1/payroll/labor-insurance/import-calculate" \
     -d '{"business_type":"general","csv_text":"社員番号,賃金\nE1,1000000\n"}'
```

Money is serialized as **JSON strings** (`"total_tax":"1664000"`) because services use `Decimal`.

## What to assert

These are statutory calculators, so vibes-based checks are worthless — assert exact hand-computed values:

- **Exact amounts** for every field, derived by hand from the statute (rates, 千円未満切捨/百円未満切捨 order).
- **A boundary case** that distinguishes rounding: e.g. income `1,111,000` → `total_tax=166600`
  (166,650 floored to 100); wage `1,234,567` → base `1,234,000`. Without the flooring the value differs
  by a visible amount, so a broken build cannot look identical.
- **A case that exercises the branch the slice adds** — e.g. an employee excluded from 雇用保険 so
  労災 base (6,000,000) ≠ 雇用 base (5,000,000). If both totals are equal your test can't detect a
  broken split.
- **Service `ValueError` → HTTP 422** with the expected `detail` message (endpoints translate it).
- **No token → HTTP 401.**

## Known unrelated noise (don't report as a regression)

- Server log: `Audit log write failed: ... audit_logs_tenant_id_fkey ... Key (tenant_id)=(00000000-...)`
  — the audit middleware writes a zero tenant id. Requests still return correct status/body. Preexisting.
- Import/startup warning: `No AI provider configured. Set LOCAL_LLM_ENDPOINT, OPENAI_API_KEY, or ANTHROPIC_API_KEY.`
  — nonblocking.
- Startup warnings about insecure dev `JWT_SECRET_KEY` / default MinIO credentials — expected locally.
- Router import can break from unrelated endpoint modules (a bad model import once made the whole router
  fail with `ImportError` while CI stayed green, since CI doesn't import the router). Sanity check with
  `python -c "from app.api.v1 import router"` — if it fails, fix or report that before testing.

## Before finishing

```bash
cd backend && source .venv/bin/activate
python -m ruff check <changed files>
python -m pytest -q                        # full suite
python -c "from app.api.v1 import router"  # router import guard (CI does NOT do this)
```

Delete throwaway harness files (`_seed_test_user.py`, test-plan/report scratch files) before committing;
stage files individually rather than `git add .`.

Recording: this is shell/API-only testing, so **do not record** — collect command output as evidence.

## Devin Secrets Needed

None. Local runtime testing uses the development defaults in `backend/app/core/config.py`
(DB `kaikei:kaikei_dev@localhost:5432/kaikei`, dev `JWT_SECRET_KEY`). AI provider keys
(`OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `LOCAL_LLM_ENDPOINT`) are only needed to test AI
inference endpoints, not the deterministic payroll/tax calculators.
