"""validators.py — input validation helpers."""

import re

_MAC_RE = re.compile(r'^([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$')
_HOSTNAME_LABEL_RE = re.compile(r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$')


def _validate_mac(mac):
    return bool(_MAC_RE.match(mac))


def _validate_hostname(name):
    """Accept a short hostname or FQDN (RFC 1123, ≤253 chars)."""
    if not name or len(name) > 253:
        return False
    labels = name.rstrip('.').split('.')
    return bool(labels) and all(_HOSTNAME_LABEL_RE.match(lbl) for lbl in labels)
