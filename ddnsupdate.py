import dns.update
import dns.query
import dns.tsigkeyring
import re

from load_cfg import load_ddns_config
from validators import _validate_hostname

_ALLOWED_RECORD_TYPES = {"A", "AAAA", "PTR", "CNAME", "TXT", "DHCID"}


def delete_dns_record(record_type, record_name):
    if record_type not in _ALLOWED_RECORD_TYPES:
        raise ValueError(f"Invalid record type: {record_type!r}")
    if not _validate_hostname(record_name):
        raise ValueError(f"Invalid record name: {record_name!r}")

    ddns_cfg = load_ddns_config()
    keyring = dns.tsigkeyring.from_text({
        ddns_cfg["tsig_key_name"]: ddns_cfg["tsig_key_secret"],
    })

    short_name = re.sub(rf"\.{re.escape(ddns_cfg['zone'])}\.?$", "", record_name)

    update = dns.update.Update(ddns_cfg["zone"], keyring=keyring, keyalgorithm="hmac-sha256")
    update.delete(short_name, record_type)
    update.delete(short_name, "DHCID")  # Remove associated DHCID record if it exists
    response = dns.query.tcp(update, ddns_cfg["server"])
    if response.rcode() != 0:
        raise Exception(f"Failed to delete DNS record: {dns.rcode.to_text(response.rcode())}")
    return response
