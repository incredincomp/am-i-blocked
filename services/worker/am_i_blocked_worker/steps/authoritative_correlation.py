"""Step 5: Query authoritative sources and collect normalized evidence."""

from __future__ import annotations

from am_i_blocked_core.config import Settings
from am_i_blocked_core.enums import EvidenceKind, EvidenceSource
from am_i_blocked_core.logging_helpers import get_logger
from am_i_blocked_core.models import EvidenceRecord

logger = get_logger(__name__)


async def run(
    request_id: str,
    destination: str,
    port: int | None,
    time_window_start: str,
    time_window_end: str,
    available_sources: list[str],
    settings: Settings,
) -> list[EvidenceRecord]:
    """Query each available adapter and aggregate evidence.

    Only queries sources listed in available_sources (from readiness check).
    """
    evidence: list[EvidenceRecord] = []

    for source in available_sources:
        adapter = _build_adapter(source, settings)
        if adapter is None:
            continue
        try:
            records = await adapter.query_evidence(
                destination=destination,
                port=port,
                time_window_start=time_window_start,
                time_window_end=time_window_end,
                request_id=request_id,
            )
            normalized_records = _normalize_authoritative_records(source=source, records=records)
            evidence.extend(normalized_records)
            logger.info(
                "evidence collected",
                source=source,
                count=len(normalized_records),
                raw_count=len(records),
            )
        except Exception as exc:
            logger.warning("adapter query failed", source=source, error=str(exc))

    return evidence


def _build_adapter(source: str, settings: Settings):  # type: ignore[return]
    """Instantiate the adapter for the given source name."""
    if source == "panos" and settings.panos_fw_hosts and settings.panos_api_key:
        from am_i_blocked_adapters.panos import PANOSAdapter
        return PANOSAdapter(
            fw_hosts=settings.panos_fw_hosts,
            api_key=settings.panos_api_key,
            verify_ssl=settings.panos_verify_ssl,
        )
    if source == "scm" and settings.scm_client_id and settings.scm_client_secret:
        from am_i_blocked_adapters.scm import SCMAdapter
        return SCMAdapter(
            client_id=settings.scm_client_id,
            client_secret=settings.scm_client_secret,
            tsg_id=settings.scm_tsg_id or "",
        )
    if source == "logscale" and settings.logscale_url and settings.logscale_token:
        from am_i_blocked_adapters.logscale import LogScaleAdapter
        return LogScaleAdapter(
            base_url=settings.logscale_url,
            repo=settings.logscale_repo or "",
            token=settings.logscale_token,
        )
    if source == "sdwan" and settings.sdwan_api_url and settings.sdwan_api_key:
        from am_i_blocked_adapters.sdwan import SDWANAdapter
        return SDWANAdapter(api_url=settings.sdwan_api_url, api_key=settings.sdwan_api_key)
    return None


def _normalize_authoritative_records(
    source: str,
    records: list[EvidenceRecord],
) -> list[EvidenceRecord]:
    """Normalize source evidence to conservative authoritative semantics.

    PAN-OS and SCM records are authoritative for deny/decrypt decisions only
    when they explicitly include authoritative flags.
    """
    authoritative_sources = {EvidenceSource.PANOS.value, EvidenceSource.SCM.value}
    if source not in authoritative_sources:
        return records

    filtered: list[EvidenceRecord] = []
    for record in records:
        if not isinstance(record, EvidenceRecord):
            continue
        if record.source.value != source:
            continue
        authoritative = record.normalized.get("authoritative")
        action = str(record.normalized.get("action", "")).strip().lower()
        has_decrypt_error = bool(record.normalized.get("decrypt_error"))
        is_authoritative_deny = action == "deny" and authoritative is True
        is_authoritative_decrypt = (
            record.kind == EvidenceKind.DECRYPT_LOG
            and has_decrypt_error
            and authoritative is True
        )
        if is_authoritative_deny or is_authoritative_decrypt:
            filtered.append(record)
    return filtered
