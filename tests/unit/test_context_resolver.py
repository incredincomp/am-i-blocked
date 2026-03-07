"""Unit tests for context resolver."""

from __future__ import annotations

from am_i_blocked_core.enums import EnforcementPlane, PathContext
from am_i_blocked_worker.steps.context_resolver import run


class TestContextResolver:
    def _readiness(self, panos=False, scm=False, sdwan=False, logscale=False):
        return {
            "panos": {"available": panos},
            "scm": {"available": scm},
            "sdwan": {"available": sdwan},
            "logscale": {"available": logscale},
            "torq": {"available": False},
        }

    def test_scm_available_gives_prisma_path(self):
        ctx = run(self._readiness(scm=True))
        assert ctx.path_context == PathContext.VPN_PRISMA_ACCESS
        assert ctx.enforcement_plane == EnforcementPlane.STRATA_CLOUD
        assert ctx.path_confidence > 0.0

    def test_sdwan_available_gives_sdwan_path(self):
        ctx = run(self._readiness(panos=True, sdwan=True))
        assert ctx.path_context == PathContext.SDWAN_OPSCENTER
        assert ctx.enforcement_plane == EnforcementPlane.ONPREM_PALO

    def test_panos_only_gives_gp_path(self):
        ctx = run(self._readiness(panos=True))
        assert ctx.path_context == PathContext.VPN_GP_ONPREM_STATIC
        assert ctx.enforcement_plane == EnforcementPlane.ONPREM_PALO

    def test_nothing_available_gives_unknown(self):
        ctx = run(self._readiness())
        assert ctx.path_context == PathContext.UNKNOWN
        assert ctx.enforcement_plane == EnforcementPlane.UNKNOWN
        assert ctx.path_confidence == 0.0

    def test_explicit_hint_prisma_overrides(self):
        ctx = run(self._readiness(), requester_hints={"tunnel_type": "prisma"})
        assert ctx.path_context == PathContext.VPN_PRISMA_ACCESS

    def test_explicit_hint_sdwan_overrides(self):
        ctx = run(self._readiness(), requester_hints={"client_type": "sdwan"})
        assert ctx.path_context == PathContext.SDWAN_OPSCENTER

    def test_site_hint_propagated(self):
        ctx = run(self._readiness(scm=True), requester_hints={"sdwan_site": "site-abc"})
        assert ctx.site == "site-abc"


def test_context_resolver_signals_recorded():
    readiness = {
        "panos": {"available": True},
        "scm": {"available": False},
        "sdwan": {"available": False},
        "logscale": {"available": False},
        "torq": {"available": False},
    }
    ctx = run(readiness)
    assert "panos_available" in ctx.signals
    assert ctx.signals["panos_available"] is True
