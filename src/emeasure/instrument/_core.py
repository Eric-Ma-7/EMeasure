"""
BaseInstrument — minimal, string‑only I/O over PyVISA.

Design goals
- Provide a tiny common base class for all instruments (connect/disconnect/read/write/query).
- String-in / string-out only; parsing and device semantics belong to subclasses.
- Optional shared ResourceManager injection; otherwise create on demand and close on disconnect.
- No threading/async logic to keep behavior predictable.

Usage
-----
from devices.BaseInstrument import BaseInstrument

import pyvisa
rm = pyvisa.ResourceManager()  # or pyvisa.ResourceManager("@py")

with BaseInstrument("TCPIP0::192.168.1.10::INSTR", rm=rm) as inst:
    print(inst.query("*IDN?"))
    inst.write("*RST")

rm.close()
"""


from typing import Optional

import pyvisa
import asyncio
from pyvisa import VisaIOError

__all__ = ["BaseInstrument", "InstrumentError", "InstrumentNotConnected", "_validate_enum_attr"]


class InstrumentError(Exception):
    """Generic instrument error."""


class InstrumentNotConnected(InstrumentError):
    """Raised when I/O is attempted without an active VISA session."""


class BaseInstrument:
    """Minimal instrument base backed by PyVISA (string I/O only).

    Subclasses may override :meth:`connect` to configure encoding, terminations,
    timeouts, or to select a specific backend (e.g., "@py"). Subclasses are
    responsible for interpreting string responses (floats, arrays, binaries, etc.).
    """

    def __init__(self, visa_address: str, rm: Optional[pyvisa.ResourceManager] = None) -> None:
        """Create an instrument instance.

        Args:
            visa_address: VISA resource string (e.g., "TCPIP0::...::INSTR", "USB0::...::INSTR").
            rm: Optional shared ResourceManager. If provided, this instance will
                use it and will **not** close it in :meth:`disconnect`.
        """
        self.address = visa_address
        self._rm: Optional[pyvisa.ResourceManager] = rm
        self._rm_owned: bool = rm is None
        self._res: Optional[pyvisa.resources.Resource] = None
        self._aio_lock: asyncio.Lock = asyncio.Lock()

    # ---------------- Lifecycle ----------------
    def connect(self) -> None:
        """Open the VISA resource using the current configuration.

        Subclasses can override this method to set encoding/terminations/timeouts
        or to choose a different backend.
        """
        if self.is_connected:
            return
        if self._rm is None:
            self._rm = pyvisa.ResourceManager()
            self._rm_owned = True
        try:
            self._res = self._rm.open_resource(self.address)
        except VisaIOError as e:
            self._rm = None
            self._rm_owned = False
            raise InstrumentError(f"Open failed for {self.address}: {e}") from e

    def disconnect(self) -> None:
        """Close the VISA resource and, if owned, the ResourceManager.

        This method is idempotent.
        """
        if self._res is not None:
            try:
                self._res.close()
            finally:
                self._res = None
        if self._rm_owned and self._rm is not None:
            try:
                self._rm.close()
            finally:
                self._rm = None
                self._rm_owned = False

    def __enter__(self) -> "BaseInstrument":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.disconnect()

    @property
    def is_connected(self) -> bool:
        return self._res is not None

    # ---------------- String I/O ----------------
    def write(self, cmd: str) -> None:
        """Send a string command (terminations/encoding are session settings)."""
        res = self._require_session()
        try:
            res.write(cmd)
        except VisaIOError as e:
            raise InstrumentError(f"write failed: {e}") from e

    def read(self) -> str:
        """Read a string response."""
        res = self._require_session()
        try:
            return res.read()
        except VisaIOError as e:
            raise InstrumentError(f"read failed: {e}") from e

    def query(self, cmd: str) -> str:
        """Write then read; return the raw string response."""
        res = self._require_session()
        try:
            return res.query(cmd)
        except VisaIOError as e:
            raise InstrumentError(f"query failed: {e}") from e
    
    
    # ---------------- Asynchronous I/O (non-blocking) ----------------
    async def aconnect(self) -> None:
        """Open the VISA resource in a background thread (non-blocking)."""
        await asyncio.to_thread(self.connect)

    async def adisconnect(self) -> None:
        """Close the VISA resource in a background thread (non-blocking)."""
        await asyncio.to_thread(self.disconnect)

    async def awrite(self, cmd: str) -> None:
        """Send a SCPI command asynchronously without blocking the event loop."""
        async with self._aio_lock:
            res = self._require_session()
            try:
                await asyncio.to_thread(res.write, cmd)
            except VisaIOError as e:
                raise InstrumentError(f"write failed: {e}") from e

    async def aread(self) -> str:
        """Read a response asynchronously without blocking the event loop."""
        async with self._aio_lock:
            res = self._require_session()
            try:
                return await asyncio.to_thread(res.read)
            except VisaIOError as e:
                raise InstrumentError(f"read failed: {e}") from e

    async def aquery(self, cmd: str) -> str:
        """Perform a SCPI query (write + read) asynchronously."""
        async with self._aio_lock:
            res = self._require_session()
            try:
                return await asyncio.to_thread(res.query, cmd)
            except VisaIOError as e:
                raise InstrumentError(f"query failed: {e}") from e

    # ---------------- Internals ----------------
    def _require_session(self) -> pyvisa.resources.Resource:
        if self._res is None:
            raise InstrumentNotConnected("No active VISA session. Call connect() first.")
        return self._res

def _validate_enum_attr(var: str, valid_set: set[str], var_name: str):
    token = var.strip().upper()
    if token not in valid_set:
        raise ValueError(f'Invalid input {var} for {var_name}. Valid inputs are {valid_set}')
    else:
        return token