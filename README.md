# Kea DHCP Lease Viewer

A set of Python tools for managing and viewing [Kea DHCP](https://www.isc.org/kea/) leases stored in a MySQL database, plus a Flask web UI.

## Files

| File | Purpose |
|---|---|
| `readlease4.py` | Read and print all `lease4` rows from MySQL |
| `importlease4.py` | Import a Kea memfile CSV into the `lease4` MySQL table |
| `app.py` | Flask web UI to browse leases and view logs |
| `config.ini` | Database credentials (gitignored — do not commit) |
| `config.ini.example` | Template for `config.ini` |
| `keadhcp.service` | systemd unit file for production deployment |

## Requirements

- Python 3.9+
- MySQL/MariaDB with the `kea` database

---

## Configuration

All scripts read database credentials from `config.ini` (next to the script) or `/etc/keadhcp/config.ini` (production).

Copy the example and fill in your values:
```bash
cp config.ini.example config.ini
```

`config.ini` is gitignored and will never be committed.

```ini
[mysql]
# Hostname or IP address of the MySQL/MariaDB server
host     = localhost

# Name of the Kea database
database = kea

# MySQL user with SELECT/INSERT/UPDATE access to the kea database
user     = kea

# Password for the above user
password = secret
```

---

## Usage

### readlease4.py

Print all leases in per-record block format:
```bash
python readlease4.py
```

Print all leases in a grid table format:
```bash
python readlease4.py --table
```

---

### importlease4.py

Import a memfile CSV (insert new rows only, skip duplicates):
```bash
python importlease4.py leases4.csv
```

Upsert — overwrite existing rows that share the same IP address:
```bash
python importlease4.py leases4.csv --update
```

Validate the CSV without writing to the database:
```bash
python importlease4.py leases4.csv --dry-run
```

---

### app.py (Flask web UI)

```bash
python app.py
```

Then open `http://<host-ip>:5000` in your browser.

**Pages:**

| Page | URL | Description |
|---|---|---|
| Leases | `/` | Browse all `lease4` rows with search, sort, and active/expired highlighting |
| Logs | `/logs` | Tail `/var/log/kea/kea-dhcp4.log` with level badges, filtering, and auto-refresh |

**Leases features:**
- Live search/filter by IP, MAC, hostname, or subnet
- Sortable columns
- Active/expired lease highlighting
- Stats bar (total, active, expired)

**Logs features:**
- Selectable tail size (100 / 250 / 500 / 1000 lines)
- Colour-coded ERROR / WARN / INFO / DEBUG badges
- Level and text filter (client-side, instant)
- Auto-refresh every 10 seconds (toggle)

**Reservations features:**
- Browse all static reservations from the `hosts` table
- Search/filter by IP, MAC, hostname, or subnet
- Add a reservation via modal form (validated client- and server-side)
- Delete a reservation with one click

---

## REST API

All endpoints return JSON. Replace `<host>` with your server address (e.g. `localhost:5000`).

---

### Search reservations

```
GET /api/v1/reservations/search
```

Provide exactly one query parameter:

| Parameter  | Description                        | Example             |
|------------|------------------------------------|---------------------|
| `ip`       | IPv4 address of the reservation    | `?ip=192.168.1.100` |
| `mac`      | MAC address (`xx:xx:xx:xx:xx:xx`)  | `?mac=aa:bb:cc:dd:ee:ff` |
| `hostname` | Exact hostname (short or FQDN)     | `?hostname=mydevice` |

**Responses**

| Code | Meaning                              |
|------|--------------------------------------|
| 200  | JSON array of matching reservations  |
| 400  | No query parameter supplied          |
| 404  | No reservation found                 |
| 422  | Invalid IP or MAC format             |

**Example**

```bash
curl "http://<host>/api/v1/reservations/search?ip=192.168.1.100"
curl "http://<host>/api/v1/reservations/search?mac=aa:bb:cc:dd:ee:ff"
curl "http://<host>/api/v1/reservations/search?hostname=mydevice"
```

**Response body (200)**

```json
[
  {
    "host_id": 7,
    "identifier": "aa:bb:cc:dd:ee:ff",
    "identifier_type": "hw-address",
    "dhcp4_subnet_id": 1,
    "ipv4_address": "192.168.1.100",
    "hostname": "mydevice",
    "dhcp4_client_classes": null,
    "dhcp4_next_server": null,
    "dhcp4_server_hostname": null,
    "dhcp4_boot_file_name": null,
    "user_context": null,
    "auth_key": null
  }
]
```

---

### Create a reservation

```
POST /api/v1/reservations
Content-Type: application/json
```

**Request body**

| Field              | Type    | Required | Constraints                          |
|--------------------|---------|----------|--------------------------------------|
| `dhcp_identifier`  | string  | yes      | Valid MAC address (`xx:xx:xx:xx:xx:xx`) |
| `ipv4_address`     | string  | yes      | Valid IPv4 address                   |
| `dhcp4_subnet_id`  | integer | yes      | Non-negative integer                 |
| `hostname`         | string  | yes      | Valid DNS name (short name or FQDN)  |

`dhcp_identifier_type` is always stored as `0` (hw-address).

**Responses**

| Code | Meaning                             |
|------|-------------------------------------|
| 201  | Reservation created; returns new `host_id` |
| 400  | Missing or non-JSON body            |
| 422  | Validation errors (per-field detail)|
| 500  | Database error                      |

**Example**

```bash
curl -X POST "http://<host>/api/v1/reservations" \
  -H "Content-Type: application/json" \
  -d '{
    "dhcp_identifier": "aa:bb:cc:dd:ee:ff",
    "ipv4_address":    "192.168.1.100",
    "dhcp4_subnet_id": 1,
    "hostname":        "mydevice"
  }'
```

**Response body (201)**

```json
{ "host_id": 7, "message": "Reservation created" }
```

**Response body (422)**

```json
{
  "errors": {
    "dhcp_identifier": "Must be a valid MAC address (xx:xx:xx:xx:xx:xx)",
    "ipv4_address": "Must be a valid IPv4 address"
  }
}
```

---

### Delete a reservation

```
DELETE /api/v1/reservations/<host_id>
```

| Path parameter | Type    | Description                   |
|----------------|---------|-------------------------------|
| `host_id`      | integer | `host_id` from the hosts table |

**Responses**

| Code | Meaning                   |
|------|---------------------------|
| 200  | Reservation deleted       |
| 404  | Reservation not found     |
| 500  | Database error            |

**Example**

```bash
curl -X DELETE "http://<host>/api/v1/reservations/7"
```

**Response body (200)**

```json
{ "message": "Reservation deleted" }
```

---

## Production Deployment on Ubuntu Noble

### 1. Clone the repository

```bash
sudo git clone <repo-url> /opt/keadhcp
```

### 2. Create a dedicated system user

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin keadhcp
sudo chown -R keadhcp:keadhcp /opt/keadhcp
```

### 3. Create a virtual environment and install dependencies

```bash
sudo apt install python3-venv python3-pip -y
cd /opt/keadhcp
sudo -u keadhcp python3 -m venv venv
sudo -u keadhcp venv/bin/pip install -r requirements.txt
```

### 4. Create and secure the config file

```bash
sudo mkdir /etc/keadhcp
sudo cp /opt/keadhcp/config.ini.example /etc/keadhcp/config.ini
sudo nano /etc/keadhcp/config.ini      # set real credentials
sudo chown root:keadhcp /etc/keadhcp/config.ini
sudo chmod 640 /etc/keadhcp/config.ini
```

### 5. Create the log directory

```bash
sudo mkdir /var/log/keadhcp
sudo chown keadhcp:keadhcp /var/log/keadhcp
```

### 6. Grant access to Kea logs

The `adm` group typically has read access to `/var/log`:
```bash
sudo usermod -aG adm keadhcp
```

### 7. Install and enable the systemd service

```bash
sudo cp /opt/keadhcp/keadhcp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now keadhcp
```

### 8. Check status and logs

```bash
sudo systemctl status keadhcp
sudo journalctl -u keadhcp -f
```

Gunicorn access and error logs are written to:
- `/var/log/keadhcp/access.log`
- `/var/log/keadhcp/error.log`

### 9. Open the firewall port (if UFW is active)

```bash
sudo ufw allow 5000/tcp
```

The app will be available at `http://<host-ip>:5000` and will restart automatically on boot or failure.

---

## Updating

```bash
cd /opt/keadhcp
sudo git pull
sudo -u keadhcp venv/bin/pip install -r requirements.txt
sudo systemctl restart keadhcp
```
