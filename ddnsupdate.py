import dns.update
import dns.query
import dns.tsigkeyring

from load_cfg import load_ddns_config


def delete_dns_record(zone, record_type, record_name):
    ddns_cfg = load_ddns_config()
    keyring = dns.tsigkeyring.from_text({
        ddns_cfg["tsig_key_name"]: ddns_cfg["tsig_key_secret"],
    })

    short_name = record_name.rstrip('.' + zone)

    update = dns.update.Update(zone, keyring=keyring, keyalgorithm="hmac-sha256")
    update.delete(short_name, record_type)
    response = dns.query.tcp(update, ddns_cfg["server"])
    if response.rcode() != 0:
        raise Exception(f"Failed to delete DNS record: {dns.rcode.to_text(response.rcode())}")
    return response
