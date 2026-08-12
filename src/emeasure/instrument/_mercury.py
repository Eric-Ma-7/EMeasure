"""
Mercury instruments.

This module contains the common Mercury protocol wrapper and higher-level
drivers for Oxford Mercury iPS controllers.

Design
------
- Mercury: low-level string protocol helpers on top of BaseInstrument.
- MercuryiPS: generic magnet power-supply controller supporting one or more axes.
  It intentionally only exposes PSU / field / persistent-switch operations.
- MercuryPSUAxis: lightweight axis view, so single-axis systems can call
  ``axis.get_field()`` instead of repeatedly passing ``direction="Z"``.
"""

from __future__ import annotations

import asyncio
import re
import threading
import time
from typing import Callable, Optional

import pyvisa

from ._core import BaseInstrument
from ._exceptions import (
    InstrumentCommandError,
    InstrumentOperationTimeout,
    InstrumentParameterError,
    InstrumentParseError,
    InstrumentResponseError,
)
from ._utils import validate_enum_attr

__all__ = [
    "Mercury",
    "MercuryiPS",
    "MercuryPSUAxis",
]


_NUM_RE = re.compile(
    r"([-+]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*([A-Za-zΩµu%/]+)?$"
)

PollStatus = dict[str, float | str | bool]
PollHook = Callable[[PollStatus], None]


class Mercury(BaseInstrument):
    """Base class for Oxford Mercury protocol instruments.

    Mercury controllers return strings such as ``STAT:...`` for queries and
    ``STAT:...:VALID`` for accepted set commands. This class provides small
    helpers for those common patterns.
    """

    def __init__(self, visa_address: str, rm: Optional[pyvisa.ResourceManager] = None) -> None:
        super().__init__(visa_address, rm)
        self._thread_lock = threading.RLock()

    def write(self, cmd: str) -> None:
        with self._thread_lock:
            super().write(cmd)

    def read(self) -> str:
        with self._thread_lock:
            return super().read()

    def query(self, cmd: str) -> str:
        with self._thread_lock:
            return super().query(cmd)

    async def awrite(self, cmd: str) -> None:
        async with self._aio_lock:
            await asyncio.to_thread(self.write, cmd)

    async def aread(self) -> str:
        async with self._aio_lock:
            return await asyncio.to_thread(self.read)

    async def aquery(self, cmd: str) -> str:
        async with self._aio_lock:
            return await asyncio.to_thread(self.query, cmd)

    def connect(self) -> None:
        with self._thread_lock:
            super().connect()
            assert self._res is not None
            self._res.set_visa_attribute(pyvisa.constants.VI_ATTR_TERMCHAR, 0x0A)
            self._res.set_visa_attribute(pyvisa.constants.VI_ATTR_TERMCHAR_EN, 0x1)
            self._res.read_termination = "\n"
            self._res.write_termination = "\n"

    def disconnect(self) -> None:
        with self._thread_lock:
            super().disconnect()

    def write_check_valid(self, cmd: str) -> str:
        """Send a set command and require a ``VALID`` response."""
        resp = (self.query(cmd) or "").strip()
        if ":VALID" not in resp.upper():
            raise InstrumentCommandError(
                f"Mercury controller rejected command {cmd!r}: {resp or 'no response'}"
            )
        return resp

    def query_check_stat(self, cmd: str) -> str:
        """Send a query and require a ``STAT:`` response."""
        resp = (self.query(cmd) or "").strip()
        if not resp.startswith("STAT:"):
            raise InstrumentResponseError(
                f"Unexpected Mercury reply for {cmd!r}: {resp or 'no response'}"
            )
        return resp

    def query_number(self, cmd: str, return_unit: bool = False):
        """Query a numeric value.

        Returns
        -------
        float
            If ``return_unit`` is False.
        tuple[float, str | None]
            If ``return_unit`` is True.
        """
        resp = self.query_check_stat(cmd)
        tail = resp.split(":")[-1].strip()
        match = _NUM_RE.search(tail)
        if not match:
            raise InstrumentParseError(
                f"Cannot parse numeric value from Mercury reply for {cmd!r}: {resp!r}"
            )

        value = float(match.group(1))
        unit = match.group(2) or None
        if return_unit:
            return value, unit
        return value

    def query_bool(self, cmd: str) -> bool:
        resp = self.query_check_stat(cmd)
        tail = resp.split(":")[-1].strip().upper()

        if tail in {"ON", "1", "TRUE"}:
            return True
        if tail in {"OFF", "0", "FALSE"}:
            return False

        raise InstrumentParseError(
            f"Cannot parse boolean value from Mercury reply for {cmd!r}: {resp!r}"
        )

    def query_str(self, cmd: str) -> str:
        resp = self.query_check_stat(cmd)
        return resp.split(":")[-1].strip().upper()


