#!/usr/bin/env bash
# Build a distributable tarball for installing on another Mac.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$ROOT/dist"
STAGING="$DIST_DIR/staging"

version() {
    if [[ -f "$ROOT/pyproject.toml" ]]; then
        sed -n 's/^version = "\(.*\)"/\1/p' "$ROOT/pyproject.toml" | head -1
    fi
}

VERSION="${VERSION:-$(version)}"
VERSION="${VERSION:-1.0.0}"
ARCHIVE_NAME="lego-part-xref-${VERSION}"
ARCHIVE_PATH="$DIST_DIR/${ARCHIVE_NAME}.tar.gz"

log() {
    printf '==> %s\n' "$*"
}

mkdir -p "$STAGING/$ARCHIVE_NAME"

log "Staging $ARCHIVE_NAME"
rsync -a \
    --exclude '.git/' \
    --exclude '.venv/' \
    --exclude 'venv/' \
    --exclude '__pycache__/' \
    --exclude '*.py[cod]' \
    --exclude '.env' \
    --exclude 'part_xref/data/' \
    --exclude '.DS_Store' \
    --exclude 'dist/' \
    "$ROOT/" "$STAGING/$ARCHIVE_NAME/"

chmod +x "$STAGING/$ARCHIVE_NAME/install/install.sh"
chmod +x "$STAGING/$ARCHIVE_NAME/install/uninstall.sh"
chmod +x "$STAGING/$ARCHIVE_NAME/scripts/build-package.sh"

log "Creating $ARCHIVE_PATH"
tar -czf "$ARCHIVE_PATH" -C "$STAGING" "$ARCHIVE_NAME"
rm -rf "$STAGING"

BYTES="$(wc -c < "$ARCHIVE_PATH" | tr -d ' ')"
log "Package ready: $ARCHIVE_PATH ($BYTES bytes)"
cat <<EOF

Transfer to your Mac Mini, then:

  scp dist/${ARCHIVE_NAME}.tar.gz mini:~/
  ssh mini
  tar -xzf ${ARCHIVE_NAME}.tar.gz
  cd ${ARCHIVE_NAME}
  ./install/install.sh --service

EOF
