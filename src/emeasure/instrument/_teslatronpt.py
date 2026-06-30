"""
TeslatronPT system wrapper.

TeslatronPT is not a single VISA instrument. It is a system-level composition
of a TeslatronPT-specific Mercury iTC wrapper, a Mercury iPS, and optionally a motor controller.

The iPS used in this TeslatronPT setup is a single Z-axis magnet. Therefore
``self.ips`` is exposed as a TeslatronPT-specific Z-axis view and does not
require passing ``direction="Z"`` for every command. This Z-axis view owns
the TeslatronPT field snapshot interface; the generic MercuryiPS driver does
not provide snapshot methods.
"""

from __future__ import annotations

import asyncio
import math
import time
from typing import Optional

import pyvisa

from ._core import BaseInstrument
from ._exceptions import (
    InstrumentConnectionError,
    InstrumentOperationTimeout,
    InstrumentParameterError,
    InstrumentParseError,
    InstrumentResponseError,
)
from ._mercury import Mercury, MercuryPSUAxis, MercuryiPS

__all__ = [
    "MotorController",
    "MercuryiTC",
    "TeslatronPTiPS",
    "TeslatronPT",
]


class MotorController(BaseInstrument):
    def __init__(self, visa_address: str, rm: Optional[pyvisa.ResourceManager] = None) -> None:
        super().__init__(visa_address, rm)

    def connect(self) -> None:
        super().connect()
        assert self._res is not None
        self._res.write_termination = "\r\n"
        self._res.read_termination = "\r\n"
        self._res.baud_rate = 115200

    @staticmethod
    def deg2code(deg: float) -> int:
        try:
            deg = float(deg)
        except (TypeError, ValueError) as e:
            raise InstrumentParameterError(f"deg must be numeric, got {deg!r}.") from e

        return math.ceil((deg % 360) * 54050 / 360)

    @staticmethod
    def code2deg(code: int) -> float:
        try:
            code = int(code)
        except (TypeError, ValueError) as e:
            raise InstrumentParameterError(f"code must be an integer, got {code!r}.") from e

        return float(code) * 360 / 54050

    @staticmethod
    def _check_speed(speed: float) -> float:
        try:
            speed = float(speed)
        except (TypeError, ValueError) as e:
            raise InstrumentParameterError(f"speed must be numeric, got {speed!r}.") from e

        if speed <= 0 or speed > 5:
            raise InstrumentParameterError(
                f"Speed must be in (0, 5] deg/sec. Now {speed} deg/sec."
            )

        return speed

    def to_zero(self) -> None:
        self.write("[z,1,1501]")

    def to_deg(self, target: float, speed: float = 5) -> None:
        speed = self._check_speed(speed)
        speed_code = self.deg2code(speed)
        target_code = self.deg2code(target)
        self.write(f"[r,0,{speed_code:04d},{target_code:06d}]")

    def get_deg_code(self) -> int:
        res = self._require_session()

        self.write("[?]")
        try:
            raw = res.read_bytes(12)
        except Exception as e:
            raise InstrumentResponseError("Failed to read motor position response.") from e

        try:
            resp = raw.decode("utf-8")
        except UnicodeDecodeError as e:
            raise InstrumentParseError(
                f"Failed to decode motor position response: {raw!r}"
            ) from e

        if len(resp) < 7:
            raise InstrumentResponseError(
                f"Unexpected motor position response length: {resp!r}"
            )

        try:
            return int(resp[5:-1])
        except ValueError as e:
            raise InstrumentParseError(
                f"Failed to parse motor position code from response: {resp!r}"
            ) from e

    def get_deg(self) -> float:
        return self.code2deg(self.get_deg_code())

    def drive_to_deg(self, target: float, speed: float = 5, *, timeout: Optional[float] = None) -> None:
        speed = self._check_speed(speed)
        speed_code = self.deg2code(speed)
        target_code = self.deg2code(target)
        now_code = self.get_deg_code()

        if speed_code <= 0:
            raise InstrumentParameterError("Internal speed code must be positive.")

        estimated_time = abs(target_code - now_code) / speed_code
        t0 = time.monotonic()

        self.write(f"[r,0,{speed_code:04d},{target_code:06d}]")

        time.sleep(estimated_time)

        while True:
            if target_code == self.get_deg_code():
                return

            if timeout is not None and time.monotonic() - t0 > timeout:
                raise InstrumentOperationTimeout(
                    f"Motor did not reach target position {target} deg before timeout."
                )

            if timeout is None and time.monotonic() - t0 > estimated_time + 2.0:
                raise InstrumentOperationTimeout(
                    f"Motor is not at the target position {target} deg."
                )

            time.sleep(0.2)

    async def adrive_to_deg(
        self,
        target: float,
        speed: float = 5,
        *,
        timeout: Optional[float] = None,
    ) -> None:
        speed = self._check_speed(speed)
        speed_code = self.deg2code(speed)
        target_code = self.deg2code(target)
        now_code = self.get_deg_code()

        if speed_code <= 0:
            raise InstrumentParameterError("Internal speed code must be positive.")

        estimated_time = abs(target_code - now_code) / speed_code
        t0 = time.monotonic()

        self.write(f"[r,0,{speed_code:04d},{target_code:06d}]")

        await asyncio.sleep(estimated_time)

        while True:
            if target_code == self.get_deg_code():
                return

            if timeout is not None and time.monotonic() - t0 > timeout:
                raise InstrumentOperationTimeout(
                    f"Motor did not reach target position {target} deg before timeout."
                )

            if timeout is None and time.monotonic() - t0 > estimated_time + 2.0:
                raise InstrumentOperationTimeout(
                    f"Motor is not at the target position {target} deg."
                )

            await asyncio.sleep(0.2)

