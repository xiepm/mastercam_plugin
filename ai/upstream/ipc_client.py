"""Portable client for Mastercam's installed NET-Scripting IPC server.

The IPC add-in is part of the local Mastercam installation.  A dedicated
Mastercam process must be running and the IPCServer add-in must have been
started before this client connects to ``MastercamPipe<PID>``.
"""

from __future__ import annotations

import argparse
import ctypes
import time
import sys
from ctypes import wintypes
from pathlib import Path


GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
OPEN_EXISTING = 3
PIPE_READMODE_MESSAGE = 0x00000002
ERROR_MORE_DATA = 234
ERROR_FILE_NOT_FOUND = 2
ERROR_SEM_TIMEOUT = 121
ERROR_PIPE_BUSY = 231
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


class MastercamIpcError(RuntimeError):
    """Raised when the bundled Mastercam named-pipe server cannot be used."""


def _wait_for_pipe(kernel32: ctypes.WinDLL, pipe_path: str, timeout_ms: int) -> None:
    """Wait for IPCServer to create the pipe, not merely for a busy instance.

    ``WaitNamedPipeW`` returns ``ERROR_FILE_NOT_FOUND`` immediately when the
    named pipe has not been created yet.  Mastercam startup takes tens of
    seconds, so a single call is not a creation wait.
    """

    if timeout_ms <= 0:
        raise MastercamIpcError("timeout_ms must be positive")
    deadline = time.monotonic() + timeout_ms / 1000.0
    last_error = ERROR_FILE_NOT_FOUND
    while True:
        remaining_ms = int(max(0.0, (deadline - time.monotonic()) * 1000))
        if remaining_ms <= 0:
            raise MastercamIpcError(
                f"Mastercam IPC server {pipe_path} was not ready (Win32 error {last_error})"
            )
        if kernel32.WaitNamedPipeW(pipe_path, min(remaining_ms, 1_000)):
            return
        last_error = ctypes.get_last_error()
        if last_error not in {ERROR_FILE_NOT_FOUND, ERROR_SEM_TIMEOUT, ERROR_PIPE_BUSY}:
            raise MastercamIpcError(
                f"Mastercam IPC server {pipe_path} failed (Win32 error {last_error})"
            )
        time.sleep(min(0.25, remaining_ms / 1000.0))


def _kernel32() -> ctypes.WinDLL:
    if not hasattr(ctypes, "WinDLL"):
        raise MastercamIpcError("Mastercam IPC is only available on Windows")
    return ctypes.WinDLL("kernel32", use_last_error=True)


def _read_message(kernel32: ctypes.WinDLL, handle: int) -> str:
    chunks: list[bytes] = []
    while True:
        buffer = ctypes.create_string_buffer(4096)
        read = wintypes.DWORD()
        ok = kernel32.ReadFile(
            handle,
            buffer,
            len(buffer),
            ctypes.byref(read),
            None,
        )
        chunks.append(buffer.raw[: read.value])
        if ok:
            break
        error = ctypes.get_last_error()
        if error != ERROR_MORE_DATA:
            raise MastercamIpcError(f"ReadFile failed with Win32 error {error}")
    return b"".join(chunks).decode("utf-8", errors="strict")


def _write_message(kernel32: ctypes.WinDLL, handle: int, message: str) -> None:
    payload = encode_command(message)
    written = wintypes.DWORD()
    ok = kernel32.WriteFile(
        handle,
        payload,
        len(payload),
        ctypes.byref(written),
        None,
    )
    if not ok or written.value != len(payload):
        error = ctypes.get_last_error()
        raise MastercamIpcError(f"WriteFile failed with Win32 error {error}")


def encode_command(message: str) -> bytes:
    """API29 reads exactly five bytes per block, then trims the whole message.

    A partial final block waits indefinitely. Per-block UTF-8 decoding also
    makes Unicode wire paths unsafe. Use ASCII and one padded pipe message.
    """
    if not message.isascii():
        raise MastercamIpcError('IPC transport path must be ASCII; choose an ASCII workspace or its Windows short path')
    payload=message.encode('ascii')
    return payload+b' '*((-len(payload))%5)


