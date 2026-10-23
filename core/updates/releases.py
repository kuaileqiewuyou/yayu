"""Read and download stable Yayu releases without sending local application data.

Only the fixed repository is an update source. Downloads are authenticated at
the GitHub API, and credentials are never forwarded to a CDN redirect.
"""

from __future__ import annotations

import hashlib
from http.client import HTTPException
import json
import os
from pathlib import Path
import re
import time
from dataclasses import dataclass
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4


REPOSITORY = "kuaileqiewuyou/yayu"
RELEASES_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
MAX_DOWNLOAD_BYTES = 1024 * 1024 * 1024
MAX_METADATA_BYTES = 2 * 1024 * 1024
MAX_CHECKSUM_BYTES = 256 * 1024
REQUEST_TIMEOUT = 30
DOWNLOAD_TIMEOUT = 30 * 60
_API_PREFIX = f"/repos/{REPOSITORY}/releases/"
_WEB_PREFIX = f"/{REPOSITORY}/releases/"
_CDN_HOSTS = frozenset({
    "release-assets.githubusercontent.com",
    "objects.githubusercontent.com",
    "github-releases.githubusercontent.com",
})
_VERSION = re.compile(r"v?((?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*))\Z")
_SHA256 = re.compile(r"[a-fA-F0-9]{64}\Z")


class UpdateError(Exception):
    """An update could not be completed; the message is safe to show in the UI."""


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    tag: str
    page_url: str
    notes: str
    asset_name: str
    asset_api_url: str
    asset_download_url: str
    size: int
    sha256: str


def _version(value: str) -> tuple[str, tuple[int, int, int]]:
    match = _VERSION.fullmatch(value) if isinstance(value, str) and len(value) <= 128 else None
    if match is None:
        raise UpdateError("版本号格式不正确，仅支持正式版本（例如 1.0.4）。")
    normal = match.group(1)
    return normal, tuple(int(part) for part in normal.split("."))


