"""Per-turn cancellation shared by workers; no Qt or provider dependencies."""
from __future__ import annotations

import asyncio
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import Event
from uuid import uuid4


class TurnCancelled(Exception):
    """Normal control flow, never an application error."""


@dataclass(eq=False)
class TurnToken:
    session_id: str = ""
    id: str = field(default_factory=lambda: uuid4().hex)
    cancelled: Event = field(default_factory=Event)

    def cancel(self):
        self.cancelled.set()

    def check(self):
        if self.cancelled.is_set():
            raise TurnCancelled()


@dataclass
class TurnWork:
    token: TurnToken
    payload: object


@dataclass
class TurnEvent:
    token: TurnToken
    kind: str
    payload: object = None


_current: ContextVar[TurnToken | None] = ContextVar("galgame_turn", default=None)


def current_token():
    return _current.get()


def check_cancelled():
    token = current_token()
    if token is not None:
        token.check()


@contextmanager
def turn_scope(token):
    marker = _current.set(token)
    try:
        check_cancelled()
        yield
    finally:
        _current.reset(marker)


def tagged(payload):
    token = current_token()
    return TurnWork(token, payload) if token is not None else payload


def run_async(operation):
    """Cancel the actual I/O task and await cleanup, including before headers arrive."""
    token = current_token()

    async def run():
        task = asyncio.create_task(operation())
        try:
            while not task.done():
                if token is not None:
                    token.check()
                await asyncio.wait({task}, timeout=0.05)
            if token is not None:
                token.check()
            return await task
        finally:
            if not task.done():
                task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await task

    return asyncio.run(run())


def discard_pending(queue):
    from queue import Empty
    while True:
        try:
            queue.get_nowait()
        except Empty:
            return
