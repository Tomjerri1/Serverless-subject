#!/usr/bin/env bash
# Usage: ./scripts/upload_parallel.sh lab4-maksymchuk-2026 1 5
BUCKET=$1; FROM=$2; TO=$3
for i in $(seq "$FROM" "$TO"); do
  aws s3 cp "testdata/stale_$i.json" "s3://$BUCKET/incoming/stale_$i.json" &
done
wait
echo "Готово"