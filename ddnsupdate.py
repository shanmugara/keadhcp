import dns.update
import dns.query
import dns.tsigkeyring
import re

from load_cfg import load_ddns_config


def delete_dns_record(record_type, record_name):
    ddns_cfg = load_ddns_config()
    keyring = dns.tsigkeyring.from_text({
        ddns_cfg["tsig_key_name"]: ddns_cfg["tsig_key_secret"],
    })

    short_name = re.sub(rf"\.{ddns_cfg['zone']}\.?$", "", record_name)

    update = dns.update.Update(ddns_cfg["zone"], keyring=keyring, keyalgorithm="hmac-sha256")
    update.delete(short_name, record_type)
    response = dns.query.tcp(update, ddns_cfg["server"])
    if response.rcode() != 0:
        raise Exception(f"Failed to delete DNS record: {dns.rcode.to_text(response.rcode())}")
    return response
