"""
app.py — Flask web UI for the Kea DHCP lease4 table.

Run:
    python app.py
Then open http://127.0.0.1:5000
"""

import configparser
import os
import socket
import struct
from collections import deque
from datetime import datetime

import mysql.connector
from flask import Flask, render_template, request

app = Flask(__name__)

_CONFIG_PATHS = [
    os.path.join(os.path.dirname(__file__), "uiconfig.ini"),
    "/etc/kea/uiconfig.ini",
]


def _load_db_config():
    cfg = configparser.ConfigParser()
    cfg.read(_CONFIG_PATHS)
    return cfg["mysql"]


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_connection():
    db = _load_db_config()
    return mysql.connector.connect(
        host=db["host"],
        database=db["database"],
        user=db["user"],
        password=db["password"],
    )


def int_to_ip(addr):
    return socket.inet_ntoa(struct.pack(">I", addr))


def bytes_to_mac(raw):
    if raw is None:
        return ""
    return ":".join(f"{b:02x}" for b in raw)


def bytes_to_hex(raw):
    if raw is None:
        return ""
    return raw.hex()


STATE_LABELS = {0: "Default", 1: "Declined", 2: "Expired-Reclaimed"}


def fetch_leases(search=None, sort_col="address", sort_dir="asc"):
    allowed_sort_cols = {
        "address", "hwaddr", "hostname", "expire",
        "subnet_id", "state", "valid_lifetime", "pool_id",
    }
    if sort_col not in allowed_sort_cols:
        sort_col = "address"
    if sort_dir not in ("asc", "desc"):
        sort_dir = "asc"

    conn = get_connection()
    try:
        cursor = conn.cursor()
        if search:
            cursor.execute(
                f"SELECT * FROM lease4 ORDER BY {sort_col} {sort_dir}"
            )
        else:
            cursor.execute(
                f"SELECT * FROM lease4 ORDER BY {sort_col} {sort_dir}"
            )
        columns = [col[0] for col in cursor.description]
        raw_rows = cursor.fetchall()
        cursor.close()
    finally:
        conn.close()

    leases = []
    now = datetime.now()
    for row in raw_rows:
        r = dict(zip(columns, row))
        ip = int_to_ip(r["address"])
        hostname = r["hostname"] or ""
        mac = bytes_to_mac(r["hwaddr"])

        # Filter client-side after conversion so we can search IP / MAC too
        if search:
            needle = search.lower()
            if not any(needle in str(v).lower() for v in [ip, hostname, mac,
                       r["subnet_id"], r["state"]]):
                continue

        expire_dt = r["expire"]
        expired = expire_dt < now if expire_dt else False

        leases.append({
            "address":        ip,
            "hwaddr":         mac,
            "client_id":      bytes_to_hex(r["client_id"]),
            "valid_lifetime": r["valid_lifetime"],
            "expire":         expire_dt.strftime("%Y-%m-%d %H:%M:%S") if expire_dt else "",
            "expired":        expired,
            "subnet_id":      r["subnet_id"],
            "fqdn_fwd":       bool(r["fqdn_fwd"]),
            "fqdn_rev":       bool(r["fqdn_rev"]),
            "hostname":       hostname,
            "state":          STATE_LABELS.get(r["state"], str(r["state"])),
            "user_context":   r["user_context"] or "",
            "relay_id":       bytes_to_hex(r["relay_id"]),
            "remote_id":      bytes_to_hex(r["remote_id"]),
            "pool_id":        r["pool_id"],
        })

    return leases


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

LOG_FILE = "/var/log/kea/kea-dhcp4.log"


def read_log_tail(path, n=250):
    """Return the last *n* lines of *path* as a list. Never raises."""
    try:
        with open(path, "r", errors="replace") as fh:
            return list(deque(fh, maxlen=n))
    except FileNotFoundError:
        return None
    except PermissionError:
        return None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    search   = request.args.get("q", "").strip()
    sort_col = request.args.get("sort", "address")
    sort_dir = request.args.get("dir", "asc")

    error = None
    leases = []
    try:
        leases = fetch_leases(search=search or None,
                              sort_col=sort_col, sort_dir=sort_dir)
    except Exception as exc:
        error = str(exc)

    return render_template(
        "index.html",
        active_page="leases",
        leases=leases,
        search=search,
        sort_col=sort_col,
        sort_dir=sort_dir,
        error=error,
    )


@app.route("/logs")
def logs():
    try:
        lines = max(1, min(int(request.args.get("lines", 250)), 5000))
    except ValueError:
        lines = 250

    log_lines = read_log_tail(LOG_FILE, lines)

    if log_lines is None:
        error = f"Cannot read {LOG_FILE} — file not found or permission denied."
        log_lines = []
    else:
        # Strip trailing newlines from each line
        log_lines = [l.rstrip("\n") for l in log_lines]
        error = None

    return render_template(
        "logs.html",
        active_page="logs",
        log_lines=log_lines,
        log_file=LOG_FILE,
        lines=lines,
        error=error,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
