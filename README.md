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
