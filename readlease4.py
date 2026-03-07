import argparse
import socket
import struct

import mysql.connector
from tabulate import tabulate


def int_to_ip(addr):
    """Convert unsigned int to dotted IPv4 string."""
    return socket.inet_ntoa(struct.pack(">I", addr))


def bytes_to_mac(raw):
    """Format raw bytes as a colon-separated MAC address string."""
    if raw is None:
        return None
    return ":".join(f"{b:02x}" for b in raw)


def bytes_to_hex(raw):
    """Format raw bytes as a hex string."""
    if raw is None:
        return None
    return raw.hex()


def get_connection():
    return mysql.connector.connect(
        host="localhost",
        database="kea",
        user="kea",
        password="secret",
    )


def convert_row(record):
    """Return a dict with all fields converted to human-readable values."""
    return {
        "address":        int_to_ip(record["address"]),
        "hwaddr":         bytes_to_mac(record["hwaddr"]),
        "client_id":      bytes_to_hex(record["client_id"]),
        "valid_lifetime": record["valid_lifetime"],
        "expire":         record["expire"],
        "subnet_id":      record["subnet_id"],
        "pool_id":        record["pool_id"],
        "fqdn_fwd":       bool(record["fqdn_fwd"]),
        "fqdn_rev":       bool(record["fqdn_rev"]),
        "hostname":       record["hostname"],
        "state":          record["state"],
        "relay_id":       bytes_to_hex(record["relay_id"]),
        "remote_id":      bytes_to_hex(record["remote_id"]),
        "user_context":   record["user_context"],
    }


def read_lease4(table_format=False):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM lease4 ORDER BY address")
        rows = cursor.fetchall()
        columns = [col[0] for col in cursor.description]

        print(f"Total leases: {len(rows)}\n")

        records = [convert_row(dict(zip(columns, row))) for row in rows]

        if table_format:
            print(tabulate(records, headers="keys", tablefmt="grid"))
        else:
            print("=" * 70)
            for rec in records:
                print(f"Address       : {rec['address']}")
                print(f"HW Address    : {rec['hwaddr']}")
                print(f"Client ID     : {rec['client_id']}")
                print(f"Valid Lifetime: {rec['valid_lifetime']} seconds")
                print(f"Expire        : {rec['expire']}")
                print(f"Subnet ID     : {rec['subnet_id']}")
                print(f"Pool ID       : {rec['pool_id']}")
                print(f"FQDN Fwd      : {rec['fqdn_fwd']}")
                print(f"FQDN Rev      : {rec['fqdn_rev']}")
                print(f"Hostname      : {rec['hostname']}")
                print(f"State         : {rec['state']}")
                print(f"Relay ID      : {rec['relay_id']}")
                print(f"Remote ID     : {rec['remote_id']}")
                print(f"User Context  : {rec['user_context']}")
                print("-" * 70)

        cursor.close()
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read Kea DHCP lease4 table")
    parser.add_argument(
        "--table", action="store_true",
        help="Print output in table format instead of per-record blocks"
    )
    args = parser.parse_args()
    read_lease4(table_format=args.table)
