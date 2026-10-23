"""Keep optional private-repository credentials in Windows user-bound DPAPI."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

from .releases import UpdateError


_TOKEN_PATH = Path("data/appdata/updates/github-token.dpapi")
_MAX_TOKEN_BYTES = 4096
_MAX_ENCRYPTED_BYTES = 64 * 1024
_ENTROPY = b"Yayu.GitHubUpdates.v1"


def _valid_token(value: str) -> str:
    value = value.strip()
    if value and (len(value) > _MAX_TOKEN_BYTES or not value.isascii()
                  or any(c.isspace() or ord(c) < 33 for c in value)):
        raise UpdateError("GitHub 访问令牌格式不正确，请重新输入。")
    return value


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def _blob(data: bytes):
    buffer = ctypes.create_string_buffer(data)
    return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer


def _dpapi(data: bytes, *, decrypt: bool) -> bytes:
    if os.name != "nt":
        raise UpdateError("当前系统不支持 Windows DPAPI 安全存储；请通过 GH_TOKEN 环境变量提供 GitHub 令牌。")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptProtectData.argtypes = [ctypes.POINTER(_Blob), wintypes.LPCWSTR, ctypes.POINTER(_Blob),
                                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(_Blob), ctypes.c_void_p, ctypes.POINTER(_Blob),
                                           ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_Blob)]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    source, source_buffer = _blob(data)
    entropy, entropy_buffer = _blob(_ENTROPY)
    output = _Blob()
    if decrypt:
        success = crypt32.CryptUnprotectData(ctypes.byref(source), None, ctypes.byref(entropy), None, None,
                                            1, ctypes.byref(output))
    else:
        success = crypt32.CryptProtectData(ctypes.byref(source), "Yayu GitHub update token", ctypes.byref(entropy),
                                          None, None, 1, ctypes.byref(output))
    if not success:
        raise UpdateError("无法解密 GitHub 访问令牌，请在当前 Windows 账户下重新设置。" if decrypt
                          else "无法安全保存 GitHub 访问令牌，请检查当前 Windows 账户。")
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        # Do not leave the decrypted DPAPI allocation around after copying it.
        if output.pbData:
            ctypes.memset(output.pbData, 0, output.cbData)
            kernel32.LocalFree(output.pbData)
        ctypes.memset(source_buffer, 0, len(source_buffer))
        ctypes.memset(entropy_buffer, 0, len(entropy_buffer))


def get_token(app_root: Path) -> str | None:
    """Use saved user DPAPI, environment, then optional installed GitHub CLI.

    No credential or subprocess output is logged. An unreadable saved token is
    an actionable error rather than silently switching to another identity.
    """
    path = Path(app_root) / _TOKEN_PATH
    if path.exists():
        try:
            if path.stat().st_size > _MAX_ENCRYPTED_BYTES:
                raise UpdateError("已保存的 GitHub 令牌文件无效，请重新设置。")
            token = _valid_token(_dpapi(path.read_bytes(), decrypt=True).decode("utf-8"))
            if not token:
                raise UpdateError("已保存的 GitHub 令牌为空，请重新设置。")
            return token
        except (OSError, UnicodeError):
            raise UpdateError("无法读取已保存的 GitHub 访问令牌，请重新设置。") from None
    for name in ("GH_TOKEN", "GITHUB_TOKEN"):
        value = os.environ.get(name, "")
        if value.strip():
            return _valid_token(value)
    gh = shutil.which("gh")
    if gh:
        try:
            result = subprocess.run(
                [gh, "auth", "token", "--hostname", "github.com"],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                timeout=8, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode == 0 and len(result.stdout) <= _MAX_TOKEN_BYTES:
                return _valid_token(result.stdout.decode("utf-8")) or None
        except (OSError, subprocess.SubprocessError, UnicodeError):
            pass
    return None


def save_token(app_root: Path, token: str) -> None:
    """Atomically save with user-bound DPAPI, or remove a saved token when blank."""
    token = _valid_token(token)
    path = Path(app_root) / _TOKEN_PATH
    if not token:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            raise UpdateError("无法移除已保存的 GitHub 访问令牌，请检查文件夹权限。") from None
        return
    encrypted = _dpapi(token.encode("utf-8"), decrypt=False)
    temporary = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("xb") as stream:
            stream.write(encrypted)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError:
        raise UpdateError("无法保存 GitHub 访问令牌，请检查文件夹写入权限。") from None
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
