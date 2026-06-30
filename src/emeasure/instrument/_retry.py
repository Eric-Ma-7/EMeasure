"""
Retry helpers for instrument methods.

This module provides decorators for retrying communication-related failures
without modifying ``BaseInstrument``.

Design notes
------------
- Retry should be applied selectively to high-level device methods.
- Query/readback methods are usually safe to retry.
- Dangerous state-changing methods, such as heater on/off, trigger, output on,
  or ramp start, should not be retried blindly.
- Reconnect, if enabled, calls the instrument's own ``connect()`` method again,
  so subclass-specific connection configuration can be restored.

Typical usage
-------------
from ._retry import retry_on_io_error

class MyInstrument(BaseInstrument):

    @retry_on_io_error(attempts=3, delay=0.2, reconnect=True)
    def fetch(self):
        return self.query(":FETCH?")
"""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

from ._exceptions import (
    InstrumentCloseError,
    InstrumentConnectionError,
    InstrumentIOError,
    InstrumentOpenError,
    InstrumentTimeoutError,
)

__all__ = [
    "DEFAULT_RETRY_ERRORS",
    "retry_on_io_error",
    "aretry_on_io_error",
]

P = ParamSpec("P")
R = TypeVar("R")

logger = logging.getLogger(__name__)

DEFAULT_RETRY_ERRORS: tuple[type[BaseException], ...] = (
    InstrumentIOError,
    InstrumentTimeoutError,
    InstrumentConnectionError,
)


