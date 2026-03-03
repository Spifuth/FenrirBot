#!/bin/bash
# Fenrir Bot - File Watcher for Hot Reload
# Watches for changes in Python files and restarts the bot

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVICE_NAME="fenrir.service"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

# Check if inotifywait is available
if ! command -v inotifywait &> /dev/null; then
    echo -e "${RED}❌ inotifywait not found. Install inotify-tools:${NC}"
    echo "   sudo apt install inotify-tools"
    exit 1
fi

log "${GREEN}🐺 Fenrir Watcher started${NC}"
log "Watching: ${PROJECT_DIR}/src and ${PROJECT_DIR}/run.py"
log "Service: ${SERVICE_NAME}"
echo ""

cd "$PROJECT_DIR"

# Debounce: wait a bit after changes to batch multiple saves
DEBOUNCE_SECONDS=2
last_restart=0

while true; do
    # Watch for changes in .py files
    changed_file=$(inotifywait -r -e modify,create,delete,move \
        --format '%w%f' \
        --include '.*\.py$' \
        --timeout -1 \
        "$PROJECT_DIR/src" \
        "$PROJECT_DIR/run.py" \
        2>/dev/null)
    
    if [ -n "$changed_file" ]; then
        current_time=$(date +%s)
        time_since_last=$((current_time - last_restart))
        
        # Debounce: skip if we just restarted
        if [ $time_since_last -lt $DEBOUNCE_SECONDS ]; then
            log "${YELLOW}⏳ Debouncing... (${time_since_last}s since last restart)${NC}"
            continue
        fi
        
        log "${YELLOW}📝 Change detected: ${changed_file}${NC}"
        log "${GREEN}🔄 Restarting ${SERVICE_NAME}...${NC}"
        
        # Restart the service
        if systemctl is-active --quiet "$SERVICE_NAME"; then
            sudo systemctl restart "$SERVICE_NAME"
            
            # Wait and check status
            sleep 2
            if systemctl is-active --quiet "$SERVICE_NAME"; then
                log "${GREEN}✅ ${SERVICE_NAME} restarted successfully${NC}"
            else
                log "${RED}❌ ${SERVICE_NAME} failed to start!${NC}"
                log "Check logs: journalctl -u ${SERVICE_NAME} -n 20"
            fi
        else
            log "${RED}⚠️ ${SERVICE_NAME} is not running${NC}"
        fi
        
        last_restart=$(date +%s)
        echo ""
    fi
done
