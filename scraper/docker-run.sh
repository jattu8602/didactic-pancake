#!/bin/bash
# docker-run.sh — Launch N parallel Docker containers to scrape districts simultaneously
#
# Usage:
#   ./docker-run.sh --containers 5                    # 5 parallel containers
#   ./docker-run.sh --containers 3 --state "Madhya Pradesh"
#   ./docker-run.sh --list                            # List remaining districts
#   ./docker-run.sh --stop                            # Stop all running containers
#
# Each container gets a shard (e.g. --shard 0/N) so districts don't overlap.
# All write to the same ./data/scraped directory.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRAPED_DIR="$PROJECT_DIR/data/scraped"
TRACKER="$SCRIPT_DIR/district_progress.json"
CSV="$SCRIPT_DIR/../data/mp_colleges.csv"
IMAGE_NAME="college-scraper"
PROXY_FILE=""
CONTAINERS=3
STATE="Madhya Pradesh"

while [[ $# -gt 0 ]]; do
    case $1 in
        --containers) CONTAINERS="$2"; shift 2 ;;
        --state) STATE="$2"; shift 2 ;;
        --proxy-file) PROXY_FILE="$2"; shift 2 ;;
        --list) docker run --rm -v "$CSV:/data/mp_colleges.csv" "$IMAGE_NAME" --csv /data/mp_colleges.csv --state "$STATE" list; exit 0 ;;
        --stop) echo "Stopping all scraper containers..."; docker stop $(docker ps -q --filter name=scraper-) 2>/dev/null || true; echo "Done"; exit 0 ;;
        --help) echo "Usage: $0 [--containers N] [--state State] [--proxy-file file] [--list] [--stop]"; exit 0 ;;
        *) echo "Unknown: $1"; exit 1 ;;
    esac
done

# Build Docker image if not present
if ! docker image inspect "$IMAGE_NAME" &>/dev/null; then
    echo "🐳 Building Docker image: $IMAGE_NAME ..."
    docker build -t "$IMAGE_NAME" "$SCRIPT_DIR"
    echo ""
fi

mkdir -p "$SCRAPED_DIR"

# Show count of incomplete districts (from summary)
SUMMARY=$(python3 "$SCRIPT_DIR/scraper.py" summary 2>/dev/null)
DIST_COUNT=$(echo "$SUMMARY" | grep -cE '\[PARTIAL\]|\[PENDING\]' || true)

echo ""
echo "========================================"
echo "  Containers: $CONTAINERS"
echo "  Districts remaining: $DIST_COUNT"
echo "  State:      $STATE"
echo "========================================"
echo ""

if [ "$DIST_COUNT" -eq 0 ]; then
    echo "✅ All districts complete!"
    exit 0
fi

CONTAINER_NAMES=()

# Stop any previous containers
docker stop $(docker ps -q --filter name=scraper-) 2>/dev/null || true
sleep 2

for ((i=0; i<CONTAINERS; i++)); do
    CNAME="scraper-$((i+1))"

    CONTAINER_NAMES+=("$CNAME")
    echo "🚀 Starting $CNAME (shard $i/$CONTAINERS)"

    docker rm -f "$CNAME" 2>/dev/null || true
    docker run -d --name "$CNAME" \
        -e PYTHONUNBUFFERED=1 \
        -v "$SCRAPED_DIR:/data/scraped" \
        -v "$CSV:/data/mp_colleges.csv" \
        -v "$TRACKER:/app/district_progress.json" \
        ${PROXY_FILE:+-v "$(cd "$(dirname "$PROXY_FILE")" && pwd)/$(basename "$PROXY_FILE"):/app/proxies.txt"} \
        "$IMAGE_NAME" \
        --csv /data/mp_colleges.csv \
        --state "$STATE" \
        ${PROXY_FILE:+--proxy-file /app/proxies.txt} \
        --all \
        --continuous 2>/dev/null
done

echo ""
echo "========================================"
echo "  ✅ ${#CONTAINER_NAMES[@]} containers running"
echo "========================================"
echo ""
echo "📊 Check progress:  python3 scraper.py summary"
echo "📋 View logs:       docker logs scraper-1 (or -2, -3...)"
echo "🛑 Stop all:        docker stop \$(docker ps -q --filter name=scraper-)"
echo "🔁 Restart:         $0 --containers $CONTAINERS"
echo ""
