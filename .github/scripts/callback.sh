#!/usr/bin/env bash
# Send a signed callback to the Miaobu API with retry logic.
#
# Usage:
#   callback.sh <json_body>
#
# Required env vars: MIAOBU_API_URL, MIAOBU_CALLBACK_SECRET

set -euo pipefail

BODY="$1"
SIGNATURE="sha256=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$MIAOBU_CALLBACK_SECRET" | awk '{print $NF}')"

for attempt in 1 2 3 4 5; do
  HTTP_CODE=$(curl -s -o /tmp/cb_response.txt -w "%{http_code}" --max-time 30 \
    -X POST "${MIAOBU_API_URL}/api/v1/internal/build-callback" \
    -H "Content-Type: application/json" \
    -H "X-Miaobu-Signature: ${SIGNATURE}" \
    -d "$BODY") || HTTP_CODE="000"

  if [ "$HTTP_CODE" = "200" ]; then
    cat /tmp/cb_response.txt
    exit 0
  fi

  # Don't retry on client errors (4xx) — those won't resolve by retrying
  if [ "$HTTP_CODE" -ge 400 ] 2>/dev/null && [ "$HTTP_CODE" -lt 500 ] 2>/dev/null; then
    echo "::warning::Callback failed with HTTP $HTTP_CODE (client error, not retrying)"
    cat /tmp/cb_response.txt 2>/dev/null || true
    exit 0  # non-fatal for callbacks
  fi

  echo "::warning::Callback attempt $attempt failed (HTTP $HTTP_CODE), retrying in 10s..."
  sleep 10
done

echo "::warning::Callback failed after 5 attempts (non-fatal)"
