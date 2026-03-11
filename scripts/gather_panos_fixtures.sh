#!/usr/bin/env bash
# shellcheck disable=SC2016
#
# Collect a sanitized PAN-OS XML fixture pack for parser-shape and mapping verification.
#
# Backward-compatible usage:
#   ./scripts/gather_panos_fixtures.sh <fw-host> <api-key> <rule-xpath-or-name>
#
# Preferred usage (versioned captures):
#   ./scripts/gather_panos_fixtures.sh \
#     --host firewall.local \
#     --api-key "$PANOS_KEY" \
#     --rule-xpath "/config/devices/entry/vsys/entry/rulebase/security/rules/entry[@name='RULE']" \
#     --dst "example.com" \
#     --dport "443" \
#     --hours "4" \
#     --capture-label "corp-egress-deny" \
#     --version "11.0.2"
#
# Outputs:
# - Versioned capture pack under docs/fixtures/panos_verification/versions/<version>/<label_timestamp>/
# - Canonical mirrored fixtures at docs/fixtures/panos_verification/*.xml (latest sanitized set)
#
# Requirements: curl, sed, grep, dirname; xmllint optional (preferred).

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=/dev/null
source "${SCRIPT_DIR}/panos_readonly_guard.sh"

ROOT_OUT="docs/fixtures/panos_verification"
CAPTURE_LABEL=""
OVERRIDE_VERSION=""
VERIFICATION_SCOPE="real_env_partial"
FW_HOST=""
API_KEY=""
USERNAME=""
PASSWORD=""
RULE_XPATH=""
DST_QUERY=""
DPORT_QUERY=""
WINDOW_HOURS="1"
CUSTOM_LOG_QUERY=""
MAX_POLLS="30"
POLL_INTERVAL_SECS="1"
INSECURE_TLS="1"

usage() {
    cat <<'USAGE'
Usage:
  gather_panos_fixtures.sh <fw-host> <api-key> <rule-xpath-or-name>

  gather_panos_fixtures.sh [options]

Options:
  --host <fw-host>               PAN-OS management host/IP
  --api-key <key>                PAN-OS API key
  --username <username>          PAN-OS username (used for keygen if api-key missing)
  --password <password>          PAN-OS password (used for keygen if api-key missing)
  --rule-xpath <xpath-or-name>   Rule XPath (preferred) or rule identifier
  --version <panos-version>      Override PAN-OS version folder slug
  --verification-scope <scope>   Manifest verification scope (default: real_env_partial)
  --capture-label <label>        Capture label for folder naming
  --dst <destination>            Optional destination filter for log query
  --dport <port>                 Optional destination port filter for log query
  --hours <n>                    Lookback window for generated query (default: 1)
  --query <raw-query>            Full raw log query string (overrides dst/dport/hours)
  --max-polls <n>                Max poll attempts for async job (default: 30)
  --poll-interval <seconds>      Delay between polls (default: 1)
  --out-root <path>              Output root (default: docs/fixtures/panos_verification)
  --no-insecure                  Disable --insecure curl mode
  -h, --help                     Show this help

Examples:
  gather_panos_fixtures.sh firewall.local REDACTED "/config/.../rules/entry[@name='RuleA']"
  gather_panos_fixtures.sh --host 10.0.0.1 --username automation --password "$PANOS_PASS" \
    --rule-xpath "/config/..." --capture-label "keygen-capture"
  gather_panos_fixtures.sh --host 10.0.0.1 --api-key "$PANOS_KEY" --rule-xpath "/config/..." \
    --dst "example.com" --dport "443" --hours 2 --capture-label "example-deny"
USAGE
}

slugify() {
    local raw=${1:-}
    printf '%s' "$raw" \
        | tr '[:upper:]' '[:lower:]' \
        | sed -E 's/[^a-z0-9._-]+/-/g; s/^-+//; s/-+$//; s/-{2,}/-/g'
}

timestamp_utc() {
    date -u +%Y%m%dT%H%M%SZ
}

