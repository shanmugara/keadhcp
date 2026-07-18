# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A set of Python tools for managing and viewing [Kea DHCP](https://www.isc.org/kea/) leases stored in a
MySQL/MariaDB database (`kea` database, `lease4` and `hosts` tables), plus a Flask web UI (`app.py`) and
standalone CLI scripts. Production deployment is via gunicorn + systemd on Ubuntu (see `keadhcp.service`
and the "Production Deployment" section of `README.md`).

## Commands

```bash
# Setup
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp config.ini.example config.ini   # then fill in real [mysql] and [ddns] credentials

# Run the Flask app (dev server, debug mode, binds 0.0.0.0:5000)
python app.py

# Run in production (as deployed by keadhcp.service)
gunicorn --workers 4 --timeout 120 --keep-alive 5 --bind 0.0.0.0:5000 \
  --access-logfile /var/log/keadhcp/access.log --error-logfile /var/log/keadhcp/error.log app:app

# Standalone CLI tools
python standalone_readlease4.py [--table]
python standalone_importlease4.py leases4.csv [--update] [--dry-run]
python standalone_dedupeleasecsv.py <input_csv> <output_csv>
```

There is no test suite, linter, or CI config in this repo — verify changes by running the app and hitting
routes/API endpoints against a real (or test) `kea` MySQL database, or by exercising the standalone scripts
against a sample CSV.

## Architecture

**`app.py`** is the single Flask application: it defines both the HTML page routes (`/`, `/leases`,
`/reservations`, `/logs`) and a REST API blueprint (`api_v1`, mounted at `/api/v1/...`) covering leases and
reservations CRUD. See `README.md` for the full REST API reference (endpoints, params, status codes,
response shapes) before changing API behavior — it documents the contract in detail.

Supporting modules, all imported by `app.py`:
- **`db.py`** — MySQL connection factory (`get_connection`, via `load_cfg.load_db_config()`) and low-level
  binary/int codec helpers used throughout: `int_to_ip`/`_ip_to_int` (IPv4 ↔ uint32, matching Kea's
  `lease4.address`/`hosts.ipv4_address` storage), `bytes_to_mac`/`_mac_to_bytes` (MAC ↔ `VARBINARY`), and
  `bytes_to_hex` (for `client_id`/`relay_id`/`remote_id` binary columns).
- **`queries.py`** — all `SELECT` query logic for `fetch_leases()` and `fetch_reservations()`, including
  sort-column allowlisting (never interpolate `sort_col`/`sort_dir` directly — check the allowlist pattern
  here), IP/MAC/hostname search dispatch, and `read_log_tail()` for the `/logs` page.
- **`validators.py`** — `_validate_mac()` and `_validate_hostname()`, used for both API-level 422 validation
  and DNS record name validation in `ddnsupdate.py`.
- **`ddnsupdate.py`** — `delete_dns_record()` sends an RFC 2136 TSIG-authenticated DNS UPDATE (via
  `dnspython`) to remove `A`/`DHCID` records when a lease is deleted through the API. Called from
  `api_delete_lease` when a `record_name` query param is supplied; failures there return a 500 even though
  the lease row was already deleted — this is a known asymmetry to be aware of when touching that route.
- **`load_cfg.py`** — reads `[mysql]` and `[ddns]` sections via `configparser`.

**Config-loading inconsistency (important gotcha):** `load_cfg.py` (used by `app.py`/`db.py`/
`ddnsupdate.py`) looks for **`uiconfig.ini`** (local dir, then `/etc/kea/uiconfig.ini`) — not `config.ini`.
The standalone scripts (`standalone_readlease4.py`, `standalone_importlease4.py`) each embed their *own*
independent config loader that reads **`config.ini`** (local dir, then `/etc/keadhcp/config.ini`) and do
**not** import `db.py`/`load_cfg.py` at all, duplicating the codec helpers instead. `README.md` and
`config.ini.example` both describe the `config.ini` path. If the Flask app fails to find DB credentials,
check this mismatch first rather than assuming `config.ini` is being read; when editing shared logic
(connection setup, codec helpers), remember it is duplicated across `db.py` and the two standalone scripts
rather than shared.

**Audit logging:** `app.py` writes reservation create/delete/import events to a dedicated
`keadhcp.audit` logger (`/var/log/keadhcp/api_audit.log`, rotating). Any new mutating API route should log
through `_audit_log` following the existing `caller=... field=value` message format.

**Templates** (`templates/`) use server-rendered Jinja2 with Bootstrap 5 (via CDN) and a shared sidebar
layout in `base.html` (`active_page` block var selects the highlighted nav item). No frontend build step —
`index.html`/`reservations.html` contain inline `<script>` for client-side search/sort/filter and modal
forms that call the `/api/v1/...` JSON endpoints directly via `fetch`.

**Data model notes:** IPv4 addresses are stored as unsigned 32-bit big-endian ints in MySQL (Kea's native
schema), MAC/client/relay/remote IDs as `VARBINARY`. Every query function converts these to human-readable
JSON at the boundary — never return raw bytes/ints from a new API route without going through the `db.py`
converters.
