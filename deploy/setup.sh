#!/usr/bin/env bash
# Provision TrackFolio on a fresh Oracle Linux 10 host (aarch64 or x86_64).
#
# Run as root from a checkout of this repository:
#   sudo TRACKFOLIO_DOMAIN=trackfolio.example.com TRACKFOLIO_ACME_EMAIL=you@example.com \
#     bash deploy/setup.sh
#
# Everything runs rootless as the dedicated user "trackfolio" (Podman Quadlets: PostgreSQL,
# the app, Caddy, and a systemd timer for the price refresh). Idempotent: re-run it to
# deploy new code (rebuilds the image and restarts the app); existing secrets are kept.
set -euo pipefail

: "${TRACKFOLIO_DOMAIN:?set TRACKFOLIO_DOMAIN (e.g. trackfolio.example.com)}"
: "${TRACKFOLIO_ACME_EMAIL:?set TRACKFOLIO_ACME_EMAIL (contact address for the TLS certificate)}"
[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }
[[ $TRACKFOLIO_DOMAIN =~ ^[A-Za-z0-9.-]+$ ]] || { echo "invalid TRACKFOLIO_DOMAIN" >&2; exit 1; }
[[ $TRACKFOLIO_ACME_EMAIL =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+$ ]] || { echo "invalid email" >&2; exit 1; }

SERVICE_USER=trackfolio
REPO_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DEPLOY_DIR=$REPO_DIR/deploy

log() { printf '==> %s\n' "$*"; }

# --- packages ---------------------------------------------------------------------------------
log "Installing packages"
dnf install -y podman openssl tar >/dev/null

# --- firewall (the cloud network security list must also allow 80/443) --------------------------
if systemctl is-active --quiet firewalld; then
    log "Opening HTTP, HTTPS and HTTP/3 in firewalld"
    firewall-cmd --permanent --add-service=http --add-service=https --add-port=443/udp >/dev/null
    firewall-cmd --reload >/dev/null
else
    echo "WARNING: firewalld is not running; make sure ports 80/443 (tcp) and 443 (udp) are open" >&2
fi

# --- rootless users may bind 80/443 --------------------------------------------------------------
log "Allowing unprivileged processes to bind ports >= 80"
echo "net.ipv4.ip_unprivileged_port_start=80" >/etc/sysctl.d/99-trackfolio-ports.conf
sysctl -w net.ipv4.ip_unprivileged_port_start=80 >/dev/null

# --- service user -------------------------------------------------------------------------------
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
    log "Creating user $SERVICE_USER"
    useradd --create-home --shell /sbin/nologin "$SERVICE_USER"
fi
grep -q "^$SERVICE_USER:" /etc/subuid || usermod --add-subuids 100000-165535 "$SERVICE_USER"
grep -q "^$SERVICE_USER:" /etc/subgid || usermod --add-subgids 100000-165535 "$SERVICE_USER"
loginctl enable-linger "$SERVICE_USER"

USER_ID=$(id -u "$SERVICE_USER")
HOME_DIR=$(getent passwd "$SERVICE_USER" | cut -d: -f6)
: "${HOME_DIR:?home directory of the service user not found}"
APP_DIR=$HOME_DIR/trackfolio
SRC_DIR=$HOME_DIR/build-src
QUADLET_DIR=$HOME_DIR/.config/containers/systemd
UNIT_DIR=$HOME_DIR/.config/systemd/user

systemctl start "user@$USER_ID.service"
for _ in $(seq 1 30); do
    [[ -S /run/user/$USER_ID/bus ]] && break
    sleep 1
done
[[ -S /run/user/$USER_ID/bus ]] || { echo "user systemd manager did not start" >&2; exit 1; }

# Run a command as the service user from its home (root's working directory is unreadable).
as_user() {
    runuser -u "$SERVICE_USER" -- env \
        XDG_RUNTIME_DIR="/run/user/$USER_ID" \
        DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$USER_ID/bus" \
        bash -c 'cd "$1" && shift && exec "$@"' _ "$HOME_DIR" "$@"
}

# --- configuration and secrets (never overwritten once created) ----------------------------------
log "Writing configuration in $APP_DIR"
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 700 "$APP_DIR" "$QUADLET_DIR" "$UNIT_DIR"
install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 644 "$DEPLOY_DIR/Caddyfile" "$APP_DIR/Caddyfile"