sanitize_text() {
    sed -E \
        -e 's#(key|api_key)=([^&<[:space:]]+)#\1=REDACTED_API_KEY#gI' \
        -e 's#(password|passwd|pass)=([^&<[:space:]]+)#\1=REDACTED_PASSWORD#gI' \
        -e 's#(user|username)=([^&<[:space:]]+)#\1=SANITIZED_USER#gI' \
        -e 's#(authorization: *bearer )[a-z0-9._-]+#\1REDACTED_BEARER#gI' \
        -e 's#(cookie:)[^\r\n]*#\1 REDACTED_COOKIE#gI' \
        -e 's#([[:alnum:]._%+-]+@[[:alnum:].-]+\.[[:alpha:]]{2,})#SANITIZED_EMAIL#g' \
        -e 's#\b((25[0-5]|2[0-4][0-9]|1?[0-9]{1,2})\.){3}(25[0-5]|2[0-4][0-9]|1?[0-9]{1,2})\b#SANITIZED_IPv4#g' \
        -e 's#<key>[^<]+</key>#<key>REDACTED_API_KEY</key>#gI' \
        -e 's#<(serial|serial-number)>[^<]+</(serial|serial-number)>#<\1>SANITIZED_SERIAL</\2>#gI' \
        -e 's#<(hostname|host|device-name|devicename)>[^<]+</(hostname|host|device-name|devicename)>#<\1>SANITIZED_HOST</\2>#gI' \
        -e 's#(<entry[^>]* name=")[^"]+("[^>]*>)#\1SANITIZED_ENTRY\2#gI' \
        -e 's#(uuid=")[^"]+(")#\1SANITIZED_UUID\2#gI' \
        -e 's#<member>[^<]+</member>#<member>SANITIZED_MEMBER</member>#gI' \
        -e 's#<(username|user)>[^<]+</(username|user)>#<\1>SANITIZED_USER</\2>#gI' \
        -e 's#<(ticket|ticket-id|case-id|reference-id)>[^<]+</(ticket|ticket-id|case-id|reference-id)>#<\1>SANITIZED_REF</\2>#gI'
}

xml_get() {
    local xpath=$1
    local file=$2
    local value=""
    if command -v xmllint >/dev/null 2>&1; then
        value=$(xmllint --xpath "string(${xpath})" "$file" 2>/dev/null || true)
        if [[ -n "$value" ]]; then
            printf '%s' "$value"
            return
        fi
    fi

    if [[ $xpath == './/job' ]]; then
        grep -oPm1 '(?<=<job>)[^<]+' "$file" || true
    elif [[ $xpath == './/status' ]]; then
        grep -oPm1 '(?<=<status>)[^<]+' "$file" || true
    elif [[ $xpath == './/sw-version' ]]; then
        grep -oPm1 '(?<=<sw-version>)[^<]+' "$file" || true
    elif [[ $xpath == './/key' ]]; then
        grep -oPm1 '(?<=<key>)[^<]+' "$file" || true
    else
        true
    fi
}