def _trusted_url(url: str) -> str:
    """Return the host after validating the transport destination."""
    if not isinstance(url, str) or "\\" in url or any(ord(c) <= 32 for c in url):
        raise UpdateError("更新地址不安全，已停止连接。")
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        raise UpdateError("更新地址不安全，已停止连接。") from None
    if (parsed.scheme != "https" or parsed.username is not None
            or parsed.password is not None or port not in (None, 443)
            or parsed.fragment or not host):
        raise UpdateError("更新地址不安全，已停止连接。")
    if host == "api.github.com":
        if not parsed.path.startswith(_API_PREFIX) or parsed.query:
            raise UpdateError("更新来源与芽语仓库不匹配。")
        suffix = parsed.path[len(_API_PREFIX):]
        if suffix != "latest" and re.fullmatch(r"(?:[0-9]+|assets/[0-9]+)", suffix) is None:
            raise UpdateError("更新来源与芽语仓库不匹配。")
    elif host == "github.com":
        if not parsed.path.startswith(_WEB_PREFIX) or parsed.query:
            raise UpdateError("更新来源与芽语仓库不匹配。")
    elif host not in _CDN_HOSTS:
        raise UpdateError("更新地址不属于受信任的 GitHub 下载服务。")
    return host


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GitHubReleaseClient:
    def __init__(self, token: str | None = None):
        token = token.strip() if isinstance(token, str) else None
        if token and (len(token) > 4096 or not token.isascii()
                      or any(c.isspace() or ord(c) < 33 for c in token)):
            raise UpdateError("GitHub 访问令牌格式不正确，请重新输入。")
        self._token = token or None
        self._opener = build_opener(_NoRedirect())

    @staticmethod
    def _check_cancelled(cancelled, deadline):
        if cancelled is not None and cancelled():
            raise UpdateError("已取消下载。")
        if time.monotonic() > deadline:
            raise UpdateError("连接更新服务超时，请稍后重试。")

    @staticmethod
    def _http_error(error: HTTPError) -> UpdateError:
        headers = error.headers or {}
        if error.code == 401:
            return UpdateError("GitHub 授权无效或已过期，请重新设置访问令牌。")
        if error.code == 429 or (error.code == 403 and (
                headers.get("X-RateLimit-Remaining") == "0" or headers.get("Retry-After"))):
            return UpdateError("GitHub 请求次数已达限制，请稍后再检查更新。")
        if error.code == 403:
            return UpdateError("GitHub 拒绝访问，请确认令牌具有该仓库的 Contents 读取权限；也可能触发了访问频率限制。")
        if error.code == 404:
            return UpdateError("无法访问更新仓库或发布资源。仓库可能为私有，请设置有仓库读取权限的 GitHub 令牌。")
        return UpdateError(f"GitHub 更新服务暂时不可用（HTTP {error.code}），请稍后重试。")

    def _open(self, url: str, accept: str, deadline: float, cancelled=None):
        # urllib's default redirect handler can retain Authorization. Follow each
        # redirect explicitly and permanently drop credentials on a host change.
        initial_host = _trusted_url(url)
        authenticated = initial_host == "api.github.com"
        for _ in range(6):
            self._check_cancelled(cancelled, deadline)
            host = _trusted_url(url)
            headers = {
                "Accept": accept,
                "Accept-Encoding": "identity",
                "User-Agent": "Yayu-Updater",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            if authenticated and host == "api.github.com" and self._token:
                headers["Authorization"] = f"Bearer {self._token}"
            request = Request(url, headers=headers, method="GET")
            try:
                response = self._opener.open(
                    request, timeout=min(REQUEST_TIMEOUT, max(0.1, deadline - time.monotonic()))
                )
            except HTTPError as error:
                try:
                    if error.code in (301, 302, 303, 307, 308):
                        location = error.headers.get("Location") if error.headers else None
                        if not location:
                            raise UpdateError("GitHub 返回了无效的下载跳转地址。")
                        redirected = urljoin(url, location)
                        new_host = _trusted_url(redirected)
                        authenticated = authenticated and new_host == host
                        url = redirected
                        continue
                    raise self._http_error(error) from None
                finally:
                    error.close()
            except (OSError, URLError, TimeoutError, HTTPException):
                # Never interpolate network exceptions: signed URLs and auth
                # details must not reach dialogs or logs.
                raise UpdateError("无法连接 GitHub 更新服务，请检查网络后重试。") from None
            try:
                final_host = _trusted_url(response.geturl())
                if final_host != host or getattr(response, "status", 200) != 200:
                    raise UpdateError("GitHub 更新服务返回了异常响应。")
            except BaseException:
                response.close()
                raise
            return response
        raise UpdateError("GitHub 下载跳转次数过多，已停止连接。")

    @staticmethod
    def _content_length(response, limit: int) -> int | None:
        length = response.headers.get("Content-Length")
        if length is None:
            return None
        try:
            length = int(length)
        except (TypeError, ValueError):
            raise UpdateError("更新服务返回的文件长度无效。") from None
        if length < 0 or length > limit:
            raise UpdateError("更新文件超过允许的大小，已停止下载。")
        return length

    def _read_small(self, url: str, limit: int, accept: str) -> bytes:
        deadline = time.monotonic() + 120
        with self._open(url, accept, deadline) as response:
            self._content_length(response, limit)
            chunks = []
            size = 0
            while True:
                self._check_cancelled(None, deadline)
                try:
                    chunk = response.read(min(64 * 1024, limit + 1 - size))
                except (OSError, URLError, TimeoutError, HTTPException):
                    raise UpdateError("读取 GitHub 更新信息失败，请重试。") from None
                if not chunk:
                    return b"".join(chunks)
                size += len(chunk)
                if size > limit:
                    raise UpdateError("GitHub 返回的更新信息过大，已停止读取。")
                chunks.append(chunk)

    @staticmethod
    def _validate_asset(asset: dict, tag: str, name: str, limit: int):
        if not isinstance(asset, dict) or asset.get("name") != name:
            raise UpdateError("发布包信息不完整，无法安全更新。")
        if asset.get("state") != "uploaded":
            raise UpdateError("更新发布包尚未上传完成，请稍后重试。")
        size = asset.get("size")
        if type(size) is not int or size <= 0 or size > limit:
            raise UpdateError("更新发布包大小无效，无法安全更新。")
        api_url = asset.get("url")
        browser_url = asset.get("browser_download_url")
        if _trusted_url(api_url) != "api.github.com" or re.fullmatch(
                rf"https://api\.github\.com{re.escape(_API_PREFIX)}assets/[0-9]+", api_url) is None:
            raise UpdateError("更新发布包来源与芽语仓库不匹配。")
        expected = f"https://github.com/{REPOSITORY}/releases/download/{quote(tag, safe='')}/{quote(name, safe='')}"
        if browser_url != expected:
            raise UpdateError("更新发布包地址与当前版本不匹配。")
        return api_url, browser_url, size

    def check(self, current_version: str) -> UpdateInfo | None:
        _, current = _version(current_version)
        raw = self._read_small(RELEASES_URL, MAX_METADATA_BYTES, "application/vnd.github+json")
        try:
            release = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError, RecursionError):
            raise UpdateError("GitHub 返回的版本信息无效，请稍后重试。") from None
        if not isinstance(release, dict):
            raise UpdateError("GitHub 返回的版本信息无效，请稍后重试。")
        if release.get("draft") is not False or release.get("prerelease") is not False:
            raise UpdateError("更新源未提供稳定正式版本，已停止更新。")
        tag = release.get("tag_name")
        version, latest = _version(tag)
        page_url = f"https://github.com/{REPOSITORY}/releases/tag/{quote(tag, safe='')}"
        if release.get("html_url") != page_url:
            raise UpdateError("更新来源与芽语仓库不匹配。")
        if latest <= current:
            return None
        name = f"Yayu-{version}-windows-x64.zip"
        assets = release.get("assets")
        if not isinstance(assets, list):
            raise UpdateError("该版本没有可安装的 Windows 发布包。")
        matching = [asset for asset in assets if isinstance(asset, dict) and asset.get("name") == name]
        if len(matching) != 1:
            raise UpdateError("该版本缺少唯一的 Windows 发布包，无法安全更新。")
        asset = matching[0]
        api_url, browser_url, size = self._validate_asset(asset, tag, name, MAX_DOWNLOAD_BYTES)
        digest = asset.get("digest")
        if digest:
            if not isinstance(digest, str) or not digest.startswith("sha256:") or not _SHA256.fullmatch(digest[7:]):
                raise UpdateError("更新发布包的 SHA-256 校验信息无效。")
            sha256 = digest[7:].lower()
        else:
            sha256 = self._checksum_from_release(assets, tag, name)
        notes = release.get("body") or ""
        if not isinstance(notes, str):
            raise UpdateError("GitHub 返回的更新说明无效。")
        return UpdateInfo(version, tag, page_url, notes, name, api_url, browser_url, size, sha256)

    def _checksum_from_release(self, assets: list, tag: str, name: str) -> str:
        checksums = [a for a in assets if isinstance(a, dict) and a.get("name") == "SHA256SUMS.txt"]
        if len(checksums) != 1:
            raise UpdateError("该版本缺少 SHA-256 校验信息，已停止更新。")
        api_url, _, declared_size = self._validate_asset(checksums[0], tag, "SHA256SUMS.txt", MAX_CHECKSUM_BYTES)
        raw = self._read_small(api_url, MAX_CHECKSUM_BYTES, "application/octet-stream")
        if len(raw) != declared_size:
            raise UpdateError("更新校验文件不完整，请重试。")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeError:
            raise UpdateError("更新校验文件格式无效。") from None
        found = []
        for line in text.splitlines():
            match = re.fullmatch(r"([a-fA-F0-9]{64})[ \t]+\*?(.+)", line)
            if match and match.group(2) == name:
                found.append(match.group(1).lower())
        if len(found) != 1:
            raise UpdateError("更新校验文件缺少唯一的 Windows 发布包校验值。")
        return found[0]

    def download(self, info: UpdateInfo, destination: Path, progress: Callable[[int, int], None] | None = None,
                 cancelled: Callable[[], bool] | None = None) -> Path:
        version, _ = _version(info.version)
        tag_version, _ = _version(info.tag)
        if version != tag_version or info.asset_name != f"Yayu-{version}-windows-x64.zip":
            raise UpdateError("更新版本与发布包信息不匹配。")
        if not isinstance(info.sha256, str) or not _SHA256.fullmatch(info.sha256):
            raise UpdateError("更新发布包缺少有效的 SHA-256 校验值。")
        self._validate_asset({"name": info.asset_name, "url": info.asset_api_url,
                              "browser_download_url": info.asset_download_url, "state": "uploaded",
                              "size": info.size}, info.tag, info.asset_name, MAX_DOWNLOAD_BYTES)
        deadline = time.monotonic() + DOWNLOAD_TIMEOUT
        self._check_cancelled(cancelled, deadline)
        destination = Path(destination)
        if destination.is_dir():
            destination = destination / info.asset_name
        temporary = destination.with_name(f"{destination.name}.{uuid4().hex}.part")
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with self._open(info.asset_api_url, "application/octet-stream", deadline, cancelled) as response:
                declared_size = self._content_length(response, info.size)
                if declared_size is not None and declared_size != info.size:
                    raise UpdateError("下载文件大小与发布信息不一致，已停止更新。")
                received = 0
                digest = hashlib.sha256()
                if progress is not None:
                    progress(0, info.size)
                with temporary.open("xb") as stream:
                    while True:
                        self._check_cancelled(cancelled, deadline)
                        chunk = response.read(min(256 * 1024, info.size + 1 - received))
                        if not chunk:
                            break
                        received += len(chunk)
                        if received > info.size:
                            raise UpdateError("下载文件超过发布信息中的大小，已停止更新。")
                        stream.write(chunk)
                        digest.update(chunk)
                        if progress is not None:
                            progress(received, info.size)
                    stream.flush()
                    os.fsync(stream.fileno())
                self._check_cancelled(cancelled, deadline)
                if received != info.size:
                    raise UpdateError("更新发布包下载不完整，请重试。")
                if digest.hexdigest() != info.sha256.lower():
                    raise UpdateError("更新发布包 SHA-256 校验失败，已停止更新。")
            os.replace(temporary, destination)
            return destination
        except UpdateError:
            raise
        except (OSError, URLError, TimeoutError, HTTPException):
            raise UpdateError("下载或保存更新发布包失败，请检查网络、磁盘空间和文件夹写入权限后重试。") from None
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