class MercuryiTC(Mercury):
    """Mercury iTC wrapper for the TeslatronPT temperature/pressure channels."""

    def get_UID_temp(self, UID: str) -> float:
        return self.query_number(f"READ:DEV:{UID}:TEMP:SIG:TEMP")

    def get_probe_temp(self) -> float:
        return self.get_UID_temp("DB8.T1")

    def get_VTI_temp(self) -> float:
        return self.get_UID_temp("MB1.T1")

    def get_pres(self) -> float:
        return self.query_number("READ:DEV:DB5.P1:PRES:SIG:PRES")

    def get_flow(self) -> float:
        return self.query_number("READ:DEV:DB5.P1:PRES:LOOP:FSET")

    # -------------------- Probe temperature --------------------

    def set_probe_temp_setpoint(self, Tprobe: float) -> None:
        self._check_range(Tprobe, "ITC_PROBE_TEMP", 0, 300, "K")
        self.write_check_valid(f"SET:DEV:DB8.T1:TEMP:LOOP:TSET:{Tprobe}")

    def get_probe_temp_setpoint(self) -> float:
        return self.query_number("READ:DEV:DB8.T1:TEMP:LOOP:TSET")

    def set_probe_loop_enable(self, is_enable: bool = True) -> None:
        self.write_check_valid(
            "SET:DEV:DB8.T1:TEMP:LOOP:ENAB:ON"
            if is_enable
            else "SET:DEV:DB8.T1:TEMP:LOOP:ENAB:OFF"
        )

    def get_probe_loop_enable(self) -> bool:
        return self.query_bool("READ:DEV:DB8.T1:TEMP:LOOP:ENAB")

    def set_probe_heater(self, percentage: float) -> None:
        self._check_range(percentage, "ITC_PROBE_HEATER", 0, 100, "%")
        self.write_check_valid(f"SET:DEV:DB8.T1:TEMP:LOOP:HSET:{percentage}")

    def get_probe_heater(self) -> float:
        return self.query_number("READ:DEV:DB8.T1:TEMP:LOOP:HSET")

    # -------------------- VTI temperature --------------------

    def set_VTI_temp_setpoint(self, Tvti: float) -> None:
        self._check_range(Tvti, "ITC_VTI_TEMP", 0, 300, "K")
        self.write_check_valid(f"SET:DEV:MB1.T1:TEMP:LOOP:TSET:{Tvti}")

    def get_VTI_temp_setpoint(self) -> float:
        return self.query_number("READ:DEV:MB1.T1:TEMP:LOOP:TSET")

    def set_VTI_loop_enable(self, is_enable: bool = True) -> None:
        self.write_check_valid(
            "SET:DEV:MB1.T1:TEMP:LOOP:ENAB:ON"
            if is_enable
            else "SET:DEV:MB1.T1:TEMP:LOOP:ENAB:OFF"
        )

    def get_VTI_loop_enable(self) -> bool:
        return self.query_bool("READ:DEV:MB1.T1:TEMP:LOOP:ENAB")

    def set_VTI_heater(self, percentage: float) -> None:
        self._check_range(percentage, "ITC_VTI_HEATER", 0, 100, "%")
        self.write_check_valid(f"SET:DEV:MB1.T1:TEMP:LOOP:HSET:{percentage}")

    def get_VTI_heater(self) -> float:
        return self.query_number("READ:DEV:MB1.T1:TEMP:LOOP:HSET")

    # -------------------- Pressure and flow --------------------

    def set_pres_setpoint(self, pres: float) -> None:
        self._check_range(pres, "ITC_PRES", 0, 2000, "mbar")
        self.write_check_valid(f"SET:DEV:DB5.P1:PRES:LOOP:PRST:{pres}")

    def get_pres_setpoint(self) -> float:
        return self.query_number("READ:DEV:DB5.P1:PRES:LOOP:PRST")

    def set_pres_loop_enable(self, is_enable: bool = True) -> None:
        self.write_check_valid(
            "SET:DEV:DB5.P1:PRES:LOOP:FAUT:ON"
            if is_enable
            else "SET:DEV:DB5.P1:PRES:LOOP:FAUT:OFF"
        )

    def get_pres_loop_enable(self) -> bool:
        return self.query_bool("READ:DEV:DB5.P1:PRES:LOOP:FAUT")

    def set_flow_setpoint(self, flow: float) -> None:
        self._check_range(flow, "ITC_FLOW", 0, 100, "%")
        self.write_check_valid(f"SET:DEV:DB5.P1:PRES:LOOP:FSET:{flow}")

    def get_flow_setpoint(self) -> float:
        return self.query_number("READ:DEV:DB5.P1:PRES:LOOP:FSET")

    # -------------------- Snapshot --------------------

    def snapshot(self) -> dict[str, float | bool]:
        return {
            "probe_temp": self.get_probe_temp(),
            "VTI_temp": self.get_VTI_temp(),
            "pressure": self.get_pres(),
            "NV_flow": self.get_flow(),
            "probe_temp_setpoint": self.get_probe_temp_setpoint(),
            "VTI_temp_setpoint": self.get_VTI_temp_setpoint(),
            "probe_loop_enable": self.get_probe_loop_enable(),
            "VTI_loop_enable": self.get_VTI_loop_enable(),
            "pres_setpoint": self.get_pres_setpoint(),
            "pres_loop_enable": self.get_pres_loop_enable(),
            "flow_setpoint": self.get_flow_setpoint(),
        }

    @staticmethod
    def _check_range(value: float, name: str, low: float, high: float, unit: str) -> float:
        try:
            value = float(value)
        except (TypeError, ValueError) as e:
            raise InstrumentParameterError(f"{name} must be numeric, got {value!r}.") from e

        if value < low or value > high:
            raise InstrumentParameterError(
                f"{name} must be in [{low}, {high}] {unit}. Now {value} {unit}."
            )

        return value

