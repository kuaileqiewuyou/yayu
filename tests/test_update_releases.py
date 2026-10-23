import hashlib
from http.client import IncompleteRead
import io
import json
from dataclasses import FrozenInstanceError, replace
from email.message import Message
from urllib.error import HTTPError, URLError

import pytest

from core.updates import releases
from core.updates.releases import GitHubReleaseClient, UpdateError, UpdateInfo


PAYLOAD = b"a fake zip downloaded entirely in a test"
FAKE_TOKEN = "test-only-value-not-a-real-token"
VERSION = "1.0.4"
TAG = "v" + VERSION
NAME = f"Yayu-{VERSION}-windows-x64.zip"
API = "https://api.github.com/repos/kuaileqiewuyou/yayu/releases/assets/123"
DOWNLOAD = f"https://github.com/kuaileqiewuyou/yayu/releases/download/{TAG}/{NAME}"
PAGE = f"https://github.com/kuaileqiewuyou/yayu/releases/tag/{TAG}"


class Response(io.BytesIO):
    status = 200

    def __init__(self, body, url, headers=None):
        super().__init__(body)
        self.url = url
        self.headers = headers or {}

    def geturl(self):
        return self.url


class Opener:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        assert 0 < timeout <= releases.REQUEST_TIMEOUT
        reply = next(self.replies)
        if isinstance(reply, Exception):
            raise reply
        return reply


def asset(name=NAME, asset_id=123, body=PAYLOAD):
    return {
        "name": name, "state": "uploaded", "size": len(body),
        "url": f"https://api.github.com/repos/kuaileqiewuyou/yayu/releases/assets/{asset_id}",
        "browser_download_url": f"https://github.com/kuaileqiewuyou/yayu/releases/download/{TAG}/{name}",
        "digest": "sha256:" + hashlib.sha256(body).hexdigest(),
    }


def release():
    return {"draft": False, "prerelease": False, "tag_name": TAG,
            "html_url": PAGE, "body": "修复更新并保留用户资料。", "assets": [asset()]}


def client_for_release(data):
    client = GitHubReleaseClient(FAKE_TOKEN)
    client._opener = Opener([Response(json.dumps(data).encode(), releases.RELEASES_URL)])
    return client


def info():
    return UpdateInfo(VERSION, TAG, PAGE, "test", NAME, API, DOWNLOAD,
                      len(PAYLOAD), hashlib.sha256(PAYLOAD).hexdigest())


def redirect(url, new_url):
    headers = Message()
    headers["Location"] = new_url
    return HTTPError(url, 302, "redirect", headers, io.BytesIO())


def test_check_uses_fixed_repository_and_returns_frozen_numeric_new_version():
    client = client_for_release(release())
    found = client.check("1.0.3")
    assert found.version == VERSION
    assert found.asset_name == NAME
    assert found.sha256 == hashlib.sha256(PAYLOAD).hexdigest()
    assert found.notes.startswith("修复")
    with pytest.raises(FrozenInstanceError):
        found.version = "9.0.0"
    request = client._opener.requests[0]
    assert request.full_url == releases.RELEASES_URL
    assert request.get_header("Authorization") == "Bearer " + FAKE_TOKEN
    assert request.get_header("Accept") == "application/vnd.github+json"


@pytest.mark.parametrize("current", ["1.0.4", "1.0.10", "2.0.0"])
def test_same_or_lower_release_is_not_offered(current):
    assert client_for_release(release()).check(current) is None


def test_version_uses_numeric_components_not_lexical_order():
    data = release()
    data.update(tag_name="v1.0.10", html_url=PAGE.replace("v1.0.4", "v1.0.10"))
    for entry in data["assets"]:
        entry["name"] = entry["name"].replace("1.0.4", "1.0.10")
        entry["browser_download_url"] = entry["browser_download_url"].replace("1.0.4", "1.0.10")
    assert client_for_release(data).check("1.0.9").version == "1.0.10"


@pytest.mark.parametrize("version", ["1.2", "1.2.3-beta", "1.2.3+build", "01.2.3", "1.02.3", "1.2.03", "-1.2.3", " 1.2.3", None])
def test_non_stable_or_invalid_version_rejected(version):
    data = release()
    data["tag_name"] = version
    with pytest.raises(UpdateError, match="版本号"):
        client_for_release(data).check("1.0.3")


@pytest.mark.parametrize("field", ["draft", "prerelease"])
def test_unpublished_or_prerelease_never_installed(field):
    data = release()
    data[field] = True
    with pytest.raises(UpdateError, match="稳定正式版本"):
        client_for_release(data).check("1.0.3")


