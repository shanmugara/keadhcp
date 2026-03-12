"""db.py — database connection and raw data-type helpers."""

import configparser
import os
import socket
import struct

import mysql.connector

_CONFIG_PATHS = [
    os.path.join(os.path.dirname(__file__), "uiconfig.ini"),
    "/etc/kea/uiconfig.ini",
]


def _load_db_config():
    cfg = configparser.ConfigParser()
    cfg.read(_CONFIG_PATHS)
    return cfg["mysql"]


def get_connection():
    db = _load_db_config()
    return mysql.connector.connect(
        host=db["host"],
        database=db["database"],
        user=db["user"],
        password=db["password"],
        # Fail fast if the DB host is unreachable instead of hanging a worker.
        connection_timeout=10,
        # Apply session-level read/write timeouts so a slow or locked query
        # doesn't block the worker indefinitely.
        init_command="SET SESSION net_read_timeout=60, net_write_timeout=60",
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


def _mac_to_bytes(mac):
    return bytes(int(b, 16) for b in mac.split(':'))


def _ip_to_int(ip):
    return struct.unpack(">I", socket.inet_pton(socket.AF_INET, ip))[0]
