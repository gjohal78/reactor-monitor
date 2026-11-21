# reactor-monitor

An educational, simplified reactor monitoring app built as a portfolio project.

> ⚠️ **Not a real safety system.** The reactor is a toy simulation for learning purposes only.

## Stack

| Layer    | Tech                                                            |
| -------- | --------------------------------------------------------------- |
| Backend  | Python 3.12, FastAPI, SQLAlchemy, PostgreSQL, WebSockets, JWT    |
| Frontend | React + TypeScript (Vite), Recharts                             |
| Tooling  | ruff, mypy (strict), pytest · ESLint (typescript-eslint), Vitest |
| Runtime  | Docker Compose                                                  |

## Quick start

```bash
cp .env.example .env
make up          # postgres + backend + frontend
```

- Frontend: http://localhost:5173
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/health
- History: http://localhost:8000/api/history?minutes=15
- Auth: `POST /api/auth/login` (form: username, password), `POST /api/auth/refresh`, `GET /api/auth/me`
- Alarms: `GET /api/alarms`, `POST /api/alarms/{id}/ack`, `GET`/`PUT /api/alarms/limits`
- Reactor control: `POST /api/reactor/rods`, `/scram`, `/reset-scram`
- Audit log: `GET /api/audit` (supervisor)
- Live stream: `ws://localhost:8000/ws/telemetry?token=<access token>`, JSON frames `{"type", "data"}`:
  `alarm_snapshot` on connect, then `telemetry` (10 Hz) and `alarm` (state changes)

`make down` stops everything.

## Development

Requires Python 3.12 and Node 22.12+ on the host for local tooling (`.nvmrc` pins Node 22; `nvm use` picks it up).

```bash
make install     # backend/.venv + frontend/node_modules
make lint        # ruff, mypy, eslint, tsc
make test        # pytest + vitest
make format      # ruff auto-fix + format
```

## Layout

```
backend/    FastAPI app (app/), tests (tests/), pyproject.toml
frontend/   Vite + React + TypeScript
docker-compose.yml
```

The backend serves JSON under `/api/*` and WebSockets under `/ws/*`. Vite proxies both
paths in development, so the browser sees a single origin.

Database migrations live in `backend/migrations` (Alembic). `make up` applies them
automatically before the API starts; `make migrate` applies them to the database in your
`DATABASE_URL`.

## Roadmap

- [x] Reactor simulator
- [x] Live telemetry over WebSockets
- [x] Persistence with SQLAlchemy + migrations
- [x] JWT auth with roles
- [ ] Recharts dashboard

## Users, roles and audit

Everything except `/api/health` needs a login. Create accounts with the CLI (there is
no sign-up endpoint); the password is prompted for, never passed on the command line:

```bash
make create-user USERNAME=alice ROLE=supervisor   # while `make up` is running
```

| Role | Can |
| --- | --- |
| viewer | read telemetry, history, alarms and alarm limits |
| operator | + acknowledge alarms, move rods within the envelope, scram |
| supervisor | + change alarm limits, reset after a scram, read the audit log |

To try the API, open `/docs`, click **Authorize** and sign in with your username and
password.

Roles are enforced by FastAPI dependencies on every route, and the user is reloaded
from the database on each request, so disabling a user or changing a role takes effect
immediately. Access tokens last 15 minutes, refresh tokens 7 days. Passwords are hashed
with bcrypt.

Every login (successful or not) and every control action (accepted or rejected) is written
to `audit_log` with who, when, the client IP and the old and new values. A logged-in user
who tries something their role doesn't allow gets a 403, recorded as `ACCESS_DENIED` with
the request they attempted. The table is
append-only: database triggers reject UPDATE and DELETE (and TRUNCATE on Postgres).

The rod envelope applies to every role: rods can't be withdrawn above 10 % inserted, and
one command can withdraw them at most 5 % (`ROD_*` settings). Inserting rods is never
limited.

## Alarms

HI power (105 %), HI coolant temperature (314 °C) and short reactor period (15 s), each
with a deadband to stop chattering. Limits are configurable through `ALARM_*` settings
(see `backend/app/core/config.py`). States follow ISA-18.2 practice:

```
NORMAL ──active──▶ ACTIVE_UNACKED ──ack──▶ ACTIVE_ACKED ──clear──▶ NORMAL
                        │                                    ▲
                      clear                                  │
                        ▼                                    │
                  CLEARED_UNACKED ───────────ack─────────────┘
                        └──active──▶ ACTIVE_UNACKED
```

An alarm only returns to NORMAL once its condition has cleared *and* it has been
acknowledged, so a transient that came and went is never lost.

## License

[MIT](LICENSE)
