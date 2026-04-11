#!/bin/bash
# Overnight scraper run — runs all rebuilt scrapers sequentially
# Each scraper gets 30 min timeout. Results logged to data/logs/overnight_run.log
# Usage: nohup bash scripts/run_all_scrapers.sh &

set -o pipefail
LOG="data/logs/overnight_run_$(date +%Y%m%d_%H%M%S).log"
mkdir -p data/logs

echo "=== OenoBench Overnight Scraper Run ===" | tee "$LOG"
echo "Started: $(date)" | tee -a "$LOG"
echo "Log file: $LOG" | tee -a "$LOG"
echo "" | tee -a "$LOG"

# Get initial DB count
INITIAL=$(docker exec wb-postgres psql -U winebench -d winebench -t -c "SELECT COUNT(*) FROM facts;" 2>/dev/null | tr -d ' ')
echo "Initial DB fact count: $INITIAL" | tee -a "$LOG"
echo "" | tee -a "$LOG"

# All scrapers that need running (rebuilt ones that may not have populated yet)
SCRAPERS=(
  rhone_loire_alsace
  europe
  spain_enrichment
  portugal_enrichment
  germany_enrichment
  eu_oiv
  usa_enrichment
  newworld
  hungary_georgia
  croatia_slovenia
  australia_nz_enrichment
  south_africa_enrichment
  south_america
  canada
  england
  lebanon_israel
)

TOTAL_INSERTED=0

for scraper in "${SCRAPERS[@]}"; do
  echo "=== $scraper ===" | tee -a "$LOG"
  echo "Started: $(date)" | tee -a "$LOG"

  BEFORE=$(docker exec wb-postgres psql -U winebench -d winebench -t -c "SELECT COUNT(*) FROM facts;" 2>/dev/null | tr -d ' ')

  # 30 min timeout per scraper
  timeout 1800 python3 -m src.scrapers.$scraper --all 2>&1 | tee -a "$LOG"
  EXIT_CODE=$?

  AFTER=$(docker exec wb-postgres psql -U winebench -d winebench -t -c "SELECT COUNT(*) FROM facts;" 2>/dev/null | tr -d ' ')
  INSERTED=$((AFTER - BEFORE))
  TOTAL_INSERTED=$((TOTAL_INSERTED + INSERTED))

  if [ $EXIT_CODE -eq 124 ]; then
    echo "TIMEOUT after 30 min" | tee -a "$LOG"
  elif [ $EXIT_CODE -ne 0 ]; then
    echo "ERROR: exit code $EXIT_CODE" | tee -a "$LOG"
  fi

  echo "Facts inserted: $INSERTED (DB: $BEFORE → $AFTER)" | tee -a "$LOG"
  echo "Finished: $(date)" | tee -a "$LOG"
  echo "" | tee -a "$LOG"

  # 30s cooldown between scrapers to avoid rate limits
  sleep 30
done

FINAL=$(docker exec wb-postgres psql -U winebench -d winebench -t -c "SELECT COUNT(*) FROM facts;" 2>/dev/null | tr -d ' ')

echo "========================================" | tee -a "$LOG"
echo "=== OVERNIGHT RUN COMPLETE ===" | tee -a "$LOG"
echo "Finished: $(date)" | tee -a "$LOG"
echo "Initial DB: $INITIAL facts" | tee -a "$LOG"
echo "Final DB: $FINAL facts" | tee -a "$LOG"
echo "Total new facts: $TOTAL_INSERTED" | tee -a "$LOG"
echo "========================================" | tee -a "$LOG"

# Refresh the paper summary table
docker exec -i wb-postgres psql -U winebench -d winebench << 'SQL' >> "$LOG" 2>&1
TRUNCATE fact_count_summary;
INSERT INTO fact_count_summary (country, domain, source_name, fact_count)
SELECT country, domain, source_name, COUNT(*) as fact_count
FROM (
  SELECT f.domain, s.name as source_name,
    CASE
      WHEN f.subdomain IN ('italy', 'italian_appellations', 'italian_consortiums') THEN 'Italy'
      WHEN f.subdomain IN ('france', 'bordeaux', 'burgundy', 'champagne', 'rhone', 'loire', 'alsace') THEN 'France'
      WHEN f.subdomain IN ('spain', 'spanish') THEN 'Spain'
      WHEN f.subdomain IN ('portugal', 'portuguese', 'port') THEN 'Portugal'
      WHEN f.subdomain IN ('germany', 'german') THEN 'Germany'
      WHEN f.subdomain IN ('austria', 'austrian') THEN 'Austria'
      WHEN f.subdomain IN ('greece', 'greek') THEN 'Greece'
      WHEN f.subdomain IN ('hungary', 'hungarian') THEN 'Hungary'
      WHEN f.subdomain IN ('georgia', 'georgian') THEN 'Georgia'
      WHEN f.subdomain IN ('croatia', 'croatian') THEN 'Croatia'
      WHEN f.subdomain IN ('slovenia', 'slovenian') THEN 'Slovenia'
      WHEN f.subdomain IN ('australia', 'australian') THEN 'Australia'
      WHEN f.subdomain IN ('new_zealand', 'nz') THEN 'New Zealand'
      WHEN f.subdomain IN ('south_africa', 'sa') THEN 'South Africa'
      WHEN f.subdomain IN ('argentina', 'argentine') THEN 'Argentina'
      WHEN f.subdomain IN ('chile', 'chilean') THEN 'Chile'
      WHEN f.subdomain IN ('us', 'usa', 'us_avas', 'us_labeling', 'us_regulation', 'ava') THEN 'United States'
      WHEN f.subdomain IN ('canada', 'canadian') THEN 'Canada'
      WHEN f.subdomain IN ('england', 'english', 'uk') THEN 'England'
      WHEN f.subdomain IN ('lebanon', 'lebanese') THEN 'Lebanon'
      WHEN f.subdomain IN ('israel', 'israeli') THEN 'Israel'
      WHEN f.subdomain = 'appellations' THEN 'France'
      ELSE 'General'
    END as country
  FROM facts f JOIN sources s ON f.source_id = s.id
) sub
GROUP BY country, domain, source_name;
SQL

echo "Paper summary table refreshed." | tee -a "$LOG"