if [[ -f $APP_DIR/db.env && ! -f $APP_DIR/app.env ]] \
    || [[ ! -f $APP_DIR/db.env && -f $APP_DIR/app.env ]]; then
    echo "only one of db.env and app.env exists in $APP_DIR: restore both from a backup, or" >&2
    echo "remove both AND the trackfolio-db volume to start over (a new password would not" >&2
    echo "match the existing database)" >&2
    exit 1
fi
if [[ ! -f $APP_DIR/db.env ]]; then
    log "Generating the database password (stored only in $APP_DIR, mode 600)"
    db_password=$(openssl rand -hex 24)
    (
        umask 077
        printf 'POSTGRES_USER=trackfolio\nPOSTGRES_DB=trackfolio\nPOSTGRES_PASSWORD=%s\n' \
            "$db_password" >"$APP_DIR/db.env"
        printf 'TRACKFOLIO_DATABASE_URL=postgresql+psycopg://trackfolio:%s@trackfolio-db:5432/trackfolio\nTRACKFOLIO_SECURE_COOKIES=true\n' \
            "$db_password" >"$APP_DIR/app.env"
    )
    unset db_password
fi
(
    umask 077
    printf 'TRACKFOLIO_DOMAIN=%s\nTRACKFOLIO_ACME_EMAIL=%s\n' \
        "$TRACKFOLIO_DOMAIN" "$TRACKFOLIO_ACME_EMAIL" >"$APP_DIR/caddy.env"
)
chown "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"/*.env
chmod 600 "$APP_DIR"/*.env

# --- units -------------------------------------------------------------------------------------
log "Installing Quadlets and the refresh timer"
db_changed=0
cmp -s "$DEPLOY_DIR/quadlet/trackfolio-db.container" "$QUADLET_DIR/trackfolio-db.container" \
    || db_changed=1
install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 644 "$DEPLOY_DIR"/quadlet/* "$QUADLET_DIR"/
install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 644 "$DEPLOY_DIR/systemd/trackfolio-refresh.timer" "$UNIT_DIR"/

# --- image -------------------------------------------------------------------------------------
log "Building the application image"
rm -rf "${SRC_DIR:?}"
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" "$SRC_DIR"
tar -C "$REPO_DIR" --exclude=.git --exclude=.venv --exclude=data --exclude=.cache -cf - . \
    | tar -C "$SRC_DIR" -xf -
chown -R "$SERVICE_USER:$SERVICE_USER" "$SRC_DIR"
as_user podman build -t localhost/trackfolio:latest -f "$SRC_DIR/Containerfile" "$SRC_DIR"

# --- start --------------------------------------------------------------------------------------
log "Starting services"
as_user systemctl --user daemon-reload
as_user systemctl --user start trackfolio-db.service
if [[ $db_changed -eq 1 ]]; then
    as_user systemctl --user restart trackfolio-db.service
fi
# App and proxy are restarted on every run: new image, possibly a new Caddyfile.
as_user systemctl --user restart trackfolio-app.service trackfolio-caddy.service
as_user systemctl --user enable --now trackfolio-refresh.timer

log "Waiting for the application to become healthy"
for _ in $(seq 1 60); do
    if as_user podman healthcheck run trackfolio-app >/dev/null 2>&1; then
        healthy=1
        break
    fi
    sleep 2
done
[[ ${healthy:-0} -eq 1 ]] || { echo "the app is not healthy: check 'journalctl' for the user $SERVICE_USER" >&2; exit 1; }

cat <<EOF

TrackFolio is running behind https://$TRACKFOLIO_DOMAIN

Next steps:
  1. DNS: point an A record for $TRACKFOLIO_DOMAIN to this host's public IP, and allow
     ports 80 and 443 (tcp) and 443 (udp) in the cloud network security list.
  2. Create the first administrator (prompts for a password):
       sudo -u $SERVICE_USER env -C $HOME_DIR XDG_RUNTIME_DIR=/run/user/$USER_ID \\
         podman exec -it trackfolio-app trackfolio create-user you@example.com --admin
  3. After adding transactions, fetch prices once without waiting for the timer:
       sudo -u $SERVICE_USER env -C $HOME_DIR XDG_RUNTIME_DIR=/run/user/$USER_ID \\
         systemctl --user start trackfolio-refresh.service
EOF
