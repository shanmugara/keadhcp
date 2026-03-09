"""
app.py — Flask web UI for the Kea DHCP lease4 table.

Run:
    python app.py
Then open http://127.0.0.1:5000
"""

import socket

from flask import Blueprint, Flask, jsonify, render_template, request

from db import _ip_to_int, _mac_to_bytes, bytes_to_hex, bytes_to_mac, get_connection, int_to_ip
from queries import (
    IDENTIFIER_TYPE_LABELS,
    LOG_FILE,
    fetch_leases,
    fetch_reservation_subnet_ids,
    fetch_reservations,
    fetch_subnet_ids,
    read_log_tail,
)
from validators import _validate_hostname, _validate_mac

app = Flask(__name__)

api_v1 = Blueprint("api_v1", __name__, url_prefix="/api/v1")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def home():
    return render_template("home.html", active_page="home")


@app.route("/leases")
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


# ---------------------------------------------------------------------------
# REST API — v1
# ---------------------------------------------------------------------------

@api_v1.route("/reservations/search", methods=["GET"])
def api_search_reservation():
    """Look up reservations by ?ip=, ?mac=, or ?hostname= (one at a time)."""
    ip       = request.args.get("ip",       "").strip()
    mac      = request.args.get("mac",      "").strip()
    hostname = request.args.get("hostname", "").strip()

    if not any([ip, mac, hostname]):
        return jsonify({"error": "Provide at least one query parameter: ip, mac, or hostname"}), 400

    try:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            if ip:
                try:
                    ip_int = _ip_to_int(ip)
                except socket.error:
                    return jsonify({"error": "Invalid IPv4 address"}), 422
                cursor.execute(
                    "SELECT * FROM hosts WHERE ipv4_address = %s", (ip_int,)
                )
            elif mac:
                if not _validate_mac(mac):
                    return jsonify({"error": "Invalid MAC address (expected xx:xx:xx:xx:xx:xx)"}), 422
                cursor.execute(
                    "SELECT * FROM hosts WHERE dhcp_identifier = %s AND dhcp_identifier_type = 0",
                    (_mac_to_bytes(mac),),
                )
            else:
                cursor.execute(
                    "SELECT * FROM hosts WHERE hostname = %s", (hostname,)
                )
            columns = [col[0] for col in cursor.description]
            raw_rows = cursor.fetchall()
            cursor.close()
        finally:
            conn.close()
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    results = []
    for row in raw_rows:
        r = dict(zip(columns, row))
        id_type = r["dhcp_identifier_type"]
        results.append({
            "host_id":               r["host_id"],
            "identifier":            bytes_to_mac(r["dhcp_identifier"]) if id_type == 0 else bytes_to_hex(r["dhcp_identifier"]),
            "identifier_type":       IDENTIFIER_TYPE_LABELS.get(id_type, str(id_type)),
            "dhcp4_subnet_id":       r["dhcp4_subnet_id"],
            "ipv4_address":          int_to_ip(r["ipv4_address"]) if r["ipv4_address"] else None,
            "hostname":              r["hostname"],
            "dhcp4_client_classes":  r["dhcp4_client_classes"],
            "dhcp4_next_server":     int_to_ip(r["dhcp4_next_server"]) if r["dhcp4_next_server"] else None,
            "dhcp4_server_hostname": r["dhcp4_server_hostname"],
            "dhcp4_boot_file_name":  r["dhcp4_boot_file_name"],
            "user_context":          r["user_context"],
            "auth_key":              r["auth_key"],
        })

    if not results:
        return jsonify({"error": "No reservation found"}), 404
    return jsonify(results), 200


@api_v1.route("/reservations", methods=["POST"])
def api_create_reservation():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    errors = {}

    mac = (data.get("dhcp_identifier") or "").strip()
    if not mac:
        errors["dhcp_identifier"] = "Required"
    elif not _validate_mac(mac):
        errors["dhcp_identifier"] = "Must be a valid MAC address (xx:xx:xx:xx:xx:xx)"

    ipv4 = (data.get("ipv4_address") or "").strip()
    if not ipv4:
        errors["ipv4_address"] = "Required"
    else:
        try:
            socket.inet_pton(socket.AF_INET, ipv4)
        except socket.error:
            errors["ipv4_address"] = "Must be a valid IPv4 address"

    raw_subnet = data.get("dhcp4_subnet_id")
    subnet_id_val = None
    if raw_subnet is None or str(raw_subnet).strip() == "":
        errors["dhcp4_subnet_id"] = "Required"
    else:
        try:
            subnet_id_val = int(raw_subnet)
            if subnet_id_val < 0:
                raise ValueError
        except (ValueError, TypeError):
            errors["dhcp4_subnet_id"] = "Must be a non-negative integer"

    hostname = (data.get("hostname") or "").strip()
    if not hostname:
        errors["hostname"] = "Required"
    elif not _validate_hostname(hostname):
        errors["hostname"] = "Must be a valid DNS name (shortname or FQDN)"

    if errors:
        return jsonify({"errors": errors}), 422

    try:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO hosts
                  (dhcp_identifier, dhcp_identifier_type,
                   dhcp4_subnet_id, ipv4_address, hostname)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (_mac_to_bytes(mac), 0, subnet_id_val, _ip_to_int(ipv4), hostname),
            )
            conn.commit()
            new_id = cursor.lastrowid
            cursor.close()
        finally:
            conn.close()
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify({"host_id": new_id, "message": "Reservation created"}), 201


@api_v1.route("/reservations/<int:host_id>", methods=["DELETE"])
def api_delete_reservation(host_id):
    try:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM hosts WHERE host_id = %s", (host_id,))
            conn.commit()
            affected = cursor.rowcount
            cursor.close()
        finally:
            conn.close()
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    if affected == 0:
        return jsonify({"error": "Reservation not found"}), 404
    return jsonify({"message": "Reservation deleted"}), 200


app.register_blueprint(api_v1)


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
