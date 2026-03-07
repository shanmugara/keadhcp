"""
app.py — Flask web UI for the Kea DHCP lease4 table.

Run:
    python app.py
Then open http://127.0.0.1:5000
"""

import socket
import struct
from datetime import datetime, timezone

import mysql.connector
from flask import Flask, render_template, request

app = Flask(__name__)


# ---------------------------------------------------------------------------
# DB helpers (re-used from readlease4.py logic)
# ---------------------------------------------------------------------------

def get_connection():
    return mysql.connector.connect(
        host="localhost",
        database="kea",
        user="kea",
        password="secret",
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
        leases=leases,
        search=search,
        sort_col=sort_col,
        sort_dir=sort_dir,
        error=error,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
