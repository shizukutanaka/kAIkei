# Proposed backend CI update — run the full suite + DB integration tests

> This change to `.github/workflows/backend-ci.yml` could **not** be pushed by the
> automation because the GitHub App lacks the `workflows` permission. Apply it
> manually (or grant the App `workflows` scope) — the test code it drives is
> already merged.

## Why

- The existing `test` job ran only **5 of 33** test files (a hardcoded list),
  so most unit tests — including the async DB integration tests — never ran in CI.
- The new DB integration tests (`-m db`) need a real PostgreSQL (models use
  `JSONB`/`UUID`).

## What to change

1. In the existing `test` job, replace the hardcoded test command with the full
   pure-logic suite (no DB needed):

   ```yaml
   - name: Run unit tests
     env: { ... unchanged ... }
     run: |
       python -m pytest tests/ -m "not db" --tb=short
   ```

2. Add a second job that starts a Postgres service and runs the DB tests:

   ```yaml
   db-test:
     runs-on: ubuntu-latest
     defaults:
       run:
         working-directory: backend
     services:
       postgres:
         image: postgres:16-alpine
         env:
           POSTGRES_USER: kaikei
           POSTGRES_PASSWORD: kaikei_dev
           POSTGRES_DB: kaikei_test
         ports: ["5432:5432"]
         options: >-
           --health-cmd "pg_isready -U kaikei"
           --health-interval 10s --health-timeout 5s --health-retries 5
     steps:
       - uses: actions/checkout@v4
       - uses: actions/setup-python@v5
         with: { python-version: "3.11" }
       - uses: astral-sh/setup-uv@v3
       - name: Install dependencies
         run: |
           uv pip install --system -r requirements.txt
           uv pip install --system pytest pytest-asyncio pytest-cov httpx asyncpg
       - name: Run DB integration tests
         env:
           JWT_SECRET_KEY: test-secret-key-for-ci
           JWT_ALGORITHM: HS256
           TEST_DATABASE_URL: postgresql+asyncpg://kaikei:kaikei_dev@localhost:5432/kaikei_test
           OPENAI_API_KEY: test-key
           ANTHROPIC_API_KEY: test-key
           LOG_LEVEL: INFO
         run: |
           python -m pytest tests/ -m db --tb=short
   ```

## Local verification

```bash
# start a throwaway Postgres (docker), or use docker-compose's db service
docker run -d --name kaikei-test-db -e POSTGRES_USER=kaikei \
  -e POSTGRES_PASSWORD=kaikei_dev -e POSTGRES_DB=kaikei_test -p 5432:5432 postgres:16-alpine

cd backend
# DB integration tests
TEST_DATABASE_URL=postgresql+asyncpg://kaikei:kaikei_dev@localhost:5432/kaikei_test \
  python -m pytest tests/ -m db -q            # 17 passed
# pure-logic suite (no DB); db tests auto-skip
python -m pytest tests/ -m "not db" -q        # 407 passed
```

The DB tests auto-skip when `TEST_DATABASE_URL` is unset (see
`backend/tests/conftest.py`), so a no-DB run stays green.
