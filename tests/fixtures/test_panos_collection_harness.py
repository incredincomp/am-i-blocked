"""Tests for PAN-OS fixture collection harness safety and manifest behavior."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATHER_SCRIPT = REPO_ROOT / "scripts" / "gather_panos_fixtures.sh"
GUARD_SCRIPT = REPO_ROOT / "scripts" / "panos_readonly_guard.sh"


def _write_fake_curl(fake_bin: Path) -> None:
    fake_bin.mkdir(parents=True, exist_ok=True)
    script = fake_bin / "curl"
    script.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
args="$*"
if printf '%s' "$args" | grep -q "type=keygen"; then
  cat <<'XML'
<response status="success"><result><key>REAL_KEY_123</key></result></response>
XML
  exit 0
fi
if printf '%s' "$args" | grep -q "type=op"; then
  cat <<'XML'
<response status="success"><result><system><sw-version>11.0.2</sw-version></system></result></response>
XML
  exit 0
fi
if printf '%s' "$args" | grep -q "type=log&log-type=traffic"; then
  cat <<'XML'
<response status="success"><result><job>123</job></result></response>
XML
  exit 0
fi
if printf '%s' "$args" | grep -q "type=log&action=get"; then
  cat <<'XML'
<response status="success"><result><job><status>FIN</status></job><log><logs count="1"><entry><action>deny</action><rule>sensitive-rule</rule></entry></logs></log></result></response>
XML
  exit 0
fi
if printf '%s' "$args" | grep -q "type=config&action=show"; then
  cat <<'XML'
<response status="success"><result><entry name="sensitive-rule"><action>deny</action></entry></result></response>
XML
  exit 0
fi
if printf '%s' "$args" | grep -q "type=config&action=complete"; then
  cat <<'XML'
<response status="success"><result><completions><completion value="rules"/></completions></result></response>
XML
  exit 0
fi
echo "unexpected curl args: $args" >&2
exit 2
""",
        encoding="utf-8",
    )
    script.chmod(0o755)


def _write_fake_curl_keygen_post_only(fake_bin: Path) -> None:
    fake_bin.mkdir(parents=True, exist_ok=True)
    script = fake_bin / "curl"
    script.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
args="$*"
if printf '%s' "$args" | grep -q "type=keygen"; then
  if printf '%s' "$args" | grep -q -- "--get"; then
    echo "keygen GET rejected for test fallback" >&2
    exit 22
  fi
  cat <<'XML'
<response status="success"><result><key>REAL_KEY_123</key></result></response>
XML
  exit 0
fi
if printf '%s' "$args" | grep -q "type=op"; then
  cat <<'XML'
<response status="success"><result><system><sw-version>11.0.2</sw-version></system></result></response>
XML
  exit 0
fi
if printf '%s' "$args" | grep -q "type=log&log-type=traffic"; then
  cat <<'XML'
<response status="success"><result><job>123</job></result></response>
XML
  exit 0
fi
if printf '%s' "$args" | grep -q "type=log&action=get"; then
  cat <<'XML'
<response status="success"><result><job><status>FIN</status></job><log><logs count="1"><entry><action>deny</action></entry></logs></log></result></response>
XML
  exit 0
fi
if printf '%s' "$args" | grep -q "type=config&action=show"; then
  cat <<'XML'
<response status="success"><result><entry name="rule-a"><action>deny</action></entry></result></response>
XML
  exit 0
fi
if printf '%s' "$args" | grep -q "type=config&action=complete"; then
  cat <<'XML'
<response status="success"><result><completions><completion value="rules"/></completions></result></response>
XML
  exit 0
fi
echo "unexpected curl args: $args" >&2
exit 2
""",
        encoding="utf-8",
    )
    script.chmod(0o755)


def _write_fake_curl_keygen_invalid_credential(fake_bin: Path) -> None:
    fake_bin.mkdir(parents=True, exist_ok=True)
    script = fake_bin / "curl"
    script.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
args="$*"
if printf '%s' "$args" | grep -q "type=keygen"; then
  cat <<'XML'
<response status="error" code="403"><msg><line>Invalid Credential</line></msg></response>
XML
  exit 0
fi
echo "unexpected curl args: $args" >&2
exit 2
""",
        encoding="utf-8",
    )
    script.chmod(0o755)


def _write_fake_curl_keygen_non_auth_error(fake_bin: Path) -> None:
    fake_bin.mkdir(parents=True, exist_ok=True)
    script = fake_bin / "curl"
    script.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
args="$*"
if printf '%s' "$args" | grep -q "type=keygen"; then
  cat <<'XML'
<response status="error" code="17"><msg><line>Insufficient privileges</line></msg></response>
XML
  exit 0
