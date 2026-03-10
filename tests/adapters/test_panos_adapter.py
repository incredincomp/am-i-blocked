"""PAN-OS adapter XML traffic-log job tests."""

from __future__ import annotations

import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx
import pytest
import respx
from am_i_blocked_adapters.panos import PANOSAdapter

from tests.fixtures.panos_fixture_selector import load_capture_manifest, select_versioned_capture

REQUEST_ID = str(uuid.uuid4())
TIME_START = "2026-01-01T00:00:00+00:00"
TIME_END = "2026-01-01T00:15:00+00:00"
FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "docs" / "fixtures" / "panos_verification"


def _job_submit_xml(job_id: str = "17") -> str:
    return f"""
<response status="success">
  <result>
    <job>{job_id}</job>
  </result>
</response>
""".strip()


def _poll_pending_xml() -> str:
    return """
<response status="success">
  <result>
    <job>
      <status>ACT</status>
    </job>
  </result>
</response>
""".strip()


def _poll_finished_xml(*entries: str) -> str:
    entries_xml = "\n".join(entries)
    return f"""
<response status="success">
  <result>
    <job>
      <status>FIN</status>
    </job>
    <log>
      <logs count="{len(entries)}">
        {entries_xml}
      </logs>
    </log>
  </result>
</response>
""".strip()


def _entry_xml(action: str, rule: str = "block-ext") -> str:
    return f"""
<entry>
  <action>{action}</action>
  <rule>{rule}</rule>
  <time_generated>2026/01/01 00:10:00</time_generated>
  <dst>203.0.113.9</dst>
  <dport>443</dport>
</entry>
""".strip()


