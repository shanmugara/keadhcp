#!/usr/bin/env bash
#
# install.sh — install keadhcp under /opt/keadhcp and register the systemd
# service (listens on port 80).
#
# Run as root from a checkout of this repository:
#   sudo ./install.sh
set -euo pipefail

INSTALL_DIR=/opt/keadhcp
SERVICE_USER=keadhcp
SERVICE_GROUP=keadhcp
CONFIG_DIR=/etc/keadhcp
LOG_DIR=/var/log/keadhcp
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root (sudo ./install.sh)" >&2
  exit 1
fi

echo "==> Creating service user ${SERVICE_USER}"
if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi

echo "==> Installing application files to ${INSTALL_DIR}"
mkdir -p "$INSTALL_DIR"
rsync -a --delete \
  --exclude '.git' \
  --exclude 'venv' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude 'config.ini' \
  "$SOURCE_DIR"/ "$INSTALL_DIR"/
chown -R "$SERVICE_USER":"$SERVICE_GROUP" "$INSTALL_DIR"

echo "==> Creating virtual environment"
sudo -u "$SERVICE_USER" python3 -m venv "$INSTALL_DIR/venv"
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install --upgrade pip
sudo -u "$SERVICE_USER" "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

echo "==> Setting up config"
mkdir -p "$CONFIG_DIR"
if [[ ! -f "$CONFIG_DIR/config.ini" ]]; then
  cp "$SOURCE_DIR/config.ini.example" "$CONFIG_DIR/config.ini"
  echo "    Wrote ${CONFIG_DIR}/config.ini from template — edit it with real [mysql]/[ddns] credentials."
else
  echo "    ${CONFIG_DIR}/config.ini already exists, leaving it untouched."
fi
chown root:"$SERVICE_GROUP" "$CONFIG_DIR/config.ini"
chmod 640 "$CONFIG_DIR/config.ini"

echo "==> Creating log directory"
mkdir -p "$LOG_DIR"
chown "$SERVICE_USER":"$SERVICE_GROUP" "$LOG_DIR"

echo "==> Granting access to Kea logs (adm group)"
usermod -aG adm "$SERVICE_USER" || true

echo "==> Installing systemd unit (port 80)"
cp "$SOURCE_DIR/keadhcp.service" /etc/systemd/system/keadhcp.service
systemctl daemon-reload
systemctl enable --now keadhcp

if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "^Status: active"; then
  echo "==> Opening firewall port 80/tcp"
  ufw allow 80/tcp
fi

echo "==> Done. Check status with: systemctl status keadhcp"
echo "    Edit ${CONFIG_DIR}/config.ini then: sudo systemctl restart keadhcp"
