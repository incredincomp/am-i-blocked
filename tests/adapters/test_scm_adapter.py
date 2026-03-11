"""Tests for bounded SCM readiness and evidence retrieval."""

from __future__ import annotations

import httpx
import pytest
import respx
from am_i_blocked_adapters.scm import SCMAdapter


class TestSCMAdapterReadiness:
    @pytest.mark.anyio
    async def test_readiness_not_configured(self):
        adapter = SCMAdapter(client_id=None, client_secret=None, tsg_id=None)
        result = await adapter.check_readiness()
        assert result["available"] is False
        assert result["status"] == "not_configured"

    @pytest.mark.anyio
    @respx.mock
    async def test_readiness_success_ready(self):
        adapter = SCMAdapter(
            client_id="cid",
            client_secret="sec",
            tsg_id="tsg",
            auth_url="https://auth.example.com/oauth2/access_token",
        )
        respx.post("https://auth.example.com/oauth2/access_token").mock(
            return_value=httpx.Response(200, json={"access_token": "abc123"})
        )

        result = await adapter.check_readiness()
        assert result["available"] is True
        assert result["status"] == "ready"
        assert isinstance(result["latency_ms"], int)

    @pytest.mark.anyio
    @respx.mock
    async def test_readiness_auth_failed(self):
        adapter = SCMAdapter(
            client_id="cid",
            client_secret="bad",
            tsg_id="tsg",
            auth_url="https://auth.example.com/oauth2/access_token",
        )
        respx.post("https://auth.example.com/oauth2/access_token").mock(
            return_value=httpx.Response(401, json={"error": "invalid_client"})
        )

        result = await adapter.check_readiness()
        assert result["available"] is False
        assert result["status"] == "auth_failed"

    @pytest.mark.anyio
    @respx.mock
    async def test_readiness_unauthorized(self):
        adapter = SCMAdapter(
            client_id="cid",
            client_secret="sec",
            tsg_id="tsg",
            auth_url="https://auth.example.com/oauth2/access_token",
        )
        respx.post("https://auth.example.com/oauth2/access_token").mock(
            return_value=httpx.Response(403, json={"error": "forbidden"})
        )

        result = await adapter.check_readiness()
        assert result["available"] is False
        assert result["status"] == "unauthorized"

    @pytest.mark.anyio
    @respx.mock
    async def test_readiness_timeout(self):
        adapter = SCMAdapter(
            client_id="cid",
            client_secret="sec",
            tsg_id="tsg",
            auth_url="https://auth.example.com/oauth2/access_token",
        )
        respx.post("https://auth.example.com/oauth2/access_token").mock(
            side_effect=httpx.ReadTimeout("timed out")
        )

        result = await adapter.check_readiness()
        assert result["available"] is False
        assert result["status"] == "timeout"

    @pytest.mark.anyio
    @respx.mock
    async def test_readiness_unreachable(self):
        adapter = SCMAdapter(
            client_id="cid",
            client_secret="sec",
            tsg_id="tsg",
            auth_url="https://auth.example.com/oauth2/access_token",
        )
        respx.post("https://auth.example.com/oauth2/access_token").mock(
            side_effect=httpx.ConnectError("dns failure")
        )

        result = await adapter.check_readiness()
        assert result["available"] is False
        assert result["status"] == "unreachable"

    @pytest.mark.anyio
    @respx.mock
    async def test_readiness_unexpected_response(self):
        adapter = SCMAdapter(
            client_id="cid",
            client_secret="sec",
            tsg_id="tsg",
            auth_url="https://auth.example.com/oauth2/access_token",
        )
        respx.post("https://auth.example.com/oauth2/access_token").mock(
            return_value=httpx.Response(200, json={"token_type": "Bearer"})
        )

        result = await adapter.check_readiness()
        assert result["available"] is False
        assert result["status"] == "unexpected_response"


