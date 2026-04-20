"""End-to-end test of the ICES MCP server over JSON-RPC stdio.

Spawns `ices_mcp_server.py` in a subprocess, sends JSON-RPC init +
tools/list + tools/call requests, and asserts the migratory-fish tools
are registered and respond correctly.

This mimics what Claude Desktop / Copilot CLI would do when talking to
the server.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_ICES_MCP = _HERE.parent
_SERVER_PY = _ICES_MCP / "ices_mcp_server.py"


def _has_internet() -> bool:
    try:
        socket.create_connection(("api.figshare.com", 443), timeout=3).close()
        return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def mcp_proc():
    """Launch the MCP server subprocess and yield the Popen handle."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_ICES_MCP) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONUNBUFFERED"] = "1"
    p = subprocess.Popen(
        [sys.executable, str(_SERVER_PY)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=False,  # binary; we'll encode ourselves
        bufsize=0,
    )
    # Give the server a moment to register tools
    time.sleep(2.0)
    assert p.poll() is None, (
        "server exited early; stderr:\n" + (p.stderr.read() or b"").decode("utf-8", errors="replace")
    )
    yield p
    try:
        p.terminate()
        p.wait(timeout=5)
    except subprocess.TimeoutExpired:
        p.kill()


def _rpc(p: subprocess.Popen, method: str, params: dict | None = None, id_: int = 1) -> dict:
    """Send a JSON-RPC 2.0 request and read exactly one framed response."""
    msg = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        msg["params"] = params
    payload = (json.dumps(msg) + "\n").encode("utf-8")
    p.stdin.write(payload)
    p.stdin.flush()

    # Read one line of response (FastMCP stdio uses LSP-style line-delimited JSON)
    deadline = time.time() + 15
    while time.time() < deadline:
        line = p.stdout.readline()
        if not line:
            time.sleep(0.05)
            continue
        try:
            return json.loads(line.decode("utf-8"))
        except json.JSONDecodeError:
            continue
    raise TimeoutError(f"no response to {method} within 15s")


def _initialize(p) -> dict:
    return _rpc(p, "initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "pytest", "version": "0.1"},
    })


class TestMcpProtocol:
    """Verify the server speaks MCP correctly and exposes our tools."""

    def test_server_starts(self, mcp_proc):
        assert mcp_proc.poll() is None

    def test_initialize_succeeds(self, mcp_proc):
        resp = _initialize(mcp_proc)
        assert resp.get("result") or "error" not in resp
        # Fire the notifications/initialized notification as MCP requires
        note = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        mcp_proc.stdin.write((json.dumps(note) + "\n").encode("utf-8"))
        mcp_proc.stdin.flush()

    def test_tools_list_contains_migratory_tools(self, mcp_proc):
        # re-initialize each time — separate test runs might have closed
        _initialize(mcp_proc)
        resp = _rpc(mcp_proc, "tools/list", {}, id_=2)
        assert "result" in resp, resp
        tools = resp["result"]["tools"]
        names = {t["name"] for t in tools}
        # The 8 new migratory tools plus smelt/shad profiles
        for expected in [
            "migratory_list_working_groups",
            "migratory_latest_wg_report",
            "ices_library_search",
            "ices_library_get_article",
            "ices_list_ecoregions",
            "ices_ecosystem_overview",
            "migratory_species_catalog",
            "migratory_aphia_map",
            "smelt_profile",
            "shad_profile",
        ]:
            assert expected in names, f"{expected} missing; got {sorted(names)}"
        # And the full server has 30+ tools total (the baseline + our additions)
        assert len(tools) >= 25

    def test_call_migratory_species_catalog(self, mcp_proc):
        _initialize(mcp_proc)
        resp = _rpc(mcp_proc, "tools/call", {
            "name": "migratory_species_catalog",
            "arguments": {"habitat": ""},
        }, id_=3)
        assert "result" in resp, resp
        content = resp["result"]["content"]
        # FastMCP returns a list of content blocks; parse the first text block
        text = content[0]["text"]
        payload = json.loads(text)
        assert "species" in payload
        assert len(payload["species"]) == 13
        common_names = {s["common"] for s in payload["species"]}
        assert "European smelt" in common_names
        assert "Twaite shad" in common_names

    def test_call_migratory_aphia_map(self, mcp_proc):
        _initialize(mcp_proc)
        resp = _rpc(mcp_proc, "tools/call", {
            "name": "migratory_aphia_map",
            "arguments": {},
        }, id_=4)
        text = resp["result"]["content"][0]["text"]
        m = json.loads(text)
        # Fixed Aphia IDs from WoRMS verification
        assert m["Osmerus eperlanus"] == 126736
        assert m["Alosa fallax"] == 126415
        assert m["Salmo salar"] == 127186

    def test_call_smelt_profile_offline(self, mcp_proc):
        """smelt_profile with include_library_search=False should return
        static reference without hitting the network."""
        _initialize(mcp_proc)
        resp = _rpc(mcp_proc, "tools/call", {
            "name": "smelt_profile",
            "arguments": {"include_library_search": False},
        }, id_=5)
        text = resp["result"]["content"][0]["text"]
        profile = json.loads(text)
        assert profile["aphia_id"] == 126736
        assert profile["scientific_name"] == "Osmerus eperlanus"
        assert "recent_publications" not in profile

    def test_call_shad_profile_offline(self, mcp_proc):
        _initialize(mcp_proc)
        resp = _rpc(mcp_proc, "tools/call", {
            "name": "shad_profile",
            "arguments": {"include_library_search": False},
        }, id_=6)
        text = resp["result"]["content"][0]["text"]
        profile = json.loads(text)
        assert profile["twaite_shad"]["aphia_id"] == 126415
        assert profile["allis_shad"]["aphia_id"] == 126413

    @pytest.mark.skipif(not _has_internet(), reason="no network")
    def test_call_latest_wg_report_wgbast(self, mcp_proc):
        _initialize(mcp_proc)
        resp = _rpc(mcp_proc, "tools/call", {
            "name": "migratory_latest_wg_report",
            "arguments": {"wg_acronym": "WGBAST"},
        }, id_=7)
        text = resp["result"]["content"][0]["text"]
        data = json.loads(text)
        assert data["wg"] == "WGBAST"
        # Should have either 'latest' (if hits) or 'results' (if fallback)
        assert "latest" in data or "results" in data
