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
- Live telemetry: `ws://localhost:8000/ws/telemetry` (10 Hz JSON)

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
- [ ] JWT auth with roles
- [ ] Recharts dashboard

## License

[MIT](LICENSE)
