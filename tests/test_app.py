import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from cardbox import app
from cardbox.localguard import host_ok, origin_ok

SCRIPT = "Hook line here.\n\n# 8.8% of the music\nOnly a little came from the servers.\n\nBye now."


@pytest.fixture()
def server(workspace):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv.server_address[1]
    srv.shutdown()


def call(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    h = {"Host": f"127.0.0.1:{port}", **(headers or {})}
    c.request(method, path, body=body, headers=h)
    r = c.getresponse()
    data = r.read()
    c.close()
    try:
        return r.status, json.loads(data)
    except ValueError:
        return r.status, data


def test_app_page_and_state(server):
    status, page = call(server, "GET", "/")
    assert status == 200 and b"cardbox" in page
    status, state = call(server, "GET", "/api/state")
    assert status == 200 and {f["name"] for f in state["options"]["formats"]} == {"vertical", "landscape", "square"}


def test_save_plain_text_writes_spec(server, workspace):
    body = json.dumps({"title": "Test", "script": SCRIPT, "options": {"format": "square", "voice": "none"}})
    status, info = call(server, "POST", "/api/reels/my-video", body, {"Content-Type": "application/json"})
    assert status == 200, info
    assert [b["kind"] for b in info["beats"]] == ["hook", "stat", "end"]
    assert (workspace / "reels" / "my-video" / "script.txt").read_text() == SCRIPT
    assert "format: square" in info["yaml"]


def test_bad_script_is_a_clear_error(server):
    status, info = call(server, "POST", "/api/reels/x", json.dumps({"script": "one paragraph"}))
    assert status == 400 and "two paragraphs" in info["error"]


def test_media_upload_and_delete(server):
    status, info = call(server, "POST", "/api/reels/v/media?file=My%20Photo!.jpg", b"fakejpeg")
    assert status == 200 and info["name"] == "My-Photo.jpg"
    status, info = call(server, "DELETE", "/api/reels/v/media/My-Photo.jpg")
    assert info["media"] == []


def test_media_rejects_other_file_types(server):
    status, info = call(server, "POST", "/api/reels/v/media?file=run.sh", b"#!/bin/sh")
    assert status == 400


def test_files_cannot_escape_the_video_folder(server):
    call(server, "POST", "/api/reels/v/media?file=a.jpg", b"x")
    status, _ = call(server, "GET", "/files/v/..%2F..%2F..%2Fetc%2Fpasswd")
    assert status == 404


def test_guard_rejects_rebinding_and_cross_site(server):
    status, _ = call(server, "GET", "/api/state", headers={"Host": "evil.example:80"})
    assert status == 403
    status, _ = call(server, "DELETE", "/api/reels/v", headers={"Origin": "https://evil.example"})
    assert status == 403
    status, _ = call(server, "POST", "/api/reels/v/media?file=a.jpg", b"x", headers={"Origin": f"http://127.0.0.1:{server}"})
    assert status == 200


@pytest.mark.parametrize("host,ok", [("127.0.0.1:8740", True), ("localhost", True), ("[::1]:8740", True),
                                     ("evil.example", False), ("127.0.0.1.evil.example", False), (None, False)])
def test_host_ok(host, ok):
    assert host_ok(host) is ok


def test_origin_ok():
    assert origin_ok(None, "127.0.0.1:1") and origin_ok("http://127.0.0.1:1", "127.0.0.1:1")
    assert not origin_ok("http://127.0.0.1:2", "127.0.0.1:1") and not origin_ok("null", "127.0.0.1:1")