@pytest.mark.parametrize("changes", [
    {"html_url": PAGE.replace("kuaileqiewuyou", "someone")},
    {"assets": []},
    {"assets": [asset(), asset()]},
    {"assets": [dict(asset(), name="windows.zip")]},
    {"assets": [dict(asset(), state="new")]},
    {"assets": [dict(asset(), size=True)]},
    {"assets": [dict(asset(), size=0)]},
    {"assets": [dict(asset(), size=releases.MAX_DOWNLOAD_BYTES + 1)]},
    {"assets": [dict(asset(), url=API.replace("yayu", "another-repo"))]},
    {"assets": [dict(asset(), browser_download_url=DOWNLOAD.replace(TAG, "v1.0.1"))]},
    {"assets": [dict(asset(), digest="sha256:not-a-digest")]},
])
def test_missing_or_untrusted_release_information_rejected(changes):
    data = release()
    data.update(changes)
    with pytest.raises(UpdateError):
        client_for_release(data).check("1.0.3")


def test_checksum_file_used_from_same_release_when_asset_has_no_digest():
    data = release()
    data["assets"][0].pop("digest")
    text = f"{hashlib.sha256(PAYLOAD).hexdigest()}  {NAME}\n".encode()
    checksum = asset("SHA256SUMS.txt", 124, text)
    data["assets"].append(checksum)
    client = client_for_release(data)
    client._opener = Opener([
        Response(json.dumps(data).encode(), releases.RELEASES_URL),
        Response(text, checksum["url"]),
    ])
    assert client.check("1.0.3").sha256 == hashlib.sha256(PAYLOAD).hexdigest()
    assert client._opener.requests[1].get_header("Accept") == "application/octet-stream"


@pytest.mark.parametrize("checksum_text", [
    b"not a checksum", ("0" * 64 + "  a-different.zip\n").encode(),
    (("0" * 64 + f"  {NAME}\n") * 2).encode(),
])
def test_missing_or_ambiguous_checksum_rejected(checksum_text):
    data = release()
    data["assets"][0].pop("digest")
    checksum = asset("SHA256SUMS.txt", 124, checksum_text)
    data["assets"].append(checksum)
    client = client_for_release(data)
    client._opener = Opener([
        Response(json.dumps(data).encode(), releases.RELEASES_URL),
        Response(checksum_text, checksum["url"]),
    ])
    with pytest.raises(UpdateError, match="校验"):
        client.check("1.0.3")


def test_missing_digest_and_checksum_fail_closed():
    data = release()
    data["assets"][0].pop("digest")
    with pytest.raises(UpdateError, match="缺少 SHA-256"):
        client_for_release(data).check("1.0.3")


def test_download_stream_verifies_and_atomically_replaces_file(tmp_path):
    client = GitHubReleaseClient(FAKE_TOKEN)
    client._opener = Opener([Response(PAYLOAD, API, {"Content-Length": str(len(PAYLOAD))})])
    destination = tmp_path / NAME
    destination.write_bytes(b"old cached download")
    progress = []
    assert client.download(info(), destination, progress=lambda *values: progress.append(values)) == destination
    assert destination.read_bytes() == PAYLOAD
    assert progress == [(0, len(PAYLOAD)), (len(PAYLOAD), len(PAYLOAD))]
    assert list(tmp_path.glob("*.part")) == []
    assert client._opener.requests[0].get_header("Accept") == "application/octet-stream"


@pytest.mark.parametrize("body,headers", [
    (b"short", {}), (PAYLOAD + b"extra", {}),
    (PAYLOAD[::-1], {}), (PAYLOAD, {"Content-Length": "1"}),
    (PAYLOAD, {"Content-Length": str(releases.MAX_DOWNLOAD_BYTES + 1)}),
    (PAYLOAD, {"Content-Length": "garbage"}),
])
def test_failed_download_leaves_existing_file_and_removes_part(tmp_path, body, headers):
    client = GitHubReleaseClient()
    client._opener = Opener([Response(body, API, headers)])
    destination = tmp_path / NAME
    destination.write_bytes(b"original")
    with pytest.raises(UpdateError):
        client.download(info(), destination)
    assert destination.read_bytes() == b"original"
    assert list(tmp_path.glob("*.part")) == []


def test_download_cancellation_removes_partial_file_and_keeps_old_download(tmp_path):
    client = GitHubReleaseClient()
    client._opener = Opener([Response(PAYLOAD, API)])
    destination = tmp_path / NAME
    destination.write_bytes(b"original")
    state = {"cancelled": False}

    def progress(received, total):
        state["cancelled"] = received > 0

    with pytest.raises(UpdateError, match="取消"):
        client.download(info(), destination, progress, lambda: state["cancelled"])
    assert destination.read_bytes() == b"original"
    assert list(tmp_path.glob("*.part")) == []


