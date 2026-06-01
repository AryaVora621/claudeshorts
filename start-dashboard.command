#!/usr/bin/env bash
# macOS double-click launcher. Finder runs this in Terminal; it just hands off
# to start-dashboard.sh in the same folder.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$DIR/start-dashboard.sh"
