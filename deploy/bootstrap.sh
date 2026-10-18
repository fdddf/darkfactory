#!/usr/bin/env bash
# Bring up Dark Factory on a fresh Nebius AI Cloud VM (Ubuntu 22.04/24.04).
#
#   ssh ubuntu@<vm-ip>
#   git clone <this repo> darkfactory && cd darkfactory
#   sudo bash deploy/bootstrap.sh
#
# Installs what the line needs, builds the frontend, seeds bugs from real
# WordPress history, and runs the platform behind systemd on port 80.
set -euo pipefail

APP_USER="${APP_USER:-ubuntu}"
APP_DIR="${APP_DIR:-/opt/darkfactory}"
PORT="${PORT:-8800}"
REPO_URL="${REPO_URL:-https://github.com/WordPress/wordpress-develop.git}"

say() { printf '\n\033[32m==>\033[0m %s\n' "$1"; }

say "system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
  git curl ca-certificates \
  python3 python3-venv python3-pip \
  php-cli php-mysql php-xml php-mbstring php-curl php-zip php-gd \
  mariadb-server composer nginx

say "node 22"
if ! command -v node >/dev/null; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
  apt-get install -y -qq nodejs
fi

say "application at $APP_DIR"
mkdir -p "$APP_DIR"
if [ "$(realpath "$PWD")" != "$(realpath "$APP_DIR")" ]; then
  cp -r . "$APP_DIR"
fi
cd "$APP_DIR"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

say "python environment"
sudo -u "$APP_USER" python3 -m venv .venv
sudo -u "$APP_USER" .venv/bin/pip install -q --upgrade pip
sudo -u "$APP_USER" .venv/bin/pip install -q -r requirements.txt

say "frontend build"
sudo -u "$APP_USER" bash -c 'cd web && npm ci --no-fund --no-audit && npm run build'

say "test database"
systemctl enable --now mariadb
mariadb <<'SQL'
CREATE DATABASE IF NOT EXISTS wordpress_tests DEFAULT CHARACTER SET utf8mb4;
CREATE USER IF NOT EXISTS 'wptests'@'localhost' IDENTIFIED BY 'wptests';
GRANT ALL PRIVILEGES ON wordpress_tests.* TO 'wptests'@'localhost';
FLUSH PRIVILEGES;
SQL

say "seed repository"
if [ ! -d wp ]; then
  sudo -u "$APP_USER" git clone --depth 900 "$REPO_URL" wp
fi
sudo -u "$APP_USER" bash -c 'cd wp && composer install --no-interaction --quiet'
sudo -u "$APP_USER" bash -c 'cd wp && sed -e "s/youremptytestdbnamehere/wordpress_tests/" \
  -e "s/yourusernamehere/wptests/" -e "s/yourpasswordhere/wptests/" \
  wp-tests-config-sample.php > wp-tests-config.php'

say "seed bugs from real WordPress history"
sudo -u "$APP_USER" .venv/bin/python -m darkfactory.cli seed --repo wp --count 3 || true

say "service"
install -m 644 deploy/darkfactory.service /etc/systemd/system/darkfactory.service
sed -i "s#__APP_DIR__#$APP_DIR#g; s#__APP_USER__#$APP_USER#g; s#__PORT__#$PORT#g" \
  /etc/systemd/system/darkfactory.service
systemctl daemon-reload
systemctl enable --now darkfactory

say "nginx"
install -m 644 deploy/nginx.conf /etc/nginx/sites-available/darkfactory
sed -i "s#__PORT__#$PORT#g" /etc/nginx/sites-available/darkfactory
ln -sf /etc/nginx/sites-available/darkfactory /etc/nginx/sites-enabled/darkfactory
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

say "up on http://$(curl -s --max-time 4 ifconfig.me || echo '<vm-ip>')/"
echo "  secrets:   set them in the Integrations page, or put them in $APP_DIR/.env"
echo "  logs:      journalctl -u darkfactory -f"