@pytest.mark.parametrize("url", [
    "https://evil.example/payload.zip", "http://github.com/kuaileqiewuyou/yayu/releases/download/x.zip",
    "https://github.com.evil.example/x.zip", "https://api.github.com/repos/other/repo/releases/assets/1",
    "https://user:password@api.github.com/repos/kuaileqiewuyou/yayu/releases/assets/1",
    "https://release-assets.githubusercontent.com:444/a.zip", "file:///C:/a.zip",
    "https://release-assets.githubusercontent.com/a.zip#fragment",
])
def test_redirects_to_untrusted_destinations_are_blocked_before_request(url, tmp_path):
    client = GitHubReleaseClient(FAKE_TOKEN)
    client._opener = Opener([redirect(API, url)])
    with pytest.raises(UpdateError):
        client.download(info(), tmp_path / NAME)
    assert len(client._opener.requests) == 1


def test_cross_domain_redirect_never_receives_authorization_even_if_returning_to_api(tmp_path):
    cdn = "https://release-assets.githubusercontent.com/github-production-release-asset/file?signature=test"
    client = GitHubReleaseClient(FAKE_TOKEN)
    client._opener = Opener([redirect(API, cdn), redirect(cdn, API), Response(PAYLOAD, API)])
    client.download(info(), tmp_path / NAME)
    assert client._opener.requests[0].get_header("Authorization") == "Bearer " + FAKE_TOKEN
    assert client._opener.requests[1].get_header("Authorization") is None
    assert client._opener.requests[2].get_header("Authorization") is None


@pytest.mark.parametrize("code,headers,match", [
    (401, {}, "授权无效"), (403, {}, "读取权限"),
    (403, {"X-RateLimit-Remaining": "0"}, "次数已达限制"),
    (429, {}, "次数已达限制"), (404, {}, "私有"), (500, {}, "HTTP 500"),
])
def test_http_errors_are_specific_and_do_not_expose_remote_body_or_token(code, headers, match):
    error = HTTPError(releases.RELEASES_URL, code, FAKE_TOKEN, headers, io.BytesIO(FAKE_TOKEN.encode()))
    client = GitHubReleaseClient(FAKE_TOKEN)
    client._opener = Opener([error])
    with pytest.raises(UpdateError, match=match) as caught:
        client.check("1.0.3")
    assert FAKE_TOKEN not in str(caught.value)


def test_network_exception_messages_are_never_exposed():
    client = GitHubReleaseClient(FAKE_TOKEN)
    client._opener = Opener([URLError(FAKE_TOKEN)])
    with pytest.raises(UpdateError, match="无法连接") as caught:
        client.check("1.0.3")
    assert FAKE_TOKEN not in str(caught.value)


@pytest.mark.parametrize("token", ["bad\nheader", "two words", "中文", "a" * 4097])
def test_header_injection_or_invalid_tokens_rejected(token):
    with pytest.raises(UpdateError, match="令牌格式"):
        GitHubReleaseClient(token)


def test_large_metadata_rejected_before_json_decode():
    client = GitHubReleaseClient()
    client._opener = Opener([Response(b"", releases.RELEASES_URL, {"Content-Length": str(releases.MAX_METADATA_BYTES + 1)})])
    with pytest.raises(UpdateError, match="大小"):
        client.check("1.0.3")


def test_download_revalidates_caller_supplied_info(tmp_path):
    client = GitHubReleaseClient()
    client._opener = Opener([])
    for changed in [replace(info(), version="1.0.5"), replace(info(), sha256=""),
                    replace(info(), asset_api_url="https://evil.example/a.zip")]:
        with pytest.raises(UpdateError):
            client.download(changed, tmp_path / NAME)
    assert client._opener.requests == []


def test_socket_disconnect_during_read_becomes_safe_update_error(tmp_path):
    class BrokenResponse(Response):
        def read(self, size):
            raise IncompleteRead(FAKE_TOKEN.encode(), 100)

    client = GitHubReleaseClient()
    client._opener = Opener([BrokenResponse(PAYLOAD, API)])
    with pytest.raises(UpdateError, match="下载或保存") as caught:
        client.download(info(), tmp_path / NAME)
    assert FAKE_TOKEN not in str(caught.value)
    assert list(tmp_path.iterdir()) == []


def test_deadline_and_initial_cancellation_stop_before_network(tmp_path, monkeypatch):
    client = GitHubReleaseClient()
    client._opener = Opener([])
    with pytest.raises(UpdateError, match="取消"):
        client.download(info(), tmp_path / NAME, cancelled=lambda: True)
    monkeypatch.setattr(releases, "DOWNLOAD_TIMEOUT", -1)
    with pytest.raises(UpdateError, match="超时"):
        client.download(info(), tmp_path / NAME)
    assert client._opener.requests == []


def test_default_urllib_redirect_handler_is_disabled():
    handler = releases._NoRedirect()
    assert handler.redirect_request(None, None, 302, "redirect", {}, "https://evil.example") is None
