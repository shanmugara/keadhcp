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


def fetch_subnet_ids():
    """Return a sorted list of distinct subnet_id values in lease4."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT subnet_id FROM lease4 ORDER BY subnet_id")
        rows = cursor.fetchall()
        cursor.close()
        return [r[0] for r in rows]
    finally:
        conn.close()


def fetch_leases(search=None, subnet_id=None, sort_col="address", sort_dir="asc"):
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
        if subnet_id is not None:
            cursor.execute(
                f"SELECT * FROM lease4 WHERE subnet_id = %s ORDER BY {sort_col} {sort_dir}",
                (subnet_id,)
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

IDENTIFIER_TYPE_LABELS = {
    0: "hw-address",
    1: "duid",
    2: "circuit-id",
    3: "client-id",
    4: "flex-id",
}


def fetch_reservations(search=None, subnet_id=None, sort_col="ipv4_address", sort_dir="asc"):
    allowed_sort_cols = {
        "host_id", "ipv4_address", "hostname", "dhcp4_subnet_id",
        "dhcp_identifier_type", "dhcp4_client_classes",
    }
    if sort_col not in allowed_sort_cols:
        sort_col = "ipv4_address"
    if sort_dir not in ("asc", "desc"):
        sort_dir = "asc"

    conn = get_connection()
    try:
        cursor = conn.cursor()
        if subnet_id is not None:
            cursor.execute(
                f"SELECT * FROM hosts WHERE dhcp4_subnet_id = %s ORDER BY {sort_col} {sort_dir}",
                (subnet_id,),
            )
        else:
            cursor.execute(
                f"SELECT * FROM hosts ORDER BY {sort_col} {sort_dir}"
            )
        columns = [col[0] for col in cursor.description]
        raw_rows = cursor.fetchall()
        cursor.close()
    finally:
        conn.close()

    reservations = []
    for row in raw_rows:
        r = dict(zip(columns, row))
        ip = int_to_ip(r["ipv4_address"]) if r["ipv4_address"] else ""
        next_server = int_to_ip(r["dhcp4_next_server"]) if r["dhcp4_next_server"] else ""
        id_type = r["dhcp_identifier_type"]
        if id_type == 0:
            identifier = bytes_to_mac(r["dhcp_identifier"])
        else:
            identifier = bytes_to_hex(r["dhcp_identifier"])

        if search:
            needle = search.lower()
            if not any(needle in str(v).lower() for v in [
                ip, identifier, r["hostname"] or "",
                r["dhcp4_subnet_id"], r["dhcp4_client_classes"] or "",
            ]):
                continue

        reservations.append({
            "host_id":             r["host_id"],
            "identifier":          identifier,
            "identifier_type":     IDENTIFIER_TYPE_LABELS.get(id_type, str(id_type)),
            "dhcp4_subnet_id":     r["dhcp4_subnet_id"],
            "ipv4_address":        ip,
            "hostname":            r["hostname"] or "",
            "dhcp4_client_classes": r["dhcp4_client_classes"] or "",
            "dhcp4_next_server":   next_server,
            "dhcp4_server_hostname": r["dhcp4_server_hostname"] or "",
            "dhcp4_boot_file_name": r["dhcp4_boot_file_name"] or "",
            "user_context":        r["user_context"] or "",
            "auth_key":            r["auth_key"] or "",
        })

    return reservations


def fetch_reservation_subnet_ids():
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT DISTINCT dhcp4_subnet_id FROM hosts "
            "WHERE dhcp4_subnet_id IS NOT NULL ORDER BY dhcp4_subnet_id"
        )
        rows = cursor.fetchall()
        cursor.close()
        return [r[0] for r in rows]
    finally:
        conn.close()


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
    search    = request.args.get("q", "").strip()
    sort_col  = request.args.get("sort", "address")
    sort_dir  = request.args.get("dir", "asc")
    subnet_id = request.args.get("subnet", "").strip()

    subnet_id_int = None
    if subnet_id:
        try:
            subnet_id_int = int(subnet_id)
        except ValueError:
            subnet_id = ""

    error = None
    leases = []
    subnet_ids = []
    try:
        subnet_ids = fetch_subnet_ids()
        leases = fetch_leases(search=search or None,
                              subnet_id=subnet_id_int,
                              sort_col=sort_col, sort_dir=sort_dir)
    except Exception as exc:
        error = str(exc)

    return render_template(
        "index.html",
        active_page="leases",
        leases=leases,
        search=search,
        subnet_id=subnet_id,
        subnet_ids=subnet_ids,
        sort_col=sort_col,
        sort_dir=sort_dir,
        error=error,
    )


@app.route("/reservations")
def reservations():
    search    = request.args.get("q", "").strip()
    sort_col  = request.args.get("sort", "ipv4_address")
    sort_dir  = request.args.get("dir", "asc")
    subnet_id = request.args.get("subnet", "").strip()

    subnet_id_int = None
    if subnet_id:
        try:
            subnet_id_int = int(subnet_id)
        except ValueError:
            subnet_id = ""

    error = None
    hosts = []
    subnet_ids = []
    try:
        subnet_ids = fetch_reservation_subnet_ids()
        hosts = fetch_reservations(
            search=search or None,
            subnet_id=subnet_id_int,
            sort_col=sort_col,
            sort_dir=sort_dir,
        )
    except Exception as exc:
        error = str(exc)

    return render_template(
        "reservations.html",
        active_page="reservations",
        hosts=hosts,
        search=search,
        subnet_id=subnet_id,
        subnet_ids=subnet_ids,
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