build_log_query_expr() {
    if [[ -n "$CUSTOM_LOG_QUERY" ]]; then
        printf '%s' "$CUSTOM_LOG_QUERY"
        return
    fi

    local parts=()
    if [[ -n "$DST_QUERY" ]]; then
        parts+=("(addr.dst eq ${DST_QUERY})")
    fi
    if [[ -n "$DPORT_QUERY" ]]; then
        parts+=("(dport eq ${DPORT_QUERY})")
    fi
    if [[ -n "$WINDOW_HOURS" ]]; then
        parts+=("(receive_time geq '$(date -u -d "-${WINDOW_HOURS} hour" '+%Y/%m/%d %H:%M:%S')')")
    fi

    if [[ ${#parts[@]} -eq 0 ]]; then
        # Broad but bounded sample query when no specific filter is supplied.
        parts+=("(receive_time geq '$(date -u -d '-1 hour' '+%Y/%m/%d %H:%M:%S')')")
    fi

    local joined=""
    local i
    for i in "${!parts[@]}"; do
        if [[ $i -gt 0 ]]; then
            joined+=" and "
        fi
        joined+="${parts[$i]}"
    done
    printf '%s' "$joined"
}

ensure_required() {
    local missing=0
    [[ -z "$FW_HOST" ]] && { echo "ERROR: --host is required" >&2; missing=1; }
    if [[ -z "$API_KEY" ]] && ([[ -z "$USERNAME" ]] || [[ -z "$PASSWORD" ]]); then
        echo "ERROR: provide --api-key, or provide both --username and --password for keygen" >&2
        missing=1
    fi
    [[ -z "$RULE_XPATH" ]] && { echo "ERROR: --rule-xpath is required" >&2; missing=1; }
    if [[ "$missing" -eq 1 ]]; then
        exit 1
    fi
    return 0
}

# Backward-compatible positional mode.
if [[ $# -eq 3 ]] && [[ $1 != --* ]]; then
    FW_HOST=$1
    API_KEY=$2
    RULE_XPATH=$3
else
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --host) FW_HOST=${2:-}; shift 2 ;;
            --api-key) API_KEY=${2:-}; shift 2 ;;
            --username) USERNAME=${2:-}; shift 2 ;;
            --password) PASSWORD=${2:-}; shift 2 ;;
            --rule-xpath) RULE_XPATH=${2:-}; shift 2 ;;
            --version) OVERRIDE_VERSION=${2:-}; shift 2 ;;
            --verification-scope) VERIFICATION_SCOPE=${2:-}; shift 2 ;;
            --capture-label) CAPTURE_LABEL=${2:-}; shift 2 ;;
            --dst) DST_QUERY=${2:-}; shift 2 ;;
            --dport) DPORT_QUERY=${2:-}; shift 2 ;;
            --hours) WINDOW_HOURS=${2:-}; shift 2 ;;
            --query) CUSTOM_LOG_QUERY=${2:-}; shift 2 ;;
            --max-polls) MAX_POLLS=${2:-}; shift 2 ;;
            --poll-interval) POLL_INTERVAL_SECS=${2:-}; shift 2 ;;
            --out-root) ROOT_OUT=${2:-}; shift 2 ;;
            --no-insecure) INSECURE_TLS="0"; shift ;;
            -h|--help) usage; exit 0 ;;
            *)
                echo "ERROR: unknown argument: $1" >&2
                usage
                exit 1
                ;;
        esac
    done
fi

ensure_required

case "$VERIFICATION_SCOPE" in
    parser_shape_only|query_shape_partial|xpath_shape_partial|real_env_partial|real_env_high_confidence) ;;
    *)
        echo "ERROR: invalid --verification-scope=${VERIFICATION_SCOPE}" >&2
        exit 1
        ;;
esac

mkdir -p "$ROOT_OUT"
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

curl_opts=(--silent --show-error --fail)
if [[ "$INSECURE_TLS" == "1" ]]; then
    curl_opts+=(--insecure)
fi
curl_opts_no_fail=(--silent --show-error)
if [[ "$INSECURE_TLS" == "1" ]]; then
    curl_opts_no_fail+=(--insecure)
fi

request_get() {
    local url=$1
    local raw_out=$2
    local req_out=$3

    printf 'GET %s\n' "$url" | sanitize_text > "$req_out"
    curl "${curl_opts[@]}" "$url" > "$raw_out"
}

request_get_with_encoded_param() {
    local base_url=$1
    local encoded_param=$2
    local raw_out=$3
    local req_out=$4

    printf 'GET %s&%s\n' "$base_url" "$encoded_param" | sanitize_text > "$req_out"
    curl "${curl_opts[@]}" --get "$base_url" --data-urlencode "$encoded_param" > "$raw_out"
}