def _normalize_axis(direction: str) -> str:
    if not isinstance(direction, str):
        raise InstrumentParameterError(
            f"direction must be a string in {{'X', 'Y', 'Z'}}, got {type(direction).__name__}."
        )

    axis = direction.strip().upper()
    if axis not in {"X", "Y", "Z"}:
        raise InstrumentParameterError(
            f"Invalid direction {direction!r}. Valid directions are 'X', 'Y', and 'Z'."
        )

    return axis


class MercuryPSUAxis:
    """A lightweight view of one iPS PSU axis.

    This class does not own a VISA session. It delegates all communication to
    its parent ``MercuryiPS`` instance.
    """

    def __init__(self, parent: "MercuryiPS", direction: str) -> None:
        self.parent = parent
        self.direction = parent._resolve_axis(direction)

    @property
    def axis(self) -> str:
        return self.direction

    def get_field(self) -> float:
        return self.parent.get_field(self.direction)

    def get_target_field(self) -> float:
        return self.parent.get_target_field(self.direction)

    def set_target_field(self, B_target: float) -> None:
        self.parent.set_target_field(B_target, self.direction)

    def get_ramp_rate(self) -> float:
        return self.parent.get_ramp_rate(self.direction)

    def set_ramp_rate(self, rate: float) -> None:
        self.parent.set_ramp_rate(rate, self.direction)

    def get_action(self) -> str:
        return self.parent.get_action(self.direction)

    def set_action(self, actn: str) -> None:
        self.parent.set_action(actn, self.direction)

    def wait_until_hold(
        self,
        poll_interval: float = 2.0,
        *,
        timeout: Optional[float] = None,
        poll_hook: Optional[PollHook] = None,
    ) -> None:
        self.parent.wait_until_hold(
            self.direction,
            poll_interval=poll_interval,
            timeout=timeout,
            poll_hook=poll_hook,
        )

    def drive_to_field(
        self,
        B_target: float,
        rate: float,
        *,
        poll_interval: float = 2.0,
        timeout: Optional[float] = None,
        poll_hook: Optional[PollHook] = None,
    ) -> None:
        self.parent.drive_to_field(
            B_target,
            rate,
            self.direction,
            poll_interval=poll_interval,
            timeout=timeout,
            poll_hook=poll_hook,
        )

    def get_heater_status(self) -> bool:
        return self.parent.get_heater_status(self.direction)

    def set_heater_on(self, *, is_wait: bool = False) -> None:
        self.parent.set_heater_on(self.direction, is_wait=is_wait)

    def set_heater_off(self, *, is_wait: bool = False) -> None:
        self.parent.set_heater_off(self.direction, is_wait=is_wait)

    def wait_heater_on(self) -> None:
        self.parent.wait_heater_on(self.direction)

    def wait_heater_off(self) -> None:
        self.parent.wait_heater_off(self.direction)

    async def await_heater_on(self) -> None:
        await self.parent.await_heater_on(self.direction)

    async def await_heater_off(self) -> None:
        await self.parent.await_heater_off(self.direction)


