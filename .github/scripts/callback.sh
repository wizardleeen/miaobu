#!/usr/bin/env bash
# Send a signed callback to the Miaobu API.
#
# Usage:
#   callback.sh <json_body>
#
# Required env vars: MIAOBU_API_URL, MIAOBU_CALLBACK_SECRET

set -euo pipefail

BODY="$1"
SIGNATURE="sha256=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$MIAOBU_CALLBACK_SECRET" | awk '{print $NF}')"

curl -sf --max-time 30 \
  -X POST "${MIAOBU_API_URL}/api/v1/internal/build-callback" \
  -H "Content-Type: application/json" \
  -H "X-Miaobu-Signature: ${SIGNATURE}" \
  -d "$BODY" || echo "Warning: callback failed (non-fatal)"
