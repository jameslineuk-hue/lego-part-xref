#!/usr/bin/env bash
# Remove lego-part-xref launchd service and optionally delete the install directory.
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-$HOME/lego-part-xref}"
REMOVE_FILES=0
PLIST_LABEL="com.legohub.part-xref"

usage() {
    cat <<'EOF'
Usage: uninstall.sh [OPTIONS]

Stop the launchd service and optionally remove the install directory.

Options:
  --dir PATH       Install location (default: ~/lego-part-xref)
  --remove-files   Delete the install directory after stopping the service
  -h, --help       Show this help
EOF
}

log() {
    printf '==> %s\n' "$*"
}

die() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dir)
            [[ $# -ge 2 ]] || die "--dir requires a path"
            INSTALL_DIR="$2"
            shift 2
            ;;
        --remove-files)
            REMOVE_FILES=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "Unknown option: $1"
            ;;
    esac
done

plist_path="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
if [[ -f "$plist_path" ]]; then
    log "Stopping launchd agent"
    launchctl bootout "gui/$(id -u)/$PLIST_LABEL" 2>/dev/null || true
    rm -f "$plist_path"
else
    log "No launchd agent found at $plist_path"
fi

if [[ "$REMOVE_FILES" -eq 1 ]]; then
    if [[ -d "$INSTALL_DIR" ]]; then
        log "Removing $INSTALL_DIR"
        rm -rf "$INSTALL_DIR"
    else
        log "Install directory not found: $INSTALL_DIR"
    fi
fi

log "Done"
