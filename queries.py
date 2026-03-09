"""queries.py — database query functions and log reader."""

from collections import deque
from datetime import datetime

from db import bytes_to_hex, bytes_to_mac, get_connection, int_to_ip

STATE_LABELS = {0: "Default", 1: "Declined", 2: "Expired-Reclaimed"}

IDENTIFIER_TYPE_LABELS = {
    0: "hw-address",
    1: "duid",
    2: "circuit-id",
    3: "client-id",
    4: "flex-id",
}

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
