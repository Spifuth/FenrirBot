#!/bin/bash
# Fenrir Bot - Service Installation Script
# Installs and configures systemd services

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}[Fenrir]${NC} $1"; }
success() { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
error() { echo -e "${RED}❌ $1${NC}"; }

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    error "Don't run this script as root. It will use sudo when needed."
    exit 1
fi

echo ""
echo -e "${GREEN}🐺 Fenrir Bot - Service Installer${NC}"
echo "=================================="
echo ""

# Get current user
CURRENT_USER=$(whoami)
log "Installing for user: ${CURRENT_USER}"
log "Project directory: ${PROJECT_DIR}"
echo ""

# Check prerequisites
log "Checking prerequisites..."

if [ ! -f "${PROJECT_DIR}/venv/bin/python" ]; then
    error "Virtual environment not found. Run setup.sh first."
    exit 1
fi
success "Virtual environment found"

if [ ! -f "${PROJECT_DIR}/.env" ]; then
    error ".env file not found. Create it from .env.example"
    exit 1
fi
success ".env file found"

# Check for inotify-tools
if ! command -v inotifywait &> /dev/null; then
    warn "inotify-tools not installed (needed for hot reload)"
    read -p "Install inotify-tools? [Y/n] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
        sudo apt update && sudo apt install -y inotify-tools
        success "inotify-tools installed"
    fi
fi

echo ""
log "Creating service files..."

# Create fenrir.service with correct paths and user
FENRIR_SERVICE="/etc/systemd/system/fenrir.service"
sudo tee "$FENRIR_SERVICE" > /dev/null << EOF
[Unit]
Description=Fenrir Discord Bot
Documentation=https://github.com/your-repo/FenrirBot
After=network-online.target docker.service
Wants=network-online.target
Requires=docker.service

[Service]
Type=simple
User=${CURRENT_USER}
Group=${CURRENT_USER}
WorkingDirectory=${PROJECT_DIR}

# Environment
Environment=PATH=${PROJECT_DIR}/venv/bin:/usr/local/bin:/usr/bin:/bin
EnvironmentFile=${PROJECT_DIR}/.env

# Start command
ExecStart=${PROJECT_DIR}/venv/bin/python run.py

# Restart policy
Restart=always
RestartSec=10

# Stop gracefully
TimeoutStopSec=30
KillMode=mixed

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=fenrir-bot

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=${PROJECT_DIR}/data

[Install]
WantedBy=multi-user.target
EOF
success "Created ${FENRIR_SERVICE}"

# Create fenrir-watcher.service
WATCHER_SERVICE="/etc/systemd/system/fenrir-watcher.service"
sudo tee "$WATCHER_SERVICE" > /dev/null << EOF
[Unit]
Description=Fenrir Bot File Watcher (Hot Reload)
Documentation=https://github.com/your-repo/FenrirBot
After=fenrir.service
BindsTo=fenrir.service
PartOf=fenrir.service

[Service]
Type=simple
User=${CURRENT_USER}
Group=${CURRENT_USER}
WorkingDirectory=${PROJECT_DIR}

ExecStart=${PROJECT_DIR}/scripts/watch.sh

Restart=always
RestartSec=5

StandardOutput=journal
StandardError=journal
SyslogIdentifier=fenrir-watcher

[Install]
WantedBy=multi-user.target
EOF
success "Created ${WATCHER_SERVICE}"

# Make watch.sh executable
chmod +x "${PROJECT_DIR}/scripts/watch.sh"
success "Made watch.sh executable"

# Allow user to restart fenrir.service without password (for watcher)
SUDOERS_FILE="/etc/sudoers.d/fenrir-bot"
sudo tee "$SUDOERS_FILE" > /dev/null << EOF
# Allow ${CURRENT_USER} to restart fenrir bot without password
${CURRENT_USER} ALL=(ALL) NOPASSWD: /bin/systemctl restart fenrir.service
${CURRENT_USER} ALL=(ALL) NOPASSWD: /bin/systemctl start fenrir.service
${CURRENT_USER} ALL=(ALL) NOPASSWD: /bin/systemctl stop fenrir.service
${CURRENT_USER} ALL=(ALL) NOPASSWD: /bin/systemctl status fenrir.service
EOF
sudo chmod 440 "$SUDOERS_FILE"
success "Created sudoers rules for password-less restart"

# Reload systemd
log "Reloading systemd..."
sudo systemctl daemon-reload
success "Systemd reloaded"

echo ""
echo -e "${GREEN}✅ Installation complete!${NC}"
echo ""
echo "Commands:"
echo "  ${BLUE}sudo systemctl start fenrir${NC}          - Start the bot"
echo "  ${BLUE}sudo systemctl stop fenrir${NC}           - Stop the bot"
echo "  ${BLUE}sudo systemctl restart fenrir${NC}        - Restart the bot"
echo "  ${BLUE}sudo systemctl status fenrir${NC}         - Check status"
echo "  ${BLUE}sudo systemctl enable fenrir${NC}         - Start on boot"
echo ""
echo "  ${BLUE}sudo systemctl start fenrir-watcher${NC}  - Start hot reload watcher"
echo "  ${BLUE}sudo systemctl enable fenrir-watcher${NC} - Enable hot reload on boot"
echo ""
echo "Logs:"
echo "  ${BLUE}journalctl -u fenrir -f${NC}              - Follow bot logs"
echo "  ${BLUE}journalctl -u fenrir-watcher -f${NC}      - Follow watcher logs"
echo ""

read -p "Start Fenrir now? [Y/n] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
    sudo systemctl start fenrir
    sleep 2
    if systemctl is-active --quiet fenrir; then
        success "Fenrir is running!"
        echo ""
        read -p "Enable hot reload watcher? [Y/n] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
            sudo systemctl start fenrir-watcher
            success "Hot reload watcher started!"
        fi
    else
        error "Fenrir failed to start. Check logs:"
        echo "  journalctl -u fenrir -n 30"
    fi
fi

echo ""
echo -e "${GREEN}🐺 Fenrir is ready!${NC}"
