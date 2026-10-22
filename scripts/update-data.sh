#!/usr/bin/env bash
# Replace this instance's data with a published data release (see README, "Data releases").
#
#   scripts/update-data.sh                  # latest release, asks before stopping the map
#   scripts/update-data.sh --tag data-2026-10-22.2
#   scripts/update-data.sh --file path/to/precinctmap-data.tar.gz
#   scripts/update-data.sh --dry-run        # download, verify and describe only; change nothing
#   scripts/update-data.sh --yes            # no confirmation prompt (for cron or CI)
#
# Steps: download the release (gh, or curl for a public repo) into data/releases/<tag>/, check
# its sha256, show what it contains, build the image for the checked-out code, then stop the
# app, move the current store to data/backups/, load the bundle into an empty store and start
# the app again. If anything fails after the stop, the previous store is put back and the app
# restarted. Backups are never deleted by this script.
#
# The map is down from the stop until the app reports healthy (about a minute). Admin uploads
# made on this instance that are not in the release are replaced along with everything else.

set -euo pipefail

cd "$(dirname "$0")/.."

ARCHIVE_NAME="precinctmap-data.tar.gz"
SERVICE="precinctmap"
STORE="data/precinctmap.duckdb"
TAG="" FILE="" DRY_RUN=0 ASSUME_YES=0
REPO="${PRECINCTMAP_RELEASE_REPO:-}"

usage() { sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }
say() { printf '\033[1m==> %s\033[0m\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --tag) TAG="${2:?--tag needs a value}"; shift 2 ;;
    --file) FILE="${2:?--file needs a path}"; shift 2 ;;
    --repo) REPO="${2:?--repo needs owner/name}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --yes|-y) ASSUME_YES=1; shift ;;
    -h|--help) usage 0 ;;
    *) printf 'unknown option: %s\n\n' "$1" >&2; usage 1 ;;
  esac
done

command -v docker >/dev/null || die "docker is not installed"
command -v sha256sum >/dev/null || die "sha256sum is not installed"

repo_from_git() {  # owner/name of the origin remote, or nothing (never fails)
  { git remote get-url origin 2>/dev/null || true; } | sed -E 's#(git@github\.com:|https://github\.com/)##; s#\.git$##'
}

download() {
  local dir="$1"
  [ -n "$REPO" ] || REPO="$(repo_from_git)"
  [ -n "$REPO" ] || die "can't tell which GitHub repo to use; pass --repo owner/name"
  mkdir -p "$dir"
  if command -v gh >/dev/null; then
    gh release download ${TAG:+"$TAG"} --repo "$REPO" --pattern "${ARCHIVE_NAME}*" --dir "$dir" --clobber
  else
    local base="https://github.com/$REPO/releases"
    local url="$base/latest/download"
    [ -n "$TAG" ] && url="$base/download/$TAG"
    curl -fL --retry 3 -o "$dir/$ARCHIVE_NAME" "$url/$ARCHIVE_NAME"
    curl -fL --retry 3 -o "$dir/$ARCHIVE_NAME.sha256" "$url/$ARCHIVE_NAME.sha256"
  fi
}

# --- 1. Get and verify the archive (nothing is changed yet) --------------------------------
if [ -n "$FILE" ]; then
  [ -f "$FILE" ] || die "$FILE does not exist"
  case "$(realpath "$FILE")" in
    "$(realpath data)"/*) ARCHIVE="$FILE" ;;
    *) mkdir -p data/releases/local && cp "$FILE" data/releases/local/ && ARCHIVE="data/releases/local/$(basename "$FILE")" ;;
  esac
  [ -f "$FILE.sha256" ] && cp "$FILE.sha256" "$ARCHIVE.sha256" 2>/dev/null || true
else
  DIR="data/releases/${TAG:-latest}"
  say "Downloading ${TAG:-the latest release} from ${REPO:-$(repo_from_git)}"
  download "$DIR"
  ARCHIVE="$DIR/$ARCHIVE_NAME"
fi

if [ -f "$ARCHIVE.sha256" ]; then
  say "Checking the sha256"
  (cd "$(dirname "$ARCHIVE")" && sed "s#  .*#  $(basename "$ARCHIVE")#" "$(basename "$ARCHIVE").sha256" | sha256sum -c -)
else
  [ -n "$FILE" ] || die "the release has no $ARCHIVE_NAME.sha256"
  echo "note: no .sha256 next to $FILE; the bundle's own per-file checks still run on load"
fi

say "Building the image for the checked-out code"
docker compose build --quiet "$SERVICE"

say "What this release contains"
docker compose run --rm --no-deps "$SERVICE" precinctmap bundle info "$ARCHIVE"

if [ "$DRY_RUN" = 1 ]; then
  say "Dry run: nothing was changed. The archive is at $ARCHIVE"
  exit 0
fi

if [ "$ASSUME_YES" != 1 ]; then
  printf '\nThis stops the map (about a minute) and replaces all of its data. Continue? [y/N] '
  read -r answer
  case "$answer" in y|Y|yes|YES) ;; *) echo "Nothing changed."; exit 0 ;; esac
fi

# --- 2. Swap the store, restoring the old one on any failure ------------------------------
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="data/backups/precinctmap-$STAMP.duckdb"
mkdir -p data/backups
swapped=0

restore() {
  local status=$?
  if [ "$swapped" = 1 ]; then
    echo "error: the update failed; putting the previous data back" >&2
    docker compose stop "$SERVICE" >/dev/null 2>&1 || true  # it may have the new store open
    rm -f "$STORE" "$STORE.wal"
    mv "$BACKUP" "$STORE"
    [ -f "$BACKUP.wal" ] && mv "$BACKUP.wal" "$STORE.wal"
  fi
  docker compose up -d "$SERVICE" >/dev/null 2>&1 || true
  echo "The app was restarted with the previous data. Nothing else changed." >&2
  exit "$status"
}

say "Stopping the app"
docker compose stop "$SERVICE"
trap restore ERR INT TERM

if [ -f "$STORE" ]; then
  say "Backing up the current data to $BACKUP"
  mv "$STORE" "$BACKUP"
  [ -f "$STORE.wal" ] && mv "$STORE.wal" "$BACKUP.wal"
  swapped=1
fi

say "Loading the release into an empty store (checks every file and re-reconciles every total)"
docker compose run --rm --no-deps "$SERVICE" precinctmap bundle load "$ARCHIVE"

say "Starting the app"
docker compose up -d "$SERVICE"
container="$(docker compose ps -q "$SERVICE")"
for _ in $(seq 60); do
  health="$(docker inspect --format '{{.State.Health.Status}}' "$container" 2>/dev/null || echo starting)"
  [ "$health" = healthy ] && break
  [ "$health" = unhealthy ] && false
  sleep 2
done
[ "$health" = healthy ] || false
trap - ERR INT TERM

say "Done: the map is serving the new data"
if [ "$swapped" = 1 ]; then
  cat <<EOF

The previous data is in $BACKUP. To go back to it:
  docker compose stop && mv $BACKUP $STORE && docker compose up -d
Delete the backup once you're happy with the new data (about 1 GB each).
EOF
fi