class TestSCMAdapterEvidence:
    @pytest.mark.anyio
    @respx.mock
    async def test_query_evidence_returns_authoritative_deny_record(self):
        adapter = SCMAdapter(
            client_id="cid",
            client_secret="sec",
            tsg_id="tsg",
            auth_url="https://auth.example.com/oauth2/access_token",
            api_base_url="https://api.example.com/scm/query",
        )
        respx.post("https://auth.example.com/oauth2/access_token").mock(
            return_value=httpx.Response(200, json={"access_token": "abc123"})
        )
        respx.post("https://api.example.com/scm/query").mock(
            return_value=httpx.Response(
                200,
                json={
                    "records": [
                        {
                            "id": "evt-1",
                            "source_system": "strata_cloud_manager",
                            "authoritative": True,
                            "decision": "deny",
                            "destination": "api.example.com",
                            "port": 443,
                            "timestamp": "2026-03-11T00:00:00Z",
                            "rule_name": "cloud-block",
                            "policy_id": "p-1",
                            "reason": "Policy deny",
                        }
                    ]
                },
            )
        )

        records = await adapter.query_evidence(
            destination="api.example.com",
            port=443,
            time_window_start="2026-03-11T00:00:00Z",
            time_window_end="2026-03-11T00:15:00Z",
            request_id="11111111-1111-1111-1111-111111111111",
        )

        assert len(records) == 1
        record = records[0]
        assert record.source.value == "scm"
        assert record.kind.value == "traffic_log"
        assert record.normalized["authoritative"] is True
        assert record.normalized["action"] == "deny"
        assert record.normalized["rule_name"] == "cloud-block"

    @pytest.mark.anyio
    @respx.mock
    async def test_query_evidence_returns_authoritative_decrypt_deny_record(self):
        adapter = SCMAdapter(
            client_id="cid",
            client_secret="sec",
            tsg_id="tsg",
            auth_url="https://auth.example.com/oauth2/access_token",
            api_base_url="https://api.example.com/scm/query",
        )
        respx.post("https://auth.example.com/oauth2/access_token").mock(
            return_value=httpx.Response(200, json={"access_token": "abc123"})
        )
        respx.post("https://api.example.com/scm/query").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "event_id": "evt-2",
                            "system_of_record": "prisma_access",
                            "authoritative": True,
                            "action": "decrypt-deny",
                            "destination_value": "api.example.com",
                            "destination_port": 443,
                            "event_ts": "2026-03-11T00:00:01Z",
                            "message": "Decryption policy deny",
                        }
                    ]
                },
            )
        )

        records = await adapter.query_evidence(
            destination="api.example.com",
            port=443,
            time_window_start="2026-03-11T00:00:00Z",
            time_window_end="2026-03-11T00:15:00Z",
            request_id="22222222-2222-2222-2222-222222222222",
        )

        assert len(records) == 1
        record = records[0]
        assert record.kind.value == "decrypt_log"
        assert record.normalized["authoritative"] is True
        assert record.normalized["action"] == "decrypt_deny"
        assert record.normalized["decrypt_error"] == "Decryption policy deny"

    @pytest.mark.anyio
    @respx.mock
    async def test_query_evidence_non_authoritative_or_non_deny_returns_empty(self):
        adapter = SCMAdapter(
            client_id="cid",
            client_secret="sec",
            tsg_id="tsg",
            auth_url="https://auth.example.com/oauth2/access_token",
            api_base_url="https://api.example.com/scm/query",
        )
        respx.post("https://auth.example.com/oauth2/access_token").mock(
            return_value=httpx.Response(200, json={"access_token": "abc123"})
        )
        respx.post("https://api.example.com/scm/query").mock(
            return_value=httpx.Response(
                200,
                json={
                    "records": [
                        {
                            "source_system": "strata_cloud_manager",
                            "authoritative": False,
                            "decision": "deny",
                            "destination": "api.example.com",
                            "port": 443,
                            "timestamp": "2026-03-11T00:00:00Z",
                        },
                        {
                            "source_system": "strata_cloud_manager",
                            "authoritative": True,
                            "decision": "allow",
                            "destination": "api.example.com",
                            "port": 443,
                            "timestamp": "2026-03-11T00:00:00Z",
                        },
                    ]
                },
            )
        )

        records = await adapter.query_evidence(
            destination="api.example.com",
            port=443,
            time_window_start="2026-03-11T00:00:00Z",
            time_window_end="2026-03-11T00:15:00Z",
            request_id="33333333-3333-3333-3333-333333333333",
        )

        assert records == []

    @pytest.mark.anyio
    @respx.mock
    async def test_query_evidence_malformed_response_returns_empty(self):
        adapter = SCMAdapter(
            client_id="cid",
            client_secret="sec",
            tsg_id="tsg",
            auth_url="https://auth.example.com/oauth2/access_token",
            api_base_url="https://api.example.com/scm/query",
        )
        respx.post("https://auth.example.com/oauth2/access_token").mock(
            return_value=httpx.Response(200, json={"access_token": "abc123"})
        )
        respx.post("https://api.example.com/scm/query").mock(
            return_value=httpx.Response(200, json={"records": [{"authoritative": True, "decision": "deny"}]})
        )

        records = await adapter.query_evidence(
            destination="api.example.com",
            port=443,
            time_window_start="2026-03-11T00:00:00Z",
            time_window_end="2026-03-11T00:15:00Z",
            request_id="44444444-4444-4444-4444-444444444444",
        )

        assert records == []

    @pytest.mark.anyio
    @respx.mock
    async def test_query_evidence_auth_or_transport_failure_returns_empty(self):
        adapter = SCMAdapter(
            client_id="cid",
            client_secret="sec",
            tsg_id="tsg",
            auth_url="https://auth.example.com/oauth2/access_token",
            api_base_url="https://api.example.com/scm/query",
        )
        respx.post("https://auth.example.com/oauth2/access_token").mock(
            return_value=httpx.Response(401, json={"error": "invalid_client"})
        )

        auth_failure_records = await adapter.query_evidence(
            destination="api.example.com",
            port=443,
            time_window_start="2026-03-11T00:00:00Z",
            time_window_end="2026-03-11T00:15:00Z",
            request_id="55555555-5555-5555-5555-555555555555",
        )
        assert auth_failure_records == []

        adapter = SCMAdapter(
            client_id="cid",
            client_secret="sec",
            tsg_id="tsg",
            auth_url="https://auth.example.com/oauth2/access_token",
            api_base_url="https://api.example.com/scm/query",
        )
        respx.post("https://auth.example.com/oauth2/access_token").mock(
            return_value=httpx.Response(200, json={"access_token": "abc123"})
        )
        respx.post("https://api.example.com/scm/query").mock(
            side_effect=httpx.ConnectError("network error")
        )
        transport_failure_records = await adapter.query_evidence(
            destination="api.example.com",
            port=443,
            time_window_start="2026-03-11T00:00:00Z",
            time_window_end="2026-03-11T00:15:00Z",
            request_id="66666666-6666-6666-6666-666666666666",
        )
        assert transport_failure_records == []
