#!/usr/bin/env bash
# Build fenrirbot:latest Docker image locally.
# Run this after code changes, then restart via the nebula stack.
#
# Usage:
#   ./build.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "▶ Building fenrirbot:latest ..."
docker build -t fenrirbot:latest .
echo "✓ fenrirbot:latest built"

echo ""
echo "Done. To deploy:"
echo "  cd /srv/nebula && ./scripts/start-docker.sh up management"
