import asyncio

from cardbox import mcp_server

GOOD = """
title: Test reel
voice: none
beats:
  - {kind: hook, text: Hello, say: Hello there.}
  - {kind: scene, scene: counter, say: It counts to ten., params: {to: 10, on: ten}}
  - {kind: end, text: Bye, say: Bye now.}
"""


def test_tools_are_registered():
    names = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
    assert {"guide", "create_reel", "preview_beat", "render_reel", "search_images", "add_image",
            "voice_status", "voice_record"} <= names


def test_create_reel_saves_a_valid_spec(workspace):
    msg = mcp_server.create_reel("My Test", GOOD)
    assert "Saved reel 'my-test'" in msg
    assert (workspace / "reels" / "my-test" / "reel.yaml").exists()
    assert "counter" in mcp_server.get_reel("my-test")


def test_create_reel_explains_errors():
    msg = mcp_server.create_reel("bad", "title: x\nbeats: [{kind: hook, say: hi}]")
    assert "problems" in msg and "text" in msg


def test_create_reel_rejects_unknown_scenes():
    msg = mcp_server.create_reel("bad", "title: x\nbeats: [{kind: scene, scene: rocket, say: hi}]")
    assert "Unknown scene" in msg


def test_guide_lists_every_scene():
    g = mcp_server.guide()
    for name in ("photo", "donut", "counter", "bars", "mesh", "terminal", "flow", "grid"):
        assert f"- {name}:" in g
