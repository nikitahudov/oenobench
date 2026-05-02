#!/usr/bin/env bash
# Overnight monitor for release_v1 build.
# Snapshots metrics every 5 minutes to data/logs/release_v1_monitor.csv.
#
# Stops on its own when:
#   * the build script (run_release_v1_build.sh) is no longer running, OR
#   * the row count for `release_v1` reaches >= 6500.

set -uo pipefail
cd /home/winebench/oenobench

CSV=data/logs/release_v1_monitor.csv
BUILD_LOG_GLOB="data/logs/release_v1_build_*.log"
INTERVAL=${MONITOR_INTERVAL:-300}   # 5 minutes default
TARGET=6500
TAG=release_v1

# Header (only on first launch — preserve history if csv exists)
if [[ ! -f "$CSV" ]]; then
    mkdir -p "$(dirname "$CSV")"
    echo "ts_utc,wall_min,total,draft,cb_reserve,template,fact_to_question,comparative,scenario_synthesis,distractor_mining,llm_calls,parse_fails,gate_quota_full,cb_reserved,build_alive,proj_eta_min" > "$CSV"
fi

# Start time anchor — read from build log if present, else NOW().
START_ISO=$(grep -h -m1 "release_v1 build — start" $BUILD_LOG_GLOB 2>/dev/null \
    | grep -oE '[A-Za-z]+ +[A-Za-z]+ +[0-9]+ +[0-9:]+ UTC [0-9]+' \
    | head -1)
if [[ -z "$START_ISO" ]]; then
    START_EPOCH=$(date -u +%s)
else
    START_EPOCH=$(date -d "$START_ISO" +%s 2>/dev/null || date -u +%s)
fi

while true; do
    NOW_EPOCH=$(date -u +%s)
    WALL_MIN=$(awk -v n="$NOW_EPOCH" -v s="$START_EPOCH" 'BEGIN{printf "%.1f", (n-s)/60.0}')

    # DB snapshot
    READ=$(docker exec -i wb-postgres psql -U winebench -d winebench -t -A -F'|' -c "
SELECT
  count(*),
  count(*) FILTER (WHERE q.status::text='draft'),
  count(*) FILTER (WHERE q.status::text='cb_reserve'),
  count(*) FILTER (WHERE gm.generation_method='template'),
  count(*) FILTER (WHERE gm.generation_method='fact_to_question'),
  count(*) FILTER (WHERE gm.generation_method='comparative'),
  count(*) FILTER (WHERE gm.generation_method='scenario_synthesis'),
  count(*) FILTER (WHERE gm.generation_method='distractor_mining')
FROM questions q
JOIN generation_metadata gm ON gm.question_id = q.id
WHERE '${TAG}' = ANY(q.tags);
" 2>/dev/null || echo "0|0|0|0|0|0|0|0")
    IFS='|' read -r TOTAL DRAFT CB_RES T_TMPL T_FTQ T_COMP T_SCEN T_DIST <<< "$READ"

    # Log-based counters (cheap grep on the build log)
    LATEST_LOG=$(ls -t $BUILD_LOG_GLOB 2>/dev/null | head -1)
    if [[ -n "$LATEST_LOG" && -f "$LATEST_LOG" ]]; then
        LLM_CALLS=$(grep -c "LLM call |" "$LATEST_LOG" 2>/dev/null || echo 0)
        PARSE_FAILS=$(grep -cE "Parse failed|Failed to extract JSON" "$LATEST_LOG" 2>/dev/null || echo 0)
        GATE_QF=$(grep -c "GATE QUOTA FULL" "$LATEST_LOG" 2>/dev/null || echo 0)
        CB_RESERVED_LOG=$(grep -c "GATE QUOTA FULL → RESERVED" "$LATEST_LOG" 2>/dev/null || echo 0)
    else
        LLM_CALLS=0; PARSE_FAILS=0; GATE_QF=0; CB_RESERVED_LOG=0
    fi

    # Build alive?
    if pgrep -f "run_release_v1_build.sh\|src.generators.orchestrator generate-all" > /dev/null; then
        ALIVE=1
    else
        ALIVE=0
    fi

    # Projected ETA (minutes), based on the last 5-min throughput from the CSV.
    # Find the previous snapshot ~5 min ago.
    PROJ_ETA="-"
    if [[ -f "$CSV" && $(wc -l < "$CSV") -gt 1 ]]; then
        PREV=$(tail -n 1 "$CSV")
        PREV_TS=$(echo "$PREV" | cut -d, -f1)
        PREV_TOTAL=$(echo "$PREV" | cut -d, -f3)
        if [[ -n "$PREV_TS" && "$PREV_TS" != "ts_utc" ]]; then
            PREV_EPOCH=$(date -d "$PREV_TS" +%s 2>/dev/null || echo 0)
            DT=$((NOW_EPOCH - PREV_EPOCH))
            DQ=$((TOTAL - PREV_TOTAL))
            if (( DT > 0 && DQ > 0 )); then
                # Q/sec * 60 = Q/min. ETA = (target - total) / (Q/min)
                PROJ_ETA=$(awk -v dt="$DT" -v dq="$DQ" -v t="$TARGET" -v cur="$TOTAL" 'BEGIN{
                    qpm = (dq * 60.0) / dt
                    if (cur >= t) { printf "0.0"; exit }
                    if (qpm <= 0) { printf "-"; exit }
                    printf "%.1f", (t - cur) / qpm
                }')
            fi
        fi
    fi

    NOW_ISO=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    echo "${NOW_ISO},${WALL_MIN},${TOTAL},${DRAFT},${CB_RES},${T_TMPL},${T_FTQ},${T_COMP},${T_SCEN},${T_DIST},${LLM_CALLS},${PARSE_FAILS},${GATE_QF},${CB_RESERVED_LOG},${ALIVE},${PROJ_ETA}" >> "$CSV"

    # Stop conditions
    if (( TOTAL >= TARGET )); then
        echo "$(date -u +%Y-%m-%dT%H:%M:%SZ): target ${TARGET} reached — stopping monitor" >> "$CSV"
        break
    fi
    if (( ALIVE == 0 )) && (( TOTAL > 100 )); then
        # Build no longer running and we have substantial output — terminal state.
        echo "$(date -u +%Y-%m-%dT%H:%M:%SZ): build no longer running (${TOTAL} questions) — stopping monitor" >> "$CSV"
        break
    fi

    sleep "$INTERVAL"
done