request_keygen() {
    local raw_out=$1
    local req_out=$2
    panos_guard_allowed_request "keygen" ""
    {
        printf 'POST https://%s/api/?type=keygen (form-urlencoded user,password)\n' "$FW_HOST"
    } | sanitize_text > "$req_out"
    curl "${curl_opts_no_fail[@]}" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -X POST \
        "https://${FW_HOST}/api/?type=keygen" \
        --data-urlencode "user=${USERNAME}" \
        --data-urlencode "password=${PASSWORD}" \
        > "$raw_out" || return 1

    if grep -Eqi 'Invalid Credential(s)?' "$raw_out" && grep -Eqi 'code="403"|status="error"' "$raw_out"; then
        return 3
    fi
    return 0
}

print_auth_failure_guidance() {
    cat >&2 <<'EOF'
ERROR: PAN-OS XML API keygen returned 403 Invalid Credential.
The XML API endpoint is reachable, but credentials/API access were rejected.
Keygen in this harness uses documented form-urlencoded POST /api/ with type=keygen.

Operator preflight checklist:
  1. Preferred unblock: provide a known-good API key via --api-key.
  2. Ensure the admin role for this account has XML API access enabled.
  3. Ensure XML API permissions include required read scopes for this workflow:
     - log retrieval (type=log submit/get)
     - configuration read (type=config action=get|show|complete)
  4. If using external auth, verify username format matches backend expectations.
  5. Do not retry live capture until valid API key or API-enabled account is confirmed.
EOF
}

response_has_invalid_credential() {
    local file_path=$1
    [[ -f "$file_path" ]] || return 1
    grep -Eqi 'Invalid Credential(s)?' "$file_path" && grep -Eqi 'code="403"|status="error"' "$file_path"
}

API_KEY_SOURCE="provided"
sanitize_scalar() {
    printf '%s' "$1" | sanitize_text
}

if [[ -z "$API_KEY" ]]; then
    echo "[0/5] requesting API key using username/password..."
    API_KEY_SOURCE="keygen"
    KEYGEN_RAW="$TMP_DIR/keygen.raw.xml"
    KEYGEN_REQ="$TMP_DIR/keygen.request.txt"
    if ! request_keygen "$KEYGEN_RAW" "$KEYGEN_REQ"; then
        if [[ -f "$KEYGEN_RAW" ]]; then
            sanitize_text < "$KEYGEN_RAW" > "$TMP_DIR/keygen.sanitized.xml"
        fi
        if response_has_invalid_credential "$TMP_DIR/keygen.sanitized.xml"; then
            print_auth_failure_guidance
            echo "Keygen response summary (sanitized):" >&2
            head -n 5 "$TMP_DIR/keygen.sanitized.xml" >&2
            exit 1
        fi
        echo "ERROR: keygen request failed before API key retrieval. Check host reachability/TLS and account/API role permissions." >&2
        exit 1
    fi
    API_KEY=$(xml_get './/key' "$KEYGEN_RAW")
    if [[ -z "$API_KEY" ]]; then
        if [[ -f "$KEYGEN_RAW" ]]; then
            sanitize_text < "$KEYGEN_RAW" > "$TMP_DIR/keygen.sanitized.xml"
        fi
        if response_has_invalid_credential "$TMP_DIR/keygen.sanitized.xml"; then
            print_auth_failure_guidance
        else
            echo "ERROR: keygen response did not contain <key>; cannot continue." >&2
        fi
        exit 1
    fi
fi

echo "[1/4] collecting system info..."
SYSTEM_INFO_RAW="$TMP_DIR/system_info.raw.xml"
SYSTEM_INFO_REQ="$TMP_DIR/system_info.request.txt"
panos_guard_allowed_request "op" "show_system_info"
request_get \
    "https://${FW_HOST}/api/?type=op&cmd=<show><system><info></info></system></show>&key=${API_KEY}" \
    "$SYSTEM_INFO_RAW" \
    "$SYSTEM_INFO_REQ"

SW_VERSION=$(xml_get './/sw-version' "$SYSTEM_INFO_RAW")
if [[ -z "$SW_VERSION" ]]; then
    SW_VERSION="unknown_version"
