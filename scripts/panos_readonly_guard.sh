#!/usr/bin/env bash
# Guard helpers for PAN-OS XML API read-only fixture collection.

set -euo pipefail

panos_guard_allowed_request() {
    local request_type=${1:-}
    local action=${2:-}

    case "$request_type" in
        op)
            # Restrict op commands to explicit read-only show system info for this workflow.
            if [[ "$action" != "show_system_info" ]]; then
                echo "ERROR: disallowed op action: ${action}" >&2
                return 1
            fi
            ;;
        log)
            # allow initial submit (no action) and poll by action=get.
            if [[ -n "$action" ]] && [[ "$action" != "get" ]]; then
                echo "ERROR: disallowed log action: ${action}" >&2
                return 1
            fi
            ;;
        config)
            case "$action" in
                get|show|complete) ;;
                *)
                    echo "ERROR: disallowed config action: ${action}" >&2
                    return 1
                    ;;
            esac
            ;;
        keygen)
            # keygen bootstrap is allowed only for username/password mode.
            if [[ -n "$action" ]]; then
                echo "ERROR: disallowed keygen action: ${action}" >&2
                return 1
            fi
            ;;
        *)
            echo "ERROR: disallowed request type: ${request_type}" >&2
            return 1
            ;;
    esac
}

if [[ "${1:-}" == "--assert" ]]; then
    if [[ $# -lt 2 ]] || [[ $# -gt 3 ]]; then
        echo "Usage: $0 --assert <type> [action]" >&2
        exit 2
    fi
    panos_guard_allowed_request "$2" "${3:-}"
fi

