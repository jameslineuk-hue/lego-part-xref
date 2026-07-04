#!/usr/bin/env bash
# Install lego-part-xref on macOS (Mac Mini or other Mac).
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-$HOME/lego-part-xref}"
INSTALL_SERVICE=0
RUN_MIGRATIONS=1
SOURCE_DIR=""

usage() {
    cat <<'EOF'
Usage: install.sh [OPTIONS]

Install the LEGO Part Cross-Reference API on this Mac.

Options:
  --dir PATH       Install location (default: ~/lego-part-xref)
  --service        Register a launchd user agent to start on login
  --no-migrate     Skip PostgreSQL schema migration
  --source DIR     Source tree (default: parent of install/)
  -h, --help       Show this help

Environment:
  INSTALL_DIR      Same as --dir

Examples:
  ./install/install.sh
  ./install/install.sh --dir /opt/lego-part-xref --service
EOF
}

log() {
    printf '==> %s\n' "$*"
}

die() {
    printf 'error: %s\n' "$*" >&2
    exit 1
}

require_python() {
    if ! command -v python3 >/dev/null 2>&1; then
        die "python3 not found. Install Python 3.10+ (e.g. brew install python@3.12)."
    fi

    local version
    version="$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
    python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' \
        || die "Python 3.10+ required; found $version"
    log "Using Python $version"
}

resolve_source_dir() {
    if [[ -n "$SOURCE_DIR" ]]; then
        [[ -f "$SOURCE_DIR/pyproject.toml" ]] || die "Not a lego-part-xref tree: $SOURCE_DIR"
        return
    fi

    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    SOURCE_DIR="$(cd "$script_dir/.." && pwd)"
    [[ -f "$SOURCE_DIR/pyproject.toml" ]] || die "Could not locate project root from $script_dir"
}

copy_app_files() {
    log "Installing into $INSTALL_DIR"
    mkdir -p "$INSTALL_DIR"

    if [[ "$(cd "$SOURCE_DIR" && pwd)" == "$(cd "$INSTALL_DIR" && pwd)" ]]; then
        log "Source and install directory are the same; skipping file copy"
        return
    fi

    rsync -a --delete \
        --exclude '.git/' \
        --exclude '.venv/' \
        --exclude 'venv/' \
        --exclude '__pycache__/' \
        --exclude '*.py[cod]' \
        --exclude '.env' \
        --exclude 'part_xref/data/' \
        --exclude '.DS_Store' \
        --exclude 'dist/' \
        "$SOURCE_DIR/" "$INSTALL_DIR/"
}

setup_venv() {
    log "Creating virtual environment"
    python3 -m venv "$INSTALL_DIR/.venv"
    # shellcheck disable=SC1091
    source "$INSTALL_DIR/.venv/bin/activate"
    python -m pip install --upgrade pip
    python -m pip install "$INSTALL_DIR"
}

setup_env_file() {
    if [[ -f "$INSTALL_DIR/.env" ]]; then
        log ".env already exists; leaving unchanged"
        return
    fi

    if [[ -f "$INSTALL_DIR/.env.example" ]]; then
        cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
        log "Created .env from .env.example — edit $INSTALL_DIR/.env before production use"
    else
        die "Missing .env.example in $INSTALL_DIR"
    fi
}

setup_data_dir() {
    mkdir -p "$INSTALL_DIR/part_xref/data"
    log "Cache directory ready at $INSTALL_DIR/part_xref/data"
}

run_migrations() {
    if [[ "$RUN_MIGRATIONS" -eq 0 ]]; then
        log "Skipping database migration (--no-migrate)"
        return
    fi

    log "Running database migration (001_add_source_columns)"
    # shellcheck disable=SC1091
    source "$INSTALL_DIR/.venv/bin/activate"
    set -a
    # shellcheck disable=SC1091
    source "$INSTALL_DIR/.env"
    set +a
    if python -m part_xref.migrations.001_add_source_columns; then
        log "Migration complete"
    else
        printf 'warning: migration failed — check PostgreSQL settings in .env\n' >&2
    fi
}

install_launchd_service() {
    local plist_label="com.legohub.part-xref"
    local plist_path="$HOME/Library/LaunchAgents/${plist_label}.plist"
    local template="$INSTALL_DIR/install/com.legohub.part-xref.plist.template"
    local log_dir="$HOME/Library/Logs/lego-part-xref"

    [[ -f "$template" ]] || die "Missing launchd template: $template"

    mkdir -p "$log_dir"
    log "Installing launchd agent at $plist_path"

    sed \
        -e "s|@INSTALL_DIR@|$INSTALL_DIR|g" \
        -e "s|@LOG_DIR@|$log_dir|g" \
        "$template" > "$plist_path"

    launchctl bootout "gui/$(id -u)/$plist_label" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$plist_path"
    launchctl enable "gui/$(id -u)/$plist_label"
    launchctl kickstart -k "gui/$(id -u)/$plist_label"
    log "Service started (logs: $log_dir)"
}

print_done() {
    # shellcheck disable=SC1091
    source "$INSTALL_DIR/.venv/bin/activate"
    set -a
    # shellcheck disable=SC1091
    source "$INSTALL_DIR/.env"
    set +a
    local port="${PART_XREF_PORT:-8035}"

    cat <<EOF

Installation complete.

  Directory:  $INSTALL_DIR
  Web UI:     http://localhost:${port}/
  API docs:   http://localhost:${port}/docs

Run manually:
  cd "$INSTALL_DIR"
  source .venv/bin/activate
  part-xref

EOF

    if [[ "$INSTALL_SERVICE" -eq 0 ]]; then
        cat <<EOF
To auto-start on login, re-run:
  INSTALL_DIR="$INSTALL_DIR" $INSTALL_DIR/install/install.sh --service

EOF
    fi
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dir)
            [[ $# -ge 2 ]] || die "--dir requires a path"
            INSTALL_DIR="$2"
            shift 2
            ;;
        --service)
            INSTALL_SERVICE=1
            shift
            ;;
        --no-migrate)
            RUN_MIGRATIONS=0
            shift
            ;;
        --source)
            [[ $# -ge 2 ]] || die "--source requires a path"
            SOURCE_DIR="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "Unknown option: $1 (try --help)"
            ;;
    esac
done

require_python
resolve_source_dir
copy_app_files
setup_venv
setup_env_file
setup_data_dir
run_migrations

if [[ "$INSTALL_SERVICE" -eq 1 ]]; then
    install_launchd_service
fi

print_done