def transport_path(kernel32, path: Path) -> str:
    value=str(path)
    if value.isascii() and ' ' not in value:return value
    kernel32.GetShortPathNameW.argtypes=[wintypes.LPCWSTR,wintypes.LPWSTR,wintypes.DWORD]
    kernel32.GetShortPathNameW.restype=wintypes.DWORD
    size=kernel32.GetShortPathNameW(value,None,0)
    if size:
        buffer=ctypes.create_unicode_buffer(size+1)
        if kernel32.GetShortPathNameW(value,buffer,len(buffer)):value=buffer.value
    if not value.isascii() or ' ' in value:
        raise MastercamIpcError('IPC job path requires an ASCII workspace without spaces when Windows short names are unavailable; the CAD input may still have a Chinese name')
    return value


def run_script(process_id: int, script_path: Path, *, timeout_ms: int = 30_000) -> dict[str, str]:
    """Run one NET-Script and leave the installed IPC service running."""

    script_path = script_path.resolve(strict=True)
    if script_path.suffix.casefold() != ".csx":
        raise MastercamIpcError("script_path must be a .csx file")
    if process_id <= 0:
        raise MastercamIpcError("process_id must be positive")

    pipe_path = rf"\\.\pipe\MastercamPipe{process_id}"
    kernel32 = _kernel32()
    wire_path = transport_path(kernel32,script_path)
    kernel32.WaitNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    kernel32.WaitNamedPipeW.restype = wintypes.BOOL
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.SetNamedPipeHandleState.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPVOID,
        wintypes.LPVOID,
    ]
    kernel32.SetNamedPipeHandleState.restype = wintypes.BOOL
    kernel32.ReadFile.restype = wintypes.BOOL
    kernel32.WriteFile.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    _wait_for_pipe(kernel32, pipe_path, timeout_ms)

    handle = kernel32.CreateFileW(
        pipe_path,
        GENERIC_READ | GENERIC_WRITE,
        0,
        None,
        OPEN_EXISTING,
        0,
        None,
    )
    if handle == INVALID_HANDLE_VALUE:
        error = ctypes.get_last_error()
        raise MastercamIpcError(f"CreateFileW failed with Win32 error {error}")

    try:
        mode = wintypes.DWORD(PIPE_READMODE_MESSAGE)
        if not kernel32.SetNamedPipeHandleState(handle, ctypes.byref(mode), None, None):
            error = ctypes.get_last_error()
            raise MastercamIpcError(
                f"SetNamedPipeHandleState failed with Win32 error {error}"
            )
        print('IPC connected; waiting greeting',file=sys.stderr,flush=True)
        greeting = _read_message(kernel32, handle)
        print('IPC greeting received; submitting script',file=sys.stderr,flush=True)
        _write_message(kernel32, handle, f"RUN {wire_path}")
        run_response = _read_message(kernel32, handle)
        print('IPC script response received',file=sys.stderr,flush=True)
        # Keep the installed IPC service alive for subsequent MCP calls.
        stop_response = "not_requested"
        return {
            "pipe": f"MastercamPipe{process_id}",
            "greeting": greeting,
            "run_response": run_response,
            "stop_response": stop_response,
        }
    finally:
        kernel32.CloseHandle(handle)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an AI-CNC NET-Script via Mastercam IPC")
    parser.add_argument("--pid", type=int, required=True, help="Dedicated Mastercam process ID")
    parser.add_argument("--script", type=Path, required=True)
    parser.add_argument("--timeout-ms", type=int, default=30_000)
    args = parser.parse_args()
    result = run_script(args.pid, args.script, timeout_ms=args.timeout_ms)
    print(result["run_response"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