fi

PANOS_VERSION_SOURCE="auto_detected"
if [[ -n "$OVERRIDE_VERSION" ]]; then
    PANOS_VERSION_SOURCE="override"
elif [[ "$SW_VERSION" == "unknown_version" ]]; then
    PANOS_VERSION_SOURCE="unknown"
fi

VERSION_SLUG=$(slugify "${OVERRIDE_VERSION:-$SW_VERSION}")
[[ -z "$VERSION_SLUG" ]] && VERSION_SLUG="unknown_version"

if [[ -z "$CAPTURE_LABEL" ]]; then
    CAPTURE_LABEL="capture"
fi
CAPTURE_SLUG=$(slugify "$CAPTURE_LABEL")
[[ -z "$CAPTURE_SLUG" ]] && CAPTURE_SLUG="capture"

CAPTURE_ID="${CAPTURE_SLUG}_$(timestamp_utc)"
VERSION_DIR="$ROOT_OUT/versions/$VERSION_SLUG/$CAPTURE_ID"
mkdir -p "$VERSION_DIR"

sanitize_text < "$SYSTEM_INFO_RAW" > "$VERSION_DIR/system_info.xml"
cp "$SYSTEM_INFO_REQ" "$VERSION_DIR/system_info_request.txt"
if [[ "$API_KEY_SOURCE" == "keygen" ]]; then
    sanitize_text < "$KEYGEN_RAW" > "$VERSION_DIR/api_keygen_response.xml"
    cp "$KEYGEN_REQ" "$VERSION_DIR/api_keygen_request.txt"
fi

LOG_QUERY_EXPR=$(build_log_query_expr)

# PAN-OS XML log query shape intentionally follows current adapter assumptions; do not treat
# fields as universally verified across PAN-OS versions without validated fixture evidence.
SUBMIT_URL_BASE="https://${FW_HOST}/api/?type=log&log-type=traffic&key=${API_KEY}"
SUBMIT_RAW="$TMP_DIR/traffic_submit.raw.xml"
SUBMIT_REQ="$VERSION_DIR/traffic_log_submit_request.txt"
SUBMIT_SAN="$VERSION_DIR/traffic_log_submit_response.xml"

echo "[2/4] submitting traffic-log query job..."
panos_guard_allowed_request "log" ""
request_get_with_encoded_param "$SUBMIT_URL_BASE" "query=${LOG_QUERY_EXPR}" "$SUBMIT_RAW" "$SUBMIT_REQ"
sanitize_text < "$SUBMIT_RAW" > "$SUBMIT_SAN"

JOB_ID=$(xml_get './/job' "$SUBMIT_RAW")
POLL_RAW_LAST=""

if [[ -n "$JOB_ID" ]]; then
    echo "[3/4] polling job-id=${JOB_ID} (max=${MAX_POLLS})..."
    poll_count=0
    while [[ $poll_count -lt $MAX_POLLS ]]; do
        poll_count=$((poll_count + 1))
        POLL_URL="https://${FW_HOST}/api/?type=log&action=get&job-id=${JOB_ID}&key=${API_KEY}"
        POLL_RAW="$TMP_DIR/traffic_poll_${poll_count}.raw.xml"
        POLL_REQ="$VERSION_DIR/traffic_log_poll_request_${poll_count}.txt"
        POLL_SAN="$VERSION_DIR/traffic_log_poll_response_${poll_count}.xml"

        panos_guard_allowed_request "log" "get"
        request_get "$POLL_URL" "$POLL_RAW" "$POLL_REQ"
        sanitize_text < "$POLL_RAW" > "$POLL_SAN"
        POLL_RAW_LAST="$POLL_RAW"

        status=$(xml_get './/status' "$POLL_RAW")
        echo "  poll #${poll_count}: status=${status:-UNKNOWN}"
        if [[ "$status" == "FIN" ]]; then
            break
        fi
        sleep "$POLL_INTERVAL_SECS"
    done

    if [[ -n "$POLL_RAW_LAST" ]]; then
        sanitize_text < "$POLL_RAW_LAST" > "$VERSION_DIR/traffic_log_poll_response.xml"
    fi
