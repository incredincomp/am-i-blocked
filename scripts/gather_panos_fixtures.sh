#!/usr/bin/env bash
# Usage:
#   ./scripts/gather_panos_fixtures.sh <fw-host> <api-key> <rule-name-or-xpath>
#
# This helper issues the sequence of PAN-OS API calls described in the
# verification README and writes sanitized copies to the fixtures directory.
#
# The script is intentionally minimal; it simply records the raw HTTP
# exchanges and then strips out any API keys or obvious private data so
# the resulting files are safe to commit.
#
# Requirements: curl, sed, xmllint (optional for pretty-printing)

set -euo pipefail

if [[ $# -lt 3 ]]; then
    cat <<EOF
Usage: $0 <fw-host> <api-key> <rule-xpath-or-name>

Examples:
  $0 firewall.homelab.local REDACTED "*/rules/Local%20net-to-internet"
  $0 10.0.0.1 abc123 "/config/pre-rulebase/security/rules/my-rule"
EOF
    exit 1
fi

FW_HOST=$1
API_KEY=$2
RULE_XPATH=$3

OUTDIR=docs/fixtures/panos_verification
mkdir -p "$OUTDIR"

# helper to sanitize query strings (remove key= and tokenise names)
sanitize() {
    sed -E \
        -e 's/(key|api_key)=[^&]*/\1=REDACTED/g' \
        -e 's/hostname=[^&]*/hostname=REDACTED/g' \
        -e 's/serial=[^&]*/serial=REDACTED/g' \
        -e 's/name=[^&]*/name=REDACTED/g'
}

curl_opts=(--silent --show-error --insecure)    # API often uses self-signed certs

# 1. PAN-OS version/build
echo "fetching system info..."
curl "https://${FW_HOST}/api/?type=op&cmd=<show><system><info></info></system></show>&key=${API_KEY}" \
    | sanitize > "$OUTDIR/system_info.xml"

# 2. submit traffic log query
LOG_QUERY="type=log&log-type=traffic&log-start-time=$(date -u +%Y/%m/%d)"
# (user can customize additional parameters by editing this file)

echo "submitting log query..."
REQ="https://${FW_HOST}/api/?${LOG_QUERY}&key=${API_KEY}"
printf 'POST %s
' "$REQ" > "$OUTDIR/traffic_log_submit_request.txt"

curl "${REQ}" > "$OUTDIR/traffic_log_submit_response.xml"
sanitize < "$OUTDIR/traffic_log_submit_response.xml" > "$OUTDIR/traffic_log_submit_response_sanitized.xml"

JOB_ID=$(grep -oPm1 '(?<=<job>)[^<]+' "$OUTDIR/traffic_log_submit_response.xml" || true)

if [[ -n "$JOB_ID" ]]; then
    echo "polling job $JOB_ID until complete..."
    while :; do
        sleep 1
        POLL_REQ="https://${FW_HOST}/api/?type=log&action=get&job-id=${JOB_ID}&key=${API_KEY}"
        curl "${POLL_REQ}" > "$OUTDIR/traffic_log_poll_response.xml"
        sanitize < "$OUTDIR/traffic_log_poll_response.xml" > "$OUTDIR/traffic_log_poll_response_sanitized.xml"
        STATUS=$(xmllint --xpath 'string(//status)' "$OUTDIR/traffic_log_poll_response.xml" 2>/dev/null || echo "")
        echo "status=$STATUS"
        if [[ "$STATUS" = "FIN" ]]; then
            break
        fi
    done
fi

# 3. fetch rule metadata config response (show + complete)
echo "fetching config for rule xpath '$RULE_XPATH'..."

# show
curl "https://${FW_HOST}/api/?type=config&action=show&xpath=${RULE_XPATH}&key=${API_KEY}" \
    | sanitize > "$OUTDIR/rule_metadata_config_response.xml"

# complete (parent tree)
PARENT=$(dirname "$RULE_XPATH")
curl "https://${FW_HOST}/api/?type=config&action=complete&xpath=${PARENT}&key=${API_KEY}" \
    | sanitize > "$OUTDIR/rule_metadata_config_complete.xml"

cat <<EOF
Fixtures written to $OUTDIR.  Please inspect and remove any remaining
sensitive details before committing.

You can add other API exchanges (for example the debug-console output) by
hand or by editing the script.
EOF
