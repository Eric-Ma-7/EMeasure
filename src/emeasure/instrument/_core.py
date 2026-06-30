"""
BaseInstrument — minimal, string-only I/O over PyVISA.

Design goals
------------
- Provide a tiny common base class for all instruments.
- Keep this class responsible only for VISA lifecycle and raw string I/O.
- Keep parsing, device semantics, safety checks, and ramp logic in subclasses
  or helper modules.
- Use project-wide exceptions from ``._exceptions`` instead of defining local
  exception classes here.

Usage
-----
import pyvisa
from emeasure.instrument import BaseInstrument

rm = pyvisa.ResourceManager()

with BaseInstrument("TCPIP0::192.168.1.10::INSTR", rm=rm) as inst:
    print(inst.query("*IDN?"))
    inst.write("*RST")

rm.close()
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import NoReturn, Optional

import pyvisa
from pyvisa import VisaIOError

from ._exceptions import (
    InstrumentCloseError,
    InstrumentNotConnected,
    InstrumentOpenError,
    InstrumentQueryError,
    InstrumentReadError,
    InstrumentResourceManagerError,
    InstrumentTimeoutError,
    InstrumentWriteError,
)

__all__ = ["BaseInstrument"]


class BaseInstrument:
    """Minimal instrument base backed by PyVISA.

    This class intentionally performs string-in / string-out I/O only.
    Subclasses should be responsible for:

    - setting terminations, timeout, encoding, and backend-specific options;
    - parsing numeric arrays, binary blocks, status registers, and error queues;
    - checking parameter validity, device state, compliance, and safety.
    """

    def __init__(
        self,
        visa_address: str,
        rm: Optional[pyvisa.ResourceManager] = None,
    ) -> None:
        """Create an instrument wrapper.

        Parameters
        ----------
        visa_address:
            VISA resource string, for example
            ``"TCPIP0::192.168.1.10::INSTR"`` or ``"USB0::...::INSTR"``.

        rm:
            Optional shared PyVISA ResourceManager. If provided, this instance
            will use it and will not close it in :meth:`disconnect`.
        """
        self.address = visa_address

        self._rm: Optional[pyvisa.ResourceManager] = rm
        self._rm_owned: bool = rm is None
        self._res: Optional[pyvisa.resources.Resource] = None

        # PyVISA calls are blocking. The async wrappers below run those calls
        # in background threads, and this lock prevents overlapping I/O on the
        # same VISA session.
        self._aio_lock: asyncio.Lock = asyncio.Lock()

        self._on_exit_hooks: list[Callable[[], None]] = []

    # ============================================================
    # Lifecycle
    # ============================================================

    def connect(self) -> None:
        """Open the VISA resource.

        Subclasses may override this method to configure timeout,
        read/write termination, encoding, chunk size, or backend-specific
        settings after the resource is opened.
        """
        if self.is_connected:
            return

        created_rm = False

        if self._rm is None:
            try:
                self._rm = pyvisa.ResourceManager()
                self._rm_owned = True
                created_rm = True
            except Exception as e:
                self._rm = None
                self._rm_owned = False
                raise InstrumentResourceManagerError(
                    f"Failed to create VISA ResourceManager: {e}"
                ) from e

        try:
            assert self._rm is not None
            self._res = self._rm.open_resource(self.address)
        except VisaIOError as e:
            self._cleanup_owned_rm_after_failed_open(created_rm)
            raise InstrumentOpenError(
                f"Open failed for {self.address}: {e}"
            ) from e
        except Exception as e:
            self._cleanup_owned_rm_after_failed_open(created_rm)
            raise InstrumentOpenError(
                f"Open failed for {self.address}: {e}"
            ) from e

    def disconnect(self) -> None:
        """Close the VISA resource and, if owned, the ResourceManager.

        This method is idempotent. It always tries to release all owned
        resources. If one or more close operations fail, an
        InstrumentCloseError is raised after cleanup has been attempted.
        """
        errors: list[BaseException] = []

        if self._res is not None:
            try:
                self._res.close()
            except Exception as e:
                errors.append(e)
            finally:
                self._res = None

        if self._rm_owned and self._rm is not None:
            try:
                self._rm.close()
            except Exception as e:
                errors.append(e)
            finally:
                self._rm = None
                self._rm_owned = False

        if errors:
            raise InstrumentCloseError(
                f"Failed to close VISA resource for {self.address}: "
                f"{'; '.join(str(e) for e in errors)}"
            ) from errors[0]

    def __enter__(self) -> "BaseInstrument":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        """Run exit hooks and disconnect.

        If the body of the ``with`` statement already raised an exception,
        cleanup errors are not allowed to mask that original exception.
        """
        hook_error: Optional[BaseException] = None
        close_error: Optional[BaseException] = None

        try:
            if self.is_connected:
                for hook in tuple(self._on_exit_hooks):
                    try:
                        hook()
                    except Exception as e:
                        hook_error = e
                        break
        finally:
            try:
                self.disconnect()
            except InstrumentCloseError as e:
                close_error = e

        if exc_type is None:
            if hook_error is not None:
                raise hook_error
            if close_error is not None:
                raise close_error

        return None

    @property
    def is_connected(self) -> bool:
        """Return True if a VISA session is currently open."""
        return self._res is not None

    # ============================================================
    # Exit hooks
    # ============================================================

    def clear_on_exit_hooks(self) -> None:
        """Remove all functions registered to run before disconnect."""
        self._on_exit_hooks.clear()

    def add_on_exit_hook(self, hook: Callable[[], None]) -> None:
        """Register a function to run before disconnect in ``__exit__``.

        Typical use cases include turning off outputs, stopping a sweep, or
        returning an instrument to a safe state.
        """
        self._on_exit_hooks.append(hook)

    # ============================================================
    # String I/O
    # ============================================================

    def write(self, cmd: str) -> None:
        """Send a string command to the instrument."""
        res = self._require_session()
        try:
            res.write(cmd)
        except VisaIOError as e:
            self._raise_visa_io_error(
                e,
                error_cls=InstrumentWriteError,
                operation="write",
                cmd=cmd,
            )

    def read(self) -> str:
        """Read a string response from the instrument."""
        res = self._require_session()
        try:
            return res.read()
        except VisaIOError as e:
            self._raise_visa_io_error(
                e,
                error_cls=InstrumentReadError,
                operation="read",
            )

    def query(self, cmd: str) -> str:
        """Send a string command and read back a string response."""
        res = self._require_session()
        try:
            return res.query(cmd)
        except VisaIOError as e:
            self._raise_visa_io_error(
                e,
                error_cls=InstrumentQueryError,
                operation="query",
                cmd=cmd,
            )

    # ============================================================
    # Asynchronous I/O wrappers
    # ============================================================

    async def aconnect(self) -> None:
        """Open the VISA resource in a background thread."""
        await asyncio.to_thread(self.connect)

    async def adisconnect(self) -> None:
        """Close the VISA resource in a background thread."""
        await asyncio.to_thread(self.disconnect)

    async def awrite(self, cmd: str) -> None:
        """Asynchronously send a string command."""
        async with self._aio_lock:
            await asyncio.to_thread(self.write, cmd)

    async def aread(self) -> str:
        """Asynchronously read a string response."""
        async with self._aio_lock:
            return await asyncio.to_thread(self.read)

    async def aquery(self, cmd: str) -> str:
        """Asynchronously perform a string query."""
        async with self._aio_lock:
            return await asyncio.to_thread(self.query, cmd)

    # ============================================================
    # Internals
    # ============================================================

    def _require_session(self) -> pyvisa.resources.Resource:
        if self._res is None:
            raise InstrumentNotConnected(
                "No active VISA session. Call connect() first."
            )
        return self._res

    def _cleanup_owned_rm_after_failed_open(self, created_rm: bool) -> None:
        """Close an owned ResourceManager after open_resource() fails."""
        if self._rm_owned and self._rm is not None:
            try:
                self._rm.close()
            except Exception:
                pass

        if created_rm:
            self._rm = None
            self._rm_owned = False

    @staticmethod
    def _is_timeout_error(error: VisaIOError) -> bool:
        """Best-effort detection of a VISA timeout error."""
        text = f"{getattr(error, 'error_code', '')} {error}".lower()
        return "timeout" in text or "timed out" in text

    def _raise_visa_io_error(
        self,
        error: VisaIOError,
        *,
        error_cls: type[Exception],
        operation: str,
        cmd: Optional[str] = None,
    ) -> NoReturn:
        detail = f"{operation} failed on {self.address}"
        if cmd is not None:
            detail += f", cmd={cmd!r}"
        detail += f": {error}"

        if self._is_timeout_error(error):
            raise InstrumentTimeoutError(detail) from error

        raise error_cls(detail) from error
