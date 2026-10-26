import pytest

from .test_helpers import DummyContext

# What Unity replies with a compile requested: it answers the moment compilation starts,
# before the domain reload, so its own snapshot is "compiling" with a hint to poll.
UNITY_REPLY_AT_COMPILE_START = {
    "success": True,
    "message": "Refresh requested.",
    "data": {
        "refresh_triggered": True,
        "compile_requested": True,
        "compile_started": True,
        "resulting_state": "compiling",
        "hint": "If Unity enters compilation/domain reload, poll the mcpforunity://editor/state resource until data.advice.ready_for_tools is true.",
    },
}


def _patch_transport(monkeypatch):
    async def fake_send_with_unity_instance(send_fn, unity_instance, command_type, params, **kwargs):
        if command_type == "refresh_unity":
            return UNITY_REPLY_AT_COMPILE_START
        if command_type == "get_editor_state":
            return {"success": True, "data": {"advice": {"ready_for_tools": True}}}
        raise ValueError(f"Unexpected command: {command_type}")

    import services.tools.refresh_unity as refresh_mod
    monkeypatch.setattr(refresh_mod.unity_transport, "send_with_unity_instance", fake_send_with_unity_instance)


@pytest.mark.asyncio
async def test_refresh_unity_reports_ready_after_waiting(monkeypatch):
    """After the server-side wait confirms readiness, the reply must not repeat Unity's
    compile-start snapshot: agents read "compiling" plus "poll until ready" as a refresh
    that hasn't finished and slept or polled on top of a wait that already happened."""
    from services.tools.refresh_unity import refresh_unity

    ctx = DummyContext()
    await ctx.set_state("unity_instance", "UnityMCPTests@cc8756d4cce0805a")
    _patch_transport(monkeypatch)

    resp = await refresh_unity(ctx, compile="request", wait_for_ready=True)
    payload = resp.model_dump() if hasattr(resp, "model_dump") else resp
    data = payload["data"]

    assert payload["success"] is True
    assert data["resulting_state"] == "idle"
    assert data["ready_confirmed"] is True
    assert data["unity_state_at_reply"] == "compiling"
    assert "poll" not in payload["message"].lower()
    assert "No need to poll" in data["hint"]
    # Unity's facts about the refresh itself are kept
    assert data["compile_started"] is True and data["refresh_triggered"] is True


@pytest.mark.asyncio
async def test_refresh_unity_without_wait_keeps_unity_reply(monkeypatch):
    """With wait_for_ready=false nothing waited, so Unity's snapshot and its hint to poll are right."""
    from services.tools.refresh_unity import refresh_unity

    ctx = DummyContext()
    await ctx.set_state("unity_instance", "UnityMCPTests@cc8756d4cce0805a")
    _patch_transport(monkeypatch)

    resp = await refresh_unity(ctx, compile="request", wait_for_ready=False)
    payload = resp.model_dump() if hasattr(resp, "model_dump") else resp

    assert payload["data"]["resulting_state"] == "compiling"
    assert "ready_confirmed" not in payload["data"]
    assert "poll" in payload["data"]["hint"]