class MercuryiPS(Mercury):
    """Generic Mercury iPS driver.

    ``MercuryiPS`` supports both single-axis and multi-axis controllers.

    Examples
    --------
    Single-axis Z system::

        ips = MercuryiPS(addr, axes=("Z",), default_axis="Z")
        ips.get_field()
        ips.drive_to_field(1.0, 0.05)

    Three-axis system::

        ips = MercuryiPS(addr, axes=("X", "Y", "Z"))
        ips.x.get_field()
        ips.z.drive_to_field(1.0, 0.05)
    """

    _ACTN = {"HOLD", "RTOS", "RTOZ"}
    _RUNNING_ACTN = {"RTOS"}
    _FINISHED_ACTN = {"HOLD"}

    def __init__(
        self,
        visa_address: str,
        rm: Optional[pyvisa.ResourceManager] = None,
        *,
        axes: tuple[str, ...] = ("X", "Y", "Z"),
        default_axis: Optional[str] = None,
        max_ramp_rate: float = 0.2,
        max_field_by_axis: Optional[dict[str, float]] = None,
    ) -> None:
        super().__init__(visa_address, rm)

        self.axes = tuple(_normalize_axis(axis) for axis in axes)
        if len(set(self.axes)) != len(self.axes):
            raise InstrumentParameterError(f"Duplicate iPS axes are not allowed: {self.axes!r}.")

        self.default_axis = _normalize_axis(default_axis) if default_axis is not None else None
        if self.default_axis is not None and self.default_axis not in self.axes:
            raise InstrumentParameterError(
                f"default_axis {self.default_axis!r} is not in available axes {self.axes!r}."
            )

        if max_ramp_rate <= 0:
            raise InstrumentParameterError("max_ramp_rate must be positive.")
        self.max_ramp_rate = float(max_ramp_rate)

        if max_field_by_axis is None:
            self.max_field_by_axis = {axis: 14.0 for axis in self.axes}
        else:
            self.max_field_by_axis = {
                _normalize_axis(axis): float(value)
                for axis, value in max_field_by_axis.items()
            }
            for axis in self.axes:
                self.max_field_by_axis.setdefault(axis, 14.0)

    def axis(self, direction: str) -> MercuryPSUAxis:
        return MercuryPSUAxis(self, direction)

    @property
    def x(self) -> MercuryPSUAxis:
        return self.axis("X")

    @property
    def y(self) -> MercuryPSUAxis:
        return self.axis("Y")

    @property
    def z(self) -> MercuryPSUAxis:
        return self.axis("Z")

    def _resolve_axis(self, direction: Optional[str] = None) -> str:
        if direction is None:
            if self.default_axis is None:
                raise InstrumentParameterError(
                    "direction is required because this MercuryiPS has no default_axis."
                )
            axis = self.default_axis
        else:
            axis = _normalize_axis(direction)

        if axis not in self.axes:
            raise InstrumentParameterError(
                f"Axis {axis!r} is not available. Available axes are {self.axes!r}."
            )

        return axis

    @staticmethod
    def _check_poll_interval(poll_interval: float) -> float:
        try:
            poll_interval = float(poll_interval)
        except (TypeError, ValueError) as e:
            raise InstrumentParameterError(
                f"poll_interval must be numeric, got {poll_interval!r}."
            ) from e

        if poll_interval <= 0:
            raise InstrumentParameterError(
                f"poll_interval must be positive. Now {poll_interval}."
            )

        return poll_interval

    @staticmethod
    def _check_timeout(timeout: Optional[float]) -> Optional[float]:
        if timeout is None:
            return None

        try:
            timeout = float(timeout)
        except (TypeError, ValueError) as e:
            raise InstrumentParameterError(f"timeout must be numeric, got {timeout!r}.") from e

        if timeout <= 0:
            raise InstrumentParameterError(f"timeout must be positive. Now {timeout}.")

        return timeout

    def _check_rate(self, rate: float) -> float:
        try:
            rate = float(rate)
        except (TypeError, ValueError) as e:
            raise InstrumentParameterError(f"Ramp rate must be numeric, got {rate!r}.") from e

        if rate <= 0 or rate > self.max_ramp_rate:
            raise InstrumentParameterError(
                f"Ramp rate must be in (0, {self.max_ramp_rate}] T/min. Now {rate} T/min."
            )

        return rate

    def _check_field(self, B_target: float, axis: str) -> float:
        try:
            B_target = float(B_target)
        except (TypeError, ValueError) as e:
            raise InstrumentParameterError(f"Target field must be numeric, got {B_target!r}.") from e

        max_field = self.max_field_by_axis[axis]
        if abs(B_target) > max_field:
            raise InstrumentParameterError(
                f"Target magnetic field for axis {axis} must be within ±{max_field} T. "
                f"Now {B_target} T."
            )

        return B_target

    def _make_poll_status(self, axis: str, *, action: str, t0: float) -> PollStatus:
        return {
            "axis": axis,
            "field": self.get_field(axis),
            "target_field": self.get_target_field(axis),
            "ramp_rate": self.get_ramp_rate(axis),
            "action": action,
            "heater_ON": self.get_heater_status(axis),
            "elapsed_s": time.monotonic() - t0,
            "timestamp": time.time(),
        }

    # -------------------- Field and action --------------------

    def get_field(self, direction: Optional[str] = None) -> float:
        axis = self._resolve_axis(direction)
        return self.query_number(f"READ:DEV:GRP{axis}:PSU:SIG:PFLD")

    def get_target_field(self, direction: Optional[str] = None) -> float:
        axis = self._resolve_axis(direction)
        return self.query_number(f"READ:DEV:GRP{axis}:PSU:SIG:FSET")

    def set_target_field(self, B_target: float, direction: Optional[str] = None) -> None:
        axis = self._resolve_axis(direction)
        B_target = self._check_field(B_target, axis)
        self.write_check_valid(f"SET:DEV:GRP{axis}:PSU:SIG:FSET:{B_target:.6f}")

    def get_ramp_rate(self, direction: Optional[str] = None) -> float:
        axis = self._resolve_axis(direction)
        return self.query_number(f"READ:DEV:GRP{axis}:PSU:SIG:RFST")

    def set_ramp_rate(self, rate: float, direction: Optional[str] = None) -> None:
        axis = self._resolve_axis(direction)
        rate = self._check_rate(rate)
        self.write_check_valid(f"SET:DEV:GRP{axis}:PSU:SIG:RFST:{rate:.4f}")

    def get_action(self, direction: Optional[str] = None) -> str:
        axis = self._resolve_axis(direction)
        return self.query_str(f"READ:DEV:GRP{axis}:PSU:ACTN")

    def set_action(self, actn: str, direction: Optional[str] = None) -> None:
        axis = self._resolve_axis(direction)
        token = validate_enum_attr(actn, self._ACTN, "IPS_ACTN")
        self.write_check_valid(f"SET:DEV:GRP{axis}:PSU:ACTN:{token}")

    def wait_until_hold(
        self,
        direction: Optional[str] = None,
        *,
        poll_interval: float = 2.0,
        timeout: Optional[float] = None,
        poll_hook: Optional[PollHook] = None,
    ) -> None:
        """Wait for an RTOS field ramp to finish normally.

        The expected state transition is strictly ``RTOS -> HOLD``.

        During polling:
        - ``RTOS`` means the ramp is still running, so waiting continues.
        - ``HOLD`` means the ramp finished normally, so this method returns.
        - Any other action is treated as an abnormal state and raises
          ``InstrumentResponseError`` immediately. This is intended to catch
          states such as CLAMP, QUENCH, FAULT, or other non-running conditions
          without waiting until timeout.

        ``poll_hook`` is called once per poll with a status dictionary. If the
        hook raises, the exception is propagated and the wait is interrupted.
        """
        axis = self._resolve_axis(direction)
        poll_interval = self._check_poll_interval(poll_interval)
        timeout = self._check_timeout(timeout)
        t0 = time.monotonic()

        while True:
            action = self.get_action(axis)
            status = self._make_poll_status(axis, action=action, t0=t0)

            if poll_hook is not None:
                poll_hook(status)

            if action in self._RUNNING_ACTN:
                pass
            elif action in self._FINISHED_ACTN:
                return
            else:
                raise InstrumentResponseError(
                    f"Unexpected iPS action while waiting for axis {axis} to reach HOLD: "
                    f"{action!r}. Last status: {status!r}"
                )

            elapsed = time.monotonic() - t0
            if timeout is not None and elapsed > timeout:
                raise InstrumentOperationTimeout(
                    f"Timed out waiting for iPS axis {axis} to reach HOLD. "
                    f"Last status: {status!r}"
                )

            time.sleep(poll_interval)

    def drive_to_field(
        self,
        B_target: float,
        rate: float,
        direction: Optional[str] = None,
        *,
        poll_interval: float = 2.0,
        timeout: Optional[float] = None,
        poll_hook: Optional[PollHook] = None,
    ) -> None:
        axis = self._resolve_axis(direction)
        self.set_action("HOLD", axis)
        self.set_target_field(B_target, axis)
        self.set_ramp_rate(rate, axis)
        self.set_action("RTOS", axis)
        self.wait_until_hold(
            axis,
            poll_interval=poll_interval,
            timeout=timeout,
            poll_hook=poll_hook,
        )

    # -------------------- Heater --------------------

    def get_heater_status(self, direction: Optional[str] = None) -> bool:
        axis = self._resolve_axis(direction)
        return self.query_bool(f"READ:DEV:GRP{axis}:PSU:SIG:SWHT")

    def set_heater_on(self, direction: Optional[str] = None, *, is_wait: bool = False) -> None:
        axis = self._resolve_axis(direction)
        if not self.get_heater_status(axis):
            self.write_check_valid(f"SET:DEV:GRP{axis}:PSU:SIG:SWHT:ON")
        if is_wait:
            self.wait_heater_on(axis)

    def set_heater_off(self, direction: Optional[str] = None, *, is_wait: bool = False) -> None:
        axis = self._resolve_axis(direction)
        if self.get_heater_status(axis):
            self.write_check_valid(f"SET:DEV:GRP{axis}:PSU:SIG:SWHT:OFF")
        if is_wait:
            self.wait_heater_off(axis)

    def wait_heater_on(self, direction: Optional[str] = None) -> None:
        axis = self._resolve_axis(direction)
        delay_ms = self.query_number(f"READ:DEV:GRP{axis}:PSU:SWONT")
        time.sleep(delay_ms / 1000.0)

        while not self.get_heater_status(axis):
            time.sleep(10)

    def wait_heater_off(self, direction: Optional[str] = None) -> None:
        axis = self._resolve_axis(direction)
        delay_ms = self.query_number(f"READ:DEV:GRP{axis}:PSU:SWOFT")
        time.sleep(delay_ms / 1000.0)

        while self.get_heater_status(axis):
            time.sleep(10)

    async def await_heater_on(self, direction: Optional[str] = None) -> None:
        axis = self._resolve_axis(direction)
        delay_ms = self.query_number(f"READ:DEV:GRP{axis}:PSU:SWONT")
        await asyncio.sleep(delay_ms / 1000.0)

        while not self.get_heater_status(axis):
            await asyncio.sleep(10)

    async def await_heater_off(self, direction: Optional[str] = None) -> None:
        axis = self._resolve_axis(direction)
        delay_ms = self.query_number(f"READ:DEV:GRP{axis}:PSU:SWOFT")
        await asyncio.sleep(delay_ms / 1000.0)

        while self.get_heater_status(axis):
            await asyncio.sleep(10)