def retry_on_io_error(
    *,
    attempts: int = 3,
    delay: float = 0.2,
    backoff: float = 2.0,
    reconnect: bool = False,
    clear_buffer: bool = True,
    retry_errors: tuple[type[BaseException], ...] = DEFAULT_RETRY_ERRORS,
    reraise_reconnect_error: bool = False,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Retry a synchronous instrument method on communication-related errors.

    Parameters
    ----------
    attempts:
        Total number of attempts, including the first call.

    delay:
        Initial delay between attempts, in seconds.

    backoff:
        Multiplicative factor applied to the delay after each failed attempt.

    reconnect:
        If True, try to disconnect and reconnect the instrument before retrying.

    clear_buffer:
        If True, try to clear the VISA I/O buffer before retrying.

    retry_errors:
        Exception classes that should trigger retry.

    reraise_reconnect_error:
        If True, an error raised during reconnect is immediately propagated.
        If False, reconnect errors are logged and the next retry attempt is still made.

    Notes
    -----
    The decorated function is expected to be an instance method. The first
    argument is treated as the instrument object.

    The instrument object may optionally provide:
    - ``clear_io_buffer()``
    - ``reconnect()``
    - ``disconnect()``
    - ``connect()``

    If these methods are not provided, the decorator falls back to using
    ``self._res.clear()`` where possible.
    """
    _validate_retry_arguments(attempts, delay, backoff)

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            self_obj = args[0] if args else None
            current_delay = delay

            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except retry_errors as exc:
                    if attempt >= attempts:
                        raise

                    _notify_retry(
                        self_obj,
                        func_name=func.__name__,
                        attempt=attempt,
                        attempts=attempts,
                        error=exc,
                    )

                    if clear_buffer:
                        _try_clear_io_buffer(self_obj)

                    if reconnect:
                        _try_reconnect(
                            self_obj,
                            reraise_reconnect_error=reraise_reconnect_error,
                        )

                    if current_delay > 0:
                        time.sleep(current_delay)
                    current_delay *= backoff

            # Unreachable, but keeps type checkers happy.
            raise RuntimeError("retry_on_io_error reached an unreachable state.")

        return wrapper

    return decorator


def aretry_on_io_error(
    *,
    attempts: int = 3,
    delay: float = 0.2,
    backoff: float = 2.0,
    reconnect: bool = False,
    clear_buffer: bool = True,
    retry_errors: tuple[type[BaseException], ...] = DEFAULT_RETRY_ERRORS,
    reraise_reconnect_error: bool = False,
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Retry an asynchronous instrument method on communication-related errors.

    This is the async counterpart of ``retry_on_io_error``.

    The instrument object may optionally provide:
    - ``aclear_io_buffer()``
    - ``areconnect()``
    - ``adisconnect()``
    - ``aconnect()``

    If async methods are not available, synchronous fallbacks are executed in
    a worker thread using ``asyncio.to_thread``.
    """
    _validate_retry_arguments(attempts, delay, backoff)

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            self_obj = args[0] if args else None
            current_delay = delay

            for attempt in range(1, attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except retry_errors as exc:
                    if attempt >= attempts:
                        raise

                    _notify_retry(
                        self_obj,
                        func_name=func.__name__,
                        attempt=attempt,
                        attempts=attempts,
                        error=exc,
                    )

                    if clear_buffer:
                        await _atry_clear_io_buffer(self_obj)

                    if reconnect:
                        await _atry_reconnect(
                            self_obj,
                            reraise_reconnect_error=reraise_reconnect_error,
                        )

                    if current_delay > 0:
                        await asyncio.sleep(current_delay)
                    current_delay *= backoff

            raise RuntimeError("aretry_on_io_error reached an unreachable state.")

        return wrapper

    return decorator


def _validate_retry_arguments(attempts: int, delay: float, backoff: float) -> None:
    if attempts < 1:
        raise ValueError("attempts must be >= 1.")
    if delay < 0:
        raise ValueError("delay must be >= 0.")
    if backoff < 1:
        raise ValueError("backoff must be >= 1.")


def _notify_retry(
    obj: Any,
    *,
    func_name: str,
    attempt: int,
    attempts: int,
    error: BaseException,
) -> None:
    """Notify the object or logger that a retry will be attempted."""
    callback = getattr(obj, "on_retry", None)

    if callable(callback):
        try:
            callback(
                instrument=obj,
                function=func_name,
                attempt=attempt,
                attempts=attempts,
                error=error,
            )
            return
        except Exception:
            logger.exception("Instrument retry callback failed.")

    logger.warning(
        "Retrying %s.%s after error on attempt %d/%d: %s",
        type(obj).__name__ if obj is not None else "<unknown>",
        func_name,
        attempt,
        attempts,
        error,
    )


def _try_clear_io_buffer(obj: Any) -> None:
    if obj is None:
        return

    method = getattr(obj, "clear_io_buffer", None)
    if callable(method):
        try:
            method()
            return
        except Exception:
            logger.debug("clear_io_buffer() failed during retry.", exc_info=True)

    res = getattr(obj, "_res", None)
    if res is not None and hasattr(res, "clear"):
        try:
            res.clear()
        except Exception:
            logger.debug("_res.clear() failed during retry.", exc_info=True)


async def _atry_clear_io_buffer(obj: Any) -> None:
    if obj is None:
        return

    method = getattr(obj, "aclear_io_buffer", None)
    if callable(method):
        try:
            await method()
            return
        except Exception:
            logger.debug("aclear_io_buffer() failed during retry.", exc_info=True)

    method = getattr(obj, "clear_io_buffer", None)
    if callable(method):
        try:
            await asyncio.to_thread(method)
            return
        except Exception:
            logger.debug("clear_io_buffer() failed during async retry.", exc_info=True)

    res = getattr(obj, "_res", None)
    if res is not None and hasattr(res, "clear"):
        try:
            await asyncio.to_thread(res.clear)
        except Exception:
            logger.debug("_res.clear() failed during async retry.", exc_info=True)


def _try_reconnect(
    obj: Any,
    *,
    reraise_reconnect_error: bool,
) -> None:
    if obj is None:
        return

    try:
        method = getattr(obj, "reconnect", None)
        if callable(method):
            method()
            return

        disconnect = getattr(obj, "disconnect", None)
        connect = getattr(obj, "connect", None)

        if callable(disconnect):
            try:
                disconnect()
            except InstrumentCloseError:
                logger.debug("disconnect() raised InstrumentCloseError during retry.", exc_info=True)
            except Exception:
                logger.debug("disconnect() failed during retry.", exc_info=True)

        if callable(connect):
            connect()

    except (InstrumentOpenError, InstrumentConnectionError, Exception) as exc:
        if reraise_reconnect_error:
            raise
        logger.debug("Reconnect failed during retry: %s", exc, exc_info=True)


async def _atry_reconnect(
    obj: Any,
    *,
    reraise_reconnect_error: bool,
) -> None:
    if obj is None:
        return

    try:
        method = getattr(obj, "areconnect", None)
        if callable(method):
            await method()
            return

        method = getattr(obj, "reconnect", None)
        if callable(method):
            await asyncio.to_thread(method)
            return

        adisconnect = getattr(obj, "adisconnect", None)
        aconnect = getattr(obj, "aconnect", None)
        disconnect = getattr(obj, "disconnect", None)
        connect = getattr(obj, "connect", None)

        if callable(adisconnect):
            try:
                await adisconnect()
            except InstrumentCloseError:
                logger.debug("adisconnect() raised InstrumentCloseError during retry.", exc_info=True)
            except Exception:
                logger.debug("adisconnect() failed during retry.", exc_info=True)
        elif callable(disconnect):
            try:
                await asyncio.to_thread(disconnect)
            except InstrumentCloseError:
                logger.debug("disconnect() raised InstrumentCloseError during async retry.", exc_info=True)
            except Exception:
                logger.debug("disconnect() failed during async retry.", exc_info=True)

        if callable(aconnect):
            await aconnect()
        elif callable(connect):
            await asyncio.to_thread(connect)

    except (InstrumentOpenError, InstrumentConnectionError, Exception) as exc:
        if reraise_reconnect_error:
            raise
        logger.debug("Async reconnect failed during retry: %s", exc, exc_info=True)