class TestPANOSAdapterTrafficLogJobs:
    def setup_method(self) -> None:
        self.adapter = PANOSAdapter(
            fw_hosts=["10.0.0.1"],
            api_key="test-key",
            verify_ssl=False,
            poll_max_attempts=3,
            poll_interval_seconds=0.0,
        )

    @pytest.mark.anyio
    @respx.mock
    async def test_query_evidence_success_normalizes_deny_and_reset(self) -> None:
        route = respx.get("https://10.0.0.1/api/")
        route.mock(
            side_effect=[
                httpx.Response(200, text=_job_submit_xml("21")),
                httpx.Response(200, text=_poll_pending_xml()),
                httpx.Response(
                    200,
                    text=_poll_finished_xml(
                        _entry_xml("allow", "allow-ext"),
                        _entry_xml("reset-client", "block-reset"),
                    ),
                ),
                httpx.Response(
                    200,
                    text=(
                        "<response status=\"success\"><result><entry name=\"block-reset\">"
                        "<action>deny</action><description>Block reset traffic</description>"
                        "<disabled>no</disabled><tag><member>secops</member></tag>"
                        "</entry></result></response>"
                    ),
                ),
            ]
        )

        records = await self.adapter.query_evidence(
            destination="api.example.com",
            port=443,
            time_window_start=TIME_START,
            time_window_end=TIME_END,
            request_id=REQUEST_ID,
        )

        assert len(records) == 1
        record = records[0]
        assert record.source.value == "panos"
        assert record.normalized["action"] == "deny"
        assert record.normalized["action_raw"] == "reset-client"
        assert record.normalized["rule_name"] == "block-reset"
        assert record.normalized["authoritative"] is True
        assert record.normalized["rule_metadata"]["rule_name"] == "block-reset"
        assert record.normalized["rule_metadata"]["rule_action"] == "deny"
        assert record.normalized["rule_metadata"]["disabled"] is False

    @pytest.mark.anyio
    @respx.mock
    async def test_query_evidence_metadata_lookup_failure_still_returns_deny_record(self) -> None:
        route = respx.get("https://10.0.0.1/api/")
        route.mock(
            side_effect=[
                httpx.Response(200, text=_job_submit_xml("22")),
                httpx.Response(200, text=_poll_finished_xml(_entry_xml("deny", "block-ext"))),
                httpx.Response(200, text="<response><result><entry name=\"block-ext\">"),
            ]
        )

        records = await self.adapter.query_evidence(
            destination="api.example.com",
            port=443,
            time_window_start=TIME_START,
            time_window_end=TIME_END,
            request_id=REQUEST_ID,
        )

        assert len(records) == 1
        assert records[0].normalized["action"] == "deny"
        assert "rule_metadata" not in records[0].normalized

    @pytest.mark.anyio
    @respx.mock
    async def test_query_evidence_timeout_returns_no_records(self) -> None:
        route = respx.get("https://10.0.0.1/api/")
        route.mock(
            side_effect=[
                httpx.Response(200, text=_job_submit_xml("31")),
                httpx.Response(200, text=_poll_pending_xml()),
                httpx.Response(200, text=_poll_pending_xml()),
                httpx.Response(200, text=_poll_pending_xml()),
            ]
        )

        records = await self.adapter.query_evidence(
            destination="api.example.com",
            port=443,
            time_window_start=TIME_START,
            time_window_end=TIME_END,
            request_id=REQUEST_ID,
        )

        assert records == []

    @pytest.mark.anyio
    @respx.mock
    async def test_query_evidence_non_deny_entries_return_no_records(self) -> None:
        route = respx.get("https://10.0.0.1/api/")
        route.mock(
            side_effect=[
                httpx.Response(200, text=_job_submit_xml("44")),
                httpx.Response(
                    200,
                    text=_poll_finished_xml(
                        _entry_xml("allow", "allow-a"),
                        _entry_xml("alert", "alert-a"),
                    ),
                ),
            ]
        )

        records = await self.adapter.query_evidence(
            destination="api.example.com",
            port=None,
            time_window_start=TIME_START,
            time_window_end=TIME_END,
            request_id=REQUEST_ID,
        )

        assert records == []

    @pytest.mark.anyio
    @respx.mock
    async def test_query_evidence_malformed_xml_returns_no_records(self) -> None:
        route = respx.get("https://10.0.0.1/api/")
        route.mock(
            side_effect=[
                httpx.Response(200, text="<response><result><job>7</job></result>"),
            ]
        )

        records = await self.adapter.query_evidence(
            destination="api.example.com",
            port=443,
            time_window_start=TIME_START,
            time_window_end=TIME_END,
            request_id=REQUEST_ID,
        )

        assert records == []


class TestPANOSAdapterRuleMetadataLookup:
    def setup_method(self) -> None:
        self.adapter = PANOSAdapter(
            fw_hosts=["10.0.0.1"],
            api_key="test-key",
            verify_ssl=False,
        )

    @pytest.mark.anyio
    @respx.mock
    async def test_lookup_rule_metadata_success(self) -> None:
        respx.get("https://10.0.0.1/api/").mock(
            return_value=httpx.Response(
                200,
                text=(
                    "<response status=\"success\"><result><entry name=\"block-ext\">"
                    "<action>deny</action><description>Block external</description>"
                    "<disabled>no</disabled><tag><member>secops</member><member>internet</member></tag>"
                    "</entry></result></response>"
                ),
            )
        )

        metadata = await self.adapter.lookup_rule_metadata(rule_name="block-ext")
        assert metadata["rule_name"] == "block-ext"
        assert metadata["rule_action"] == "deny"
        assert metadata["description"] == "Block external"
        assert metadata["disabled"] is False
        assert metadata["tags"] == ["secops", "internet"]

    @pytest.mark.anyio
    @respx.mock
    async def test_lookup_rule_metadata_no_match_returns_empty(self) -> None:
        respx.get("https://10.0.0.1/api/").mock(
            return_value=httpx.Response(
                200,
                text="<response status=\"success\"><result></result></response>",
            )
        )

        metadata = await self.adapter.lookup_rule_metadata(rule_name="missing-rule")
        assert metadata == {}

    @pytest.mark.anyio
    @respx.mock
    async def test_lookup_rule_metadata_malformed_response_returns_empty(self) -> None:
        respx.get("https://10.0.0.1/api/").mock(
            return_value=httpx.Response(200, text="<response><result><entry"),
        )
        metadata = await self.adapter.lookup_rule_metadata(rule_name="block-ext")
        assert metadata == {}

    @pytest.mark.anyio
    @respx.mock
    async def test_lookup_rule_metadata_timeout_returns_empty(self) -> None:
        respx.get("https://10.0.0.1/api/").mock(side_effect=httpx.ReadTimeout("timeout"))
        metadata = await self.adapter.lookup_rule_metadata(rule_name="block-ext")
        assert metadata == {}


