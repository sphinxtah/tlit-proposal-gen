# TeamLogic IT Proposal Studio v0.1.0

Internal intake, pricing, editable PowerPoint proposals, and PDF managed services agreements. Runs without Microsoft Office in production.

## Public repository and local data

The checked-in example is fictional. Original client documents, generated exports, SQLite databases, credentials, and local overrides are excluded from Git. A local `templates/example.private.json` can replace the demo through an ignored `compose.override.yaml` read-only mount; it is also excluded from the Docker image. Never commit real client records or completed payment forms.

The template extraction helper accepts `--document`, `--presentation`, `--client-name` and `--proposal-month`. It is tailored to the original reference structure; inspect extracted content before committing templates from another source.

## Local start

```powershell
docker compose -p tlit-proposal-gen up -d --build
docker compose -p tlit-proposal-gen exec app python -m app.manage add-user your-username
docker compose -p tlit-proposal-gen exec app python -m app.manage add-user tal
```

The commands prompt privately for passwords (12+ characters). There are no default/shared credentials. Open http://localhost:8088 and sign in. Load the Example Company example to exercise the full workflow. Save a draft, review pricing/scope/tax notes, then generate the ZIP containing PPTX, PDF, input JSON and a manifest.

In Docker Desktop's **Exec** tab you are already inside the container. Run `python -m app.manage add-user your-username` there, without the `docker compose exec app` prefix. Password input is intentionally invisible.

Only this Compose project is created/modified. It has its own `tlit-proposal-gen` network and named `proposal-data` volume. Default binding is localhost only. Original DOCX/PPTX examples are never modified and are not copied into the Docker image; prepared templates are.

## Run tests

```powershell
docker compose -p tlit-proposal-gen exec app python -m pytest -q
```

Tests use a temporary database, never the working proposal database. Covers billing modes, Decimal math, taxable allocation, invalid inputs, authentication, draft persistence, ZIP/document content and long-content pagination.

## Acadia deployment (dedicated Debian 13 VM)

Install Docker Engine with the Compose plugin using Docker's Debian instructions. Copy this project (excluding `tmp`, `output`, local `data`, and the two original example files) to `/opt/tlit-proposal-gen`. Then:

```sh
cd /opt/tlit-proposal-gen
docker compose -p tlit-proposal-gen up -d --build
docker compose -p tlit-proposal-gen exec app python -m app.manage add-user YOUR_USERNAME
docker compose -p tlit-proposal-gen exec app python -m app.manage add-user tal
```

For intranet access, place an HTTPS reverse proxy on the Debian VM in front of `127.0.0.1:8088` and point an internal DNS name at it. Set `COOKIE_SECURE=true` in the container environment via a Compose override for HTTPS. Default cookie behavior supports localhost HTTP development. Do not expose the Docker socket to the app. This project has not been deployed to Acadia: VM address/DNS/access details are still needed.

If a separate reverse-proxy container is used, connect only that proxy to this project's network and route it to `app:8000`. No internet-facing access is required. Provision the local TLS certificate through your intranet's trust/certificate process.

## Operations

```sh
# Status and logs, scoped to this project
docker compose -p tlit-proposal-gen ps
docker compose -p tlit-proposal-gen logs --tail 100 app
# Reset a user's password and invalidate existing sessions
docker compose -p tlit-proposal-gen exec app python -m app.manage reset-password tal
# Stop without deleting drafts or credentials
docker compose -p tlit-proposal-gen stop
```

Back up the SQLite database using SQLite's backup API (not a live raw file copy):

```sh
docker compose -p tlit-proposal-gen exec app python -c "import sqlite3; s=sqlite3.connect('/app/data/proposals.sqlite3'); d=sqlite3.connect('/app/data/backup.sqlite3'); s.backup(d); d.close(); s.close()"
docker compose -p tlit-proposal-gen cp app:/app/data/backup.sqlite3 ./backup.sqlite3
```

Store the backup securely with a copy of `templates/`. Restore only to a stopped instance, replacing its database within the named volume, and restart. Do not run `down -v` unless intentionally deleting all proposals and accounts. Test restores on a separate instance before relying on backups.

## Code map

- `app/models.py`: validated intake schema and authoritative pricing.
- `app/main.py`: authenticated API, drafts, sessions and export.
- `app/manage.py`: private account provisioning/reset.
- `app/static/`: responsive browser UI, no frontend build step.
- `app/generate.py`: template PPTX and flowing PDF renderers.
- `templates/`: editable PPTX, extracted contract text, scope and example JSON.
- `scripts/prepare_templates.py`: one-time extraction from originals (requires python-docx outside production image).
- `docs/PLAN.md`: scope, architecture, known template issues and next increments.
- `docs/TAX-RESEARCH.md`: sourced tax findings and implementation limits.

Both users share drafts and version history. Save explicitly; exporting also saves a revision and retains the exact documents. Stale saves are rejected if another session changed the proposal. History older than one year is compressed automatically. Individual deletion and previewed bulk deletion of history older than two years are available in Version history. See [history and retention](docs/HISTORY.md) for precise behavior and backup considerations.

Session lifetime is eight hours. Passwords use salted scrypt hashes, cookies are HttpOnly/SameSite Strict, writes require a custom request header, and login attempts are rate-limited. Accounts currently have equal access, including deletion.