fi
echo "unexpected curl args: $args" >&2
exit 2
""",
        encoding="utf-8",
    )
    script.chmod(0o755)


def _capture_dir(out_root: Path) -> Path:
    captures = sorted((out_root / "versions" / "11.0.2").glob("*"))
    assert captures
    return captures[-1]


def test_readonly_guard_rejects_disallowed_config_action() -> None:
    proc = subprocess.run(
        [str(GUARD_SCRIPT), "--assert", "config", "delete"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "disallowed config action" in proc.stderr


def test_readonly_guard_allows_expected_log_poll_action() -> None:
    subprocess.run(
        [str(GUARD_SCRIPT), "--assert", "log", "get"],
        cwd=REPO_ROOT,
        check=True,
    )


def test_gather_script_writes_real_capture_manifest_and_sanitized_keygen_artifacts(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "fake_bin"
    _write_fake_curl(fake_bin)
    out_root = tmp_path / "fixtures"

    env = dict(os.environ)
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"

    proc = subprocess.run(
        [
            str(GATHER_SCRIPT),
            "--host",
            "10.0.0.1",
            "--username",
            "admin",
            "--password",
            "super-secret-password",
            "--rule-xpath",
            "/config/devices/entry[@name='LOCAL-DEVICE']/vsys/entry[@name='vsys1']/rulebase/security/rules",
            "--capture-label",
            "deny-hit",
            "--out-root",
            str(out_root),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"

    capture_dir = _capture_dir(out_root)
    manifest = (capture_dir / "CAPTURE_METADATA.txt").read_text(encoding="utf-8")
    assert "capture_provenance=real_capture" in manifest
    assert "verification_scope=real_env_partial" in manifest
    assert "panos_version_reported=11.0.2" in manifest
    assert "panos_version_source=auto_detected" in manifest
    assert "scenario=deny-hit" in manifest
    assert "capture_label=deny-hit" in manifest

    keygen_request = (capture_dir / "api_keygen_request.txt").read_text(encoding="utf-8")
    keygen_response = (capture_dir / "api_keygen_response.xml").read_text(encoding="utf-8")
    assert "super-secret-password" not in keygen_request
    assert "REAL_KEY_123" not in keygen_request
    assert "REAL_KEY_123" not in keygen_response
    assert "/api/?type=keygen" in keygen_request
    assert "form-urlencoded user,password" in keygen_request
    assert "REDACTED_API_KEY" in keygen_response


def test_gather_script_keygen_post_fallback_is_supported(tmp_path: Path) -> None:
    fake_bin = tmp_path / "fake_bin"
    _write_fake_curl_keygen_post_only(fake_bin)
    out_root = tmp_path / "fixtures"
    env = dict(os.environ)
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"

    subprocess.run(
        [
            str(GATHER_SCRIPT),
            "--host",
            "10.0.0.1",
            "--username",
            "admin",
            "--password",
            "super-secret-password",
            "--rule-xpath",
            "/config/devices/entry/vsys/entry/rulebase/security/rules",
            "--capture-label",
            "query-shape",
            "--out-root",
            str(out_root),
        ],
        cwd=REPO_ROOT,
        env=env,
        check=True,
    )


def test_gather_script_fails_fast_with_auth_guidance_on_invalid_credential(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "fake_bin"
    _write_fake_curl_keygen_invalid_credential(fake_bin)
    out_root = tmp_path / "fixtures"
    env = dict(os.environ)
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"

    proc = subprocess.run(
        [
            str(GATHER_SCRIPT),
            "--host",
            "10.0.0.1",
            "--username",
            "admin",
            "--password",
            "super-secret-password",
            "--rule-xpath",
            "/config/devices/entry/vsys/entry/rulebase/security/rules",
            "--capture-label",
            "deny-hit",
            "--out-root",
            str(out_root),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode != 0
    assert "returned 403 Invalid Credential" in proc.stderr
    assert "known-good API key" in proc.stderr
    assert "XML API access enabled" in proc.stderr
    assert "Do not retry live capture" in proc.stderr
    assert "super-secret-password" not in proc.stderr


def test_gather_script_non_auth_keygen_xml_error_stays_generic(
    tmp_path: Path,
) -> None:
    fake_bin = tmp_path / "fake_bin"
    _write_fake_curl_keygen_non_auth_error(fake_bin)
    out_root = tmp_path / "fixtures"
    env = dict(os.environ)
    env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"

    proc = subprocess.run(
        [
            str(GATHER_SCRIPT),
            "--host",
            "10.0.0.1",
            "--username",
            "admin",
            "--password",
            "super-secret-password",
            "--rule-xpath",
            "/config/devices/entry/vsys/entry/rulebase/security/rules",
            "--capture-label",
            "deny-hit",
            "--out-root",
            str(out_root),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode != 0
    assert "did not contain <key>" in proc.stderr
    assert "known-good API key" not in proc.stderr
    assert "authentication/authorization" not in proc.stderr
    assert "super-secret-password" not in proc.stderr
