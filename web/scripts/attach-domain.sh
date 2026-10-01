#!/usr/bin/env bash
set -euo pipefail

: "${CLOUDFLARE_ACCOUNT_ID:?Set CLOUDFLARE_ACCOUNT_ID first}"
: "${CLOUDFLARE_API_TOKEN:?Set CLOUDFLARE_API_TOKEN (Pages Write permission) first}"

project="carvefoundry-web"
domain="cnc.skotic.com"

echo "Associating ${domain} with Cloudflare Pages project ${project}…"
curl --fail-with-body --show-error --silent \
  --request POST \
  "https://api.cloudflare.com/client/v4/accounts/${CLOUDFLARE_ACCOUNT_ID}/pages/projects/${project}/domains" \
  --header "Authorization: Bearer ${CLOUDFLARE_API_TOKEN}" \
  --header "Content-Type: application/json" \
  --data "{\"name\":\"${domain}\"}"
echo
echo "Check the Cloudflare Pages Custom domains panel for DNS/TLS activation."