class TestPANOSAdapterFixtureAlignment:
    def setup_method(self) -> None:
        self.adapter = PANOSAdapter(
            fw_hosts=["10.0.0.1"],
            api_key="test-key",
            verify_ssl=False,
        )

    def test_fixture_submit_shape_contains_job_marker_used_by_adapter(self) -> None:
        root = ET.fromstring((FIXTURE_ROOT / "traffic_log_submit_response.xml").read_text(encoding="utf-8"))
        assert (root.findtext(".//job") or "").strip()

    def test_fixture_poll_shape_parses_log_entries_with_current_extractor(self) -> None:
        # Canonical pattern for versioned PAN-OS fixture tests:
        # resolve one explicit version/scenario capture with explicit provenance gating,
        # then read fixture files from that directory.
        capture_dir = select_versioned_capture(
            version="11.0.2",
            scenario="deny-hit",
            require_provenance="template_seeded",
            minimum_verification_scope="parser_shape_only",
        )
        manifest = load_capture_manifest(capture_dir)
        assert manifest.get("panos_version_reported") == "11.0.2"
        assert manifest.get("scenario") == "deny-hit"
        assert manifest.get("capture_provenance") == "template_seeded"

        root = ET.fromstring((capture_dir / "traffic_log_poll_response.xml").read_text(encoding="utf-8"))
        status = (root.findtext(".//status") or "").strip().upper()
        assert status
        entries = self.adapter._extract_log_entries(root)
        assert entries
        assert "action" in entries[0]
        assert "rule" in entries[0]

    def test_fixture_metadata_shape_parses_with_current_metadata_extractor(self) -> None:
        root = ET.fromstring((FIXTURE_ROOT / "rule_metadata_config_response.xml").read_text(encoding="utf-8"))
        entry = root.find(".//entry")
        assert entry is not None
        rule_name = entry.attrib.get("name")
        assert rule_name
        metadata = self.adapter._extract_rule_metadata(
            root=root,
            rule_name=rule_name,
            vsys="vsys1",
            host="10.0.0.1",
        )
        assert metadata.get("rule_name") == rule_name

    def test_real_capture_query_shape_selection_fails_closed_when_capture_incomplete(self) -> None:
        # Query-shape capture currently contains a real submit error sample but no poll file,
        # so selector must fail closed rather than silently downgrading trust requirements.
        with pytest.raises(FileNotFoundError, match="missing required files"):
            select_versioned_capture(
                version="11.0.6-h1",
                scenario="query-shape",
                require_provenance="real_capture",
                minimum_verification_scope="query_shape_partial",
            )

    def test_real_capture_xpath_shape_selection_is_provenance_gated(self) -> None:
        capture_dir = select_versioned_capture(
            version="11.0.6-h1",
            scenario="xpath-shape",
            require_provenance="real_capture",
            minimum_verification_scope="xpath_shape_partial",
        )
        manifest = load_capture_manifest(capture_dir)
        assert manifest.get("capture_provenance") == "real_capture"
        assert manifest.get("scenario") == "xpath-shape"

        root = ET.fromstring((capture_dir / "rule_metadata_config_response.xml").read_text(encoding="utf-8"))
        assert root.find(".//rules/entry") is not None
