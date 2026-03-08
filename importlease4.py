"""
importlease4.py — Import a Kea memfile CSV into the MySQL lease4 table.

Usage:
    python importlease4.py leases4.csv
    python importlease4.py leases4.csv --update   # upsert: overwrite existing rows
    python importlease4.py leases4.csv --dry-run  # show what would be inserted
"""

import argparse
import configparser
import csv
import os
import socket
import struct
import sys
from datetime import datetime

import mysql.connector

_CONFIG_PATHS = [
    os.path.join(os.path.dirname(__file__), "config.ini"),
    "/etc/keadhcp/config.ini",
]


def _load_db_config():
    cfg = configparser.ConfigParser()
    cfg.read(_CONFIG_PATHS)
    return cfg["mysql"]


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------

def ip_to_int(ip_str):
    """Dotted IPv4 string → unsigned 32-bit int (network byte order)."""
    return struct.unpack("!I", socket.inet_aton(ip_str))[0]


def mac_to_bytes(mac_str):
    """Colon-separated hex MAC (e.g. '6e:08:b9:26:a1:6f') → bytes."""
    if not mac_str:
        return None
    return bytes.fromhex(mac_str.replace(":", ""))


def hex_id_to_bytes(hex_str):
    """Colon-separated hex client/relay/remote id → bytes, or None if empty."""
    if not hex_str:
        return None
    return bytes.fromhex(hex_str.replace(":", ""))


def unix_to_datetime(ts_str):
    """Unix timestamp string → Python datetime (for MySQL TIMESTAMP column)."""
    return datetime.fromtimestamp(int(ts_str))


def str_or_none(value):
    """Return None for empty strings, otherwise the stripped string."""
    s = value.strip()
    return s if s else None


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_connection():
    db = _load_db_config()
    return mysql.connector.connect(
        host=db["host"],
        database=db["database"],
        user=db["user"],
        password=db["password"],
    )


# ---------------------------------------------------------------------------
# CSV → row conversion
# ---------------------------------------------------------------------------

def csv_row_to_db(row):
    """
    Convert a CSV row dict to a tuple of values matching the INSERT statement.
    Table columns not present in the CSV (relay_id, remote_id) fall back to
    their schema defaults (NULL).
    """
    return (
        ip_to_int(row["address"]),                 # address  INT UNSIGNED
        mac_to_bytes(row["hwaddr"]),               # hwaddr   VARBINARY(20)
        hex_id_to_bytes(row["client_id"]),         # client_id VARBINARY(255)
        int(row["valid_lifetime"]),                # valid_lifetime INT UNSIGNED
        unix_to_datetime(row["expire"]),           # expire   TIMESTAMP
        int(row["subnet_id"]),                     # subnet_id INT UNSIGNED
        int(row["fqdn_fwd"]),                      # fqdn_fwd TINYINT
        int(row["fqdn_rev"]),                      # fqdn_rev TINYINT
        str_or_none(row["hostname"]),              # hostname VARCHAR(255)
        int(row["state"]),                         # state    INT UNSIGNED
        str_or_none(row["user_context"]),          # user_context TEXT
        None,                                      # relay_id  — not in CSV, default NULL
        None,                                      # remote_id — not in CSV, default NULL
        int(row["pool_id"]),                       # pool_id  INT UNSIGNED
    )


INSERT_SQL = """
    INSERT INTO lease4
        (address, hwaddr, client_id, valid_lifetime, expire,
         subnet_id, fqdn_fwd, fqdn_rev, hostname, state,
         user_context, relay_id, remote_id, pool_id)
    VALUES
        (%s, %s, %s, %s, %s,
         %s, %s, %s, %s, %s,
         %s, %s, %s, %s)
"""

UPSERT_SQL = INSERT_SQL.rstrip() + """
    ON DUPLICATE KEY UPDATE
        hwaddr         = VALUES(hwaddr),
        client_id      = VALUES(client_id),
        valid_lifetime = VALUES(valid_lifetime),
        expire         = VALUES(expire),
        subnet_id      = VALUES(subnet_id),
        fqdn_fwd       = VALUES(fqdn_fwd),
        fqdn_rev       = VALUES(fqdn_rev),
        hostname       = VALUES(hostname),
        state          = VALUES(state),
        user_context   = VALUES(user_context),
        relay_id       = VALUES(relay_id),
        remote_id      = VALUES(remote_id),
        pool_id        = VALUES(pool_id)
"""


# ---------------------------------------------------------------------------
# Main import logic
# ---------------------------------------------------------------------------

def import_leases(csv_path, update=False, dry_run=False):
    sql = UPSERT_SQL if update else INSERT_SQL

    rows = []
    errors = []

    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for line_num, row in enumerate(reader, start=2):  # 2 = first data line
            try:
                rows.append(csv_row_to_db(row))
            except Exception as exc:
                errors.append(f"  Line {line_num} [{row.get('address', '?')}]: {exc}")

    if errors:
        print(f"WARNING: {len(errors)} row(s) skipped due to conversion errors:")
        for e in errors:
            print(e)

    if not rows:
        print("No valid rows to import.")
        return

    if dry_run:
        print(f"Dry run — {len(rows)} row(s) would be {'upserted' if update else 'inserted'}:")
        for r in rows:
            print(f"  address={socket.inet_ntoa(struct.pack('!I', r[0]))} "
                  f"hwaddr={r[1].hex() if r[1] else None} "
                  f"hostname={r[8]} expire={r[4]}")
        return

    conn = get_connection()
    try:
        cursor = conn.cursor()
        inserted = updated = skipped = 0

        for params in rows:
            try:
                cursor.execute(sql, params)
                # affected_rows: 1 = inserted, 2 = updated (ON DUPLICATE KEY), 0 = no change
                if cursor.rowcount == 1:
                    inserted += 1
                elif cursor.rowcount == 2:
                    updated += 1
                else:
                    skipped += 1
            except mysql.connector.Error as exc:
                ip = socket.inet_ntoa(struct.pack("!I", params[0]))
                print(f"  ERROR inserting {ip}: {exc}")
                conn.rollback()
                continue

        conn.commit()
        cursor.close()

        mode = "upsert" if update else "insert"
        print(f"Done ({mode} mode): {inserted} inserted, {updated} updated, "
              f"{skipped} unchanged, {len(errors)} skipped (bad data).")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Import a Kea memfile CSV into the MySQL lease4 table"
    )
    parser.add_argument("csv_file", help="Path to the memfile CSV")
    parser.add_argument(
        "--update", action="store_true",
        help="Upsert: overwrite existing rows that share the same IP address"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse and validate the CSV without writing to the database"
    )
    args = parser.parse_args()

    import_leases(args.csv_file, update=args.update, dry_run=args.dry_run)
