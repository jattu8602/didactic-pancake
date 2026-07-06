#!/bin/bash
set -e

COLLEGES=(
  "IGDTUW:http://www.igdtuw.ac.in/"
  "NSUT:https://www.nsut.ac.in/"
  "IIIT_Delhi:https://www.iiitd.ac.in/"
  "JNU:http://www.jnu.ac.in/"
  "DTU:http://www.dtu.ac.in/"
  "Jamia_Millia_Islamia:http://www.jmi.ac.in/"
)

OUTPUT_DIR="$(pwd)/scraper_output"
mkdir -p "$OUTPUT_DIR"

echo "Building Docker image..."
docker build -t college-scraper scraper/ > /dev/null 2>&1
echo "Docker image built: college-scraper"

echo ""
echo "========================================"
echo " Launching 6 scraper containers..."
echo "========================================"

CONTAINERS=()

for entry in "${COLLEGES[@]}"; do
  NAME="${entry%%:*}"
  URL="${entry#*:}"
  CONTAINER_NAME="scraper_$NAME"
  
  echo ""
  echo "Starting $CONTAINER_NAME -> $URL"
  
  docker rm -f "$CONTAINER_NAME" 2>/dev/null || true
  
  docker run -d \
    --name "$CONTAINER_NAME" \
    -v "$OUTPUT_DIR:/output" \
    college-scraper \
    --name "$NAME" --url "$URL" --output /output
  
  CONTAINERS+=("$CONTAINER_NAME")
  echo "  Container started: $CONTAINER_NAME"
done

echo ""
echo "========================================"
echo " All containers launched!"
echo "========================================"
echo ""
echo "Monitoring logs. Press Ctrl+C to stop watching (containers will keep running)."
echo ""

# Watch all logs in a multiplexed view
while true; do
  clear 2>/dev/null || true
  echo "========================================="
  echo " COLLEGE SCRAPER MONITOR  ($(date +%H:%M:%S))"
  echo "========================================="
  echo ""
  
  ALL_DONE=true
  for c in "${CONTAINERS[@]}"; do
    STATUS=$(docker inspect "$c" --format='{{.State.Status}}' 2>/dev/null || echo "not found")
    EXIT_CODE=$(docker inspect "$c" --format='{{.State.ExitCode}}' 2>/dev/null || echo "-")
    
    if [ "$STATUS" = "running" ]; then
      ALL_DONE=false
    fi
    
    # Get last 5 lines of logs
    LOGS=$(docker logs "$c" --tail 6 2>&1 | tail -5)
    
    echo "── $c [$STATUS] ───────────────────────"
    if [ -n "$LOGS" ]; then
      echo "$LOGS" | while read -r line; do
        echo "  $line"
      done
    fi
    echo ""
  done
  
  if [ "$ALL_DONE" = true ]; then
    echo ""
    echo "========================================="
    echo " ALL CONTAINERS FINISHED!"
    echo "========================================="
    echo ""
    echo "Results in: $OUTPUT_DIR"
    echo ""
    
    # Show summary
    echo "SUMMARY:"
    echo "--------"
    for c in "${CONTAINERS[@]}"; do
      EXIT_CODE=$(docker inspect "$c" --format='{{.State.ExitCode}}' 2>/dev/null || echo "-")
      echo "  $c -> exit code $EXIT_CODE"
    done
    echo ""
    echo "Files:"
    ls -la "$OUTPUT_DIR/"
    break
  fi
  
  sleep 5
done