class TeslatronPTiPS(MercuryPSUAxis):
    """TeslatronPT-specific single-axis iPS view.

    The generic ``MercuryiPS`` driver deliberately does not implement a
    snapshot interface, because different Mercury iPS installations can have
    different axes, sensors, naming conventions, and safety policies.  The
    TeslatronPT setup used here is a single Z-axis magnet, so its field
    snapshot can be defined unambiguously at the system layer.
    """

    def __init__(self, parent: MercuryiPS) -> None:
        super().__init__(parent, "Z")

    def snapshot(self) -> dict[str, float | str | bool]:
        return {
            "iPS_Bz": self.get_field(),
            "iPS_Bz_target": self.get_target_field(),
            "iPS_Bz_ramp_rate": self.get_ramp_rate(),
            "iPS_action": self.get_action(),
            "iPS_heater_ON": self.get_heater_status(),
        }

class TeslatronPT:
    """System-level controller for a TeslatronPT setup.

    Attributes
    ----------
    itc:
        Mercury iTC object.
    ips_controller:
        Mercury iPS controller object.
    ips:
        TeslatronPT-specific Z-axis view of ``ips_controller``. This is the
        main field-control interface and owns the field snapshot for this
        single-axis TeslatronPT system.
    """

    def __init__(
        self,
        rm: Optional[pyvisa.ResourceManager] = None,
        *,
        itc: Optional[MercuryiTC] = None,
        ips: Optional[MercuryiPS] = None,
        itc_address: str = "TCPIP0::192.168.0.20::7020::SOCKET",
        ips_address: str = "TCPIP0::192.168.0.30::7020::SOCKET",
        connect: bool = False,
    ) -> None:
        self.itc = itc or MercuryiTC(itc_address, rm=rm)

        self.ips_controller = ips or MercuryiPS(
            ips_address,
            rm=rm,
            axes=("Z",),
            default_axis="Z",
            max_ramp_rate=0.2,
            max_field_by_axis={"Z": 14.0},
        )

        self.ips: TeslatronPTiPS = TeslatronPTiPS(self.ips_controller)

        self._is_connected = False
        if connect:
            self.connect()

    def connect(self) -> None:
        if self._is_connected:
            return

        connected = []
        try:
            self.itc.connect()
            connected.append(self.itc)

            self.ips_controller.connect()
            connected.append(self.ips_controller)

            self._is_connected = True
        except Exception:
            for inst in reversed(connected):
                try:
                    inst.disconnect()
                except Exception:
                    pass
            raise

    def disconnect(self) -> None:
        if not self._is_connected:
            return

        errors: list[BaseException] = []

        for inst in (self.ips_controller, self.itc):
            try:
                inst.disconnect()
            except Exception as e:
                errors.append(e)

        self._is_connected = False

        if errors:
            raise InstrumentConnectionError(
                "Failed to disconnect one or more TeslatronPT instruments: "
                + "; ".join(str(e) for e in errors)
            ) from errors[0]

    def __enter__(self) -> "TeslatronPT":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            self.disconnect()
        except InstrumentConnectionError:
            if exc_type is None:
                raise

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    # -------------------- TeslatronPT-specific temperature diagnostics --------------------

    def get_magnet_temp(self) -> float:
        return self.ips_controller.query_number("READ:DEV:MB1.T1:TEMP:SIG:TEMP")

    def get_PT2_temp(self) -> float:
        return self.ips_controller.query_number("READ:DEV:DB7.T1:TEMP:SIG:TEMP")

    def get_PT1_temp(self) -> float:
        return self.ips_controller.query_number("READ:DEV:DB8.T1:TEMP:SIG:TEMP")

    def temp_snapshot(self) -> dict[str, float | bool]:
        snap = self.itc.snapshot()
        snap.update(
            {
                "magnet_temp": self.get_magnet_temp(),
                "PT2_temp": self.get_PT2_temp(),
                "PT1_temp": self.get_PT1_temp(),
            }
        )
        return snap

    def field_snapshot(self) -> dict[str, float | str | bool]:
        return self.ips.snapshot()

    def snapshot(self) -> dict[str, float | str | bool]:
        return {
            **self.temp_snapshot(),
            **self.field_snapshot(),
        }

    def warm_up(self, target_temp: float = 300) -> None:
        try:
            target_temp = float(target_temp)
        except (TypeError, ValueError) as e:
            raise InstrumentParameterError(
                f"target_temp must be numeric, got {target_temp!r}."
            ) from e

        if target_temp < 0 or target_temp > 300:
            raise InstrumentParameterError(
                f"PROBE_TEMP and VTI_TEMP must be in [0, 300] K. Now {target_temp} K."
            )

        self.itc.set_probe_loop_enable(True)
        self.itc.set_VTI_loop_enable(True)
        self.itc.set_probe_temp_setpoint(target_temp)
        self.itc.set_VTI_temp_setpoint(target_temp)
