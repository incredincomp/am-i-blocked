"""Domain enums for am-i-blocked."""

from enum import StrEnum


class Verdict(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"
    UNKNOWN = "unknown"


class EnforcementPlane(StrEnum):
    ONPREM_PALO = "onprem_palo"
    STRATA_CLOUD = "strata_cloud"
    UNKNOWN = "unknown"


class PathContext(StrEnum):
    VPN_PRISMA_ACCESS = "vpn_prisma_access"
    VPN_GP_ONPREM_STATIC = "vpn_gp_onprem_static"
    SDWAN_OPSCENTER = "sdwan_opscenter"
    CAMPUS_NON_SDWAN = "campus_non_sdwan"
    UNKNOWN = "unknown"


class OwnerTeam(StrEnum):
    SECOPS = "SecOps"
    NETOPS = "NetOps"
    APPOPS = "AppOps"
    VENDOR = "Vendor"
    UNKNOWN = "Unknown"


class RequestStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class EvidenceSource(StrEnum):
    PANOS = "panos"
    SCM = "scm"
    SDWAN = "sdwan"
    LOGSCALE = "logscale"
    TORQ = "torq"
    PROBE_DNS = "probe_dns"
    PROBE_TCP = "probe_tcp"
    PROBE_TLS = "probe_tls"
    PROBE_HTTP = "probe_http"
    INTERNAL = "internal"


class DestinationType(StrEnum):
    URL = "url"
    FQDN = "fqdn"
    IP = "ip"
    UNKNOWN = "unknown"


class TimeWindow(StrEnum):
    NOW = "now"
    LAST_15M = "last_15m"
    LAST_60M = "last_60m"


class EvidenceKind(StrEnum):
    TRAFFIC_LOG = "traffic_log"
    POLICY_RULE = "policy_rule"
    DECRYPT_LOG = "decrypt_log"
    PROBE_RESULT = "probe_result"
    PATH_SIGNAL = "path_signal"
    READINESS = "readiness"
