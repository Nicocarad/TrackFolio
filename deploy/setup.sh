#!/usr/bin/env bash
# Provision TrackFolio on a fresh Oracle Linux 10 host (aarch64 or x86_64)
#
# Run as root from a checkout of this repository:
#   sudo TRACKFOLIO_DOMAIN=trackfolio.example.com bash deploy/setup.sh
#
# Without TRACKFOLIO_DOMAIN the site is served over plain HTTP on port 80 (no certificate, cookies not marked Secure): enough to test, not to use. Re-run with the domain once DNS points at this host.
# Everything runs rootless as the dedicated user "trackfolio" (Podman Quadlets: PostgreSQL, the app, Caddy, and a systemd timer for the price refresh). Idempotent: re-run it to deploy new code (rebuilds the image and restarts the app); existing secrets are kept.
set -euo pipefail

TRACKFOLIO_DOMAIN=${TRACKFOLIO_DOMAIN:-}
[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }
[[ -z $TRACKFOLIO_DOMAIN || $TRACKFOLIO_DOMAIN =~ ^[A-Za-z0-9.-]+$ ]] \
    || { echo "invalid TRACKFOLIO_DOMAIN" >&2; exit 1; }

SERVICE_USER=trackfolio
REPO_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DEPLOY_DIR=$REPO_DIR/deploy

log() { printf '==> %s\n' "$*"; }

# --- packages ---------------------------------------------------------------------------------
log "Installing packages"
dnf install -y podman openssl tar >/dev/null

# --- firewall: rootless Caddy listens on 8080/8443, firewalld forwards 80/443 to it ------------
if systemctl is-active --quiet firewalld; then
    log "Opening and forwarding HTTP, HTTPS and HTTP/3 in firewalld"
    zone=(--permanent --zone=public)
    firewall-cmd "${zone[@]}" --add-service=http --add-service=https >/dev/null
    firewall-cmd "${zone[@]}" --add-port=443/udp >/dev/null
    for rule in 80:tcp:8080 443:tcp:8443 443:udp:8443; do
        IFS=: read -r port proto target <<<"$rule"
        firewall-cmd "${zone[@]}" \
            --add-forward-port="port=$port:proto=$proto:toport=$target" >/dev/null
    done
    firewall-cmd --reload >/dev/null
else
    echo "WARNING: firewalld is not running; forward 80/443 to 8080/8443 yourself" >&2
fi

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

as_user() {
    runuser -u "$SERVICE_USER" -- env \
        XDG_RUNTIME_DIR="/run/user/$USER_ID" \
        DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$USER_ID/bus" \
        bash -c 'cd "$1" && shift && exec "$@"' _ "$HOME_DIR" "$@"
}

# --- configuration and secrets (database password never overwritten once created) -----------------
log "Writing configuration in $APP_DIR"
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 700 "$APP_DIR"
# Parents of these directories must belong to the service user, not root.
as_user mkdir -p "$QUADLET_DIR" "$UNIT_DIR"
chown -R "$SERVICE_USER:$SERVICE_USER" "$HOME_DIR/.config"
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 755 "$APP_DIR/caddy"
caddyfile=Caddyfile
[[ -n $TRACKFOLIO_DOMAIN ]] || caddyfile=Caddyfile.http
install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 644 "$DEPLOY_DIR/caddy/$caddyfile" "$APP_DIR/caddy/Caddyfile"
install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 644 "$DEPLOY_DIR/caddy/site.conf" "$APP_DIR/caddy/site.conf"

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
        printf 'TRACKFOLIO_DATABASE_URL=postgresql+psycopg://trackfolio:%s@trackfolio-db:5432/trackfolio\n' \
            "$db_password" >"$APP_DIR/app.env"
    )
    unset db_password
fi
(
    umask 077
    if [[ -n $TRACKFOLIO_DOMAIN ]]; then
        printf 'TRACKFOLIO_SECURE_COOKIES=true\n' >"$APP_DIR/web.env"
        printf 'TRACKFOLIO_SITE=%s\n' "$TRACKFOLIO_DOMAIN" >"$APP_DIR/caddy.env"
    else
        printf 'TRACKFOLIO_SECURE_COOKIES=false\n' >"$APP_DIR/web.env"
        : >"$APP_DIR/caddy.env"
    fi
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
# An interrupted earlier build leaves buildah working containers that keep images in use.
as_user bash -c "podman ps -a --external --format '{{.Names}}' | grep -- '-working-container\$' | xargs -r podman rm -f >/dev/null || true"
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
as_user systemctl --user restart trackfolio-app.service trackfolio-caddy.service
as_user podman image prune -f >/dev/null || true
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

if [[ -n $TRACKFOLIO_DOMAIN ]]; then
    where="https://$TRACKFOLIO_DOMAIN"
    dns="  1. DNS: point an A record for $TRACKFOLIO_DOMAIN to this host's public IP, and allow
     ports 80 and 443 (tcp) and 443 (udp) in the cloud network security list."
else
    where="http://<this host's IP> (plain HTTP, no domain configured)"
    dns="  1. No domain yet: re-run with TRACKFOLIO_DOMAIN=your.domain once DNS points here,
     and allow ports 80 and 443 (tcp) and 443 (udp) in the cloud network security list."
fi
cat <<EOF

TrackFolio is running at $where

Next steps:
$dns
  2. Create the first administrator (prompts for a password):
       sudo -u $SERVICE_USER env -C $HOME_DIR XDG_RUNTIME_DIR=/run/user/$USER_ID \\
         podman exec -it trackfolio-app trackfolio create-user you@example.com --admin
  3. After adding transactions, fetch prices once without waiting for the timer:
       sudo -u $SERVICE_USER env -C $HOME_DIR XDG_RUNTIME_DIR=/run/user/$USER_ID \\
         systemctl --user start trackfolio-refresh.service
EOF