else
    echo "WARN: submit response did not include <job>; no poll capture created." >&2
fi

echo "[4/4] collecting rule metadata config response..."
RULE_CFG_RAW="$TMP_DIR/rule_config.raw.xml"
RULE_CFG_REQ="$VERSION_DIR/rule_metadata_config_request.txt"
RULE_CFG_SAN="$VERSION_DIR/rule_metadata_config_response.xml"
panos_guard_allowed_request "config" "show"
request_get_with_encoded_param \
    "https://${FW_HOST}/api/?type=config&action=show&key=${API_KEY}" \
    "xpath=${RULE_XPATH}" \
    "$RULE_CFG_RAW" \
    "$RULE_CFG_REQ"
sanitize_text < "$RULE_CFG_RAW" > "$RULE_CFG_SAN"

RULE_PARENT=$(dirname "$RULE_XPATH")
RULE_COMPLETE_RAW="$TMP_DIR/rule_complete.raw.xml"
RULE_COMPLETE_REQ="$VERSION_DIR/rule_metadata_config_complete_request.txt"
RULE_COMPLETE_SAN="$VERSION_DIR/rule_metadata_config_complete_response.xml"
panos_guard_allowed_request "config" "complete"
request_get_with_encoded_param \
    "https://${FW_HOST}/api/?type=config&action=complete&key=${API_KEY}" \
    "xpath=${RULE_PARENT}" \
    "$RULE_COMPLETE_RAW" \
    "$RULE_COMPLETE_REQ"
sanitize_text < "$RULE_COMPLETE_RAW" > "$RULE_COMPLETE_SAN"

cat > "$VERSION_DIR/CAPTURE_METADATA.txt" <<META
captured_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
capture_label=${CAPTURE_SLUG}
capture_provenance=real_capture
verification_scope=${VERIFICATION_SCOPE}
panos_version_reported=${SW_VERSION}
panos_version_source=${PANOS_VERSION_SOURCE}
scenario=${CAPTURE_SLUG}
firewall_host_input=$(sanitize_scalar "${FW_HOST}")
rule_xpath_input=$(sanitize_scalar "${RULE_XPATH}")
log_query_expr=${LOG_QUERY_EXPR}
max_polls=${MAX_POLLS}
poll_interval_secs=${POLL_INTERVAL_SECS}
notes=Sanitized real-firewall fixture capture; values are representative structure only.
api_key_source=${API_KEY_SOURCE}
META

# Mirror latest sanitized set into canonical filenames used by validation tests.
cp "$VERSION_DIR/traffic_log_submit_response.xml" "$ROOT_OUT/traffic_log_submit_response.xml"
if [[ -f "$VERSION_DIR/traffic_log_poll_response.xml" ]]; then
    cp "$VERSION_DIR/traffic_log_poll_response.xml" "$ROOT_OUT/traffic_log_poll_response.xml"
fi
cp "$VERSION_DIR/rule_metadata_config_response.xml" "$ROOT_OUT/rule_metadata_config_response.xml"
cp "$VERSION_DIR/system_info.xml" "$ROOT_OUT/system_info.xml"

cat <<EOF
Capture complete.

Versioned fixture set:
  ${VERSION_DIR}

Canonical fixture mirror (latest sanitized):
  ${ROOT_OUT}/traffic_log_submit_response.xml
  ${ROOT_OUT}/traffic_log_poll_response.xml
  ${ROOT_OUT}/rule_metadata_config_response.xml

Next steps:
  1. Manually inspect XML and request logs for residual sensitive values.
  2. Keep placeholders consistent if additional redaction is needed.
  3. Re-run: uv run pytest -q tests/fixtures/test_panos_verification_fixture_pack.py
EOF
