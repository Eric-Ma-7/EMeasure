from ._core import BaseInstrument
from ._exceptions import (
    InstrumentModeError,
    InstrumentParameterError,
    InstrumentParseError,
    InstrumentResponseError,
    InstrumentStateError,
)
from ._utils import validate_enum_attr

from typing import Sequence
from pathlib import Path
import h5py
import json
import time


_B2902_CHANNELS = {1, 2}
_DSO9104A_CHANNELS = {1, 2, 3, 4}


class B2902(BaseInstrument):

    def _validate_channel(self, channel: int) -> int:
        if channel not in _B2902_CHANNELS:
            raise InstrumentParameterError(
                f"Invalid B2902 channel {channel!r}. Valid channels are {sorted(_B2902_CHANNELS)}."
            )
        return channel

    def _get_source_mode_or_raise(self, channel: int) -> str:
        mode = self.get_mode(channel)
        if mode not in {"CURR", "VOLT"}:
            raise InstrumentModeError(f"Unknown B2902 source mode received: {mode!r}.")
        return mode

    # --------------- Source mode & output ---------------
    def set_mode(self, mode: str, channel: int):
        channel = self._validate_channel(channel)
        token = validate_enum_attr(
            mode,
            {"I", "CURR", "CURRENT", "V", "VOLT", "VOLTAGE"},
            "source mode",
        )
        if token in {"I", "CURR", "CURRENT"}:
            self.write(f":SOUR{channel}:FUNC:MODE CURR")
        elif token in {"V", "VOLT", "VOLTAGE"}:
            self.write(f":SOUR{channel}:FUNC:MODE VOLT")

    def get_mode(self, channel: int) -> str:
        channel = self._validate_channel(channel)
        return self.query(f":SOUR{channel}:FUNC:MODE?").strip().upper()

    def set_output_on(self, is_on, channel: int):
        channel = self._validate_channel(channel)
        if is_on:
            self.write(f":OUTP{channel} ON")
        else:
            self.write(f":OUTP{channel} OFF")

    def get_output_on(self, channel: int) -> bool:
        channel = self._validate_channel(channel)
        raw = self.query(f":OUTP{channel}:STAT?").strip()
        try:
            resp = int(raw)
        except ValueError as e:
            raise InstrumentParseError(f"Failed to parse OUTP:STAT response: {raw!r}.") from e

        if resp == 1:
            return True
        if resp == 0:
            return False
        raise InstrumentResponseError(f"Unknown OUTP:STAT response: {resp!r}.")

    # --------------- Source Value ---------------
    def set_curr(self, curr: float, channel: int):
        channel = self._validate_channel(channel)
        self.write(f":SOUR{channel}:CURR {curr}")

    def get_curr_setpoint(self, channel: int) -> float:
        channel = self._validate_channel(channel)
        return float(self.query(f":SOUR{channel}:CURR?"))

    def set_volt(self, volt: float, channel: int):
        channel = self._validate_channel(channel)
        self.write(f":SOUR{channel}:VOLT {volt}")

    def get_volt_setpoint(self, channel: int) -> float:
        channel = self._validate_channel(channel)
        return float(self.query(f":SOUR{channel}:VOLT?"))

    def set_src_value(self, val: float, channel: int):
        mode = self._get_source_mode_or_raise(channel)
        if mode == "CURR":
            self.set_curr(val, channel)
        elif mode == "VOLT":
            self.set_volt(val, channel)

    def get_src_value(self, channel: int) -> float:
        mode = self._get_source_mode_or_raise(channel)
        if mode == "CURR":
            return self.get_curr_setpoint(channel)
        if mode == "VOLT":
            return self.get_volt_setpoint(channel)
        raise InstrumentModeError(f"Unknown B2902 source mode received: {mode!r}.")

    # --------------- Source Range ---------------
    def set_curr_src_range(self, curr_range: float, channel: int):
        channel = self._validate_channel(channel)
        self.write(f":SOUR{channel}:CURR:RANG {curr_range}")

    def set_volt_src_range(self, volt_range: float, channel: int):
        channel = self._validate_channel(channel)
        self.write(f":SOUR{channel}:VOLT:RANG {volt_range}")

    def set_src_range(self, src_range: float, channel: int):
        mode = self._get_source_mode_or_raise(channel)
        if mode == "CURR":
            return self.set_curr_src_range(src_range, channel)
        if mode == "VOLT":
            return self.set_volt_src_range(src_range, channel)
        raise InstrumentModeError(f"Unknown B2902 source mode received: {mode!r}.")

    def set_curr_src_range_auto(self, is_auto: bool, channel: int):
        channel = self._validate_channel(channel)
        if is_auto:
            self.write(f":SOUR{channel}:CURR:RANG:AUTO ON")
        else:
            self.write(f":SOUR{channel}:CURR:RANG:AUTO OFF")

    def set_volt_src_range_auto(self, is_auto: bool, channel: int):
        channel = self._validate_channel(channel)
        if is_auto:
            self.write(f":SOUR{channel}:VOLT:RANG:AUTO ON")
        else:
            self.write(f":SOUR{channel}:VOLT:RANG:AUTO OFF")

    def set_src_range_auto(self, is_auto: bool, channel: int):
        mode = self._get_source_mode_or_raise(channel)
        if mode == "CURR":
            return self.set_curr_src_range_auto(is_auto, channel)
        if mode == "VOLT":
            return self.set_volt_src_range_auto(is_auto, channel)
        raise InstrumentModeError(f"Unknown B2902 source mode received: {mode!r}.")

    # --------------- Remote Sense ---------------
    def set_remote_sense(self, is_remote: bool, channel: int):
        channel = self._validate_channel(channel)
        if is_remote:
            self.write(f":SENS{channel}:REM ON")
        else:
            self.write(f":SENS{channel}:REM OFF")

    def get_remote_sense(self, channel: int) -> bool:
        channel = self._validate_channel(channel)
        resp = self.query(f":SENS{channel}:REM?").strip().upper()
        if resp == "ON":
            return True
        if resp == "OFF":
            return False
        raise InstrumentResponseError(f"Unknown :SENSx:REM response: {resp!r}.")

    # --------------- Measure VI ---------------
    def set_form_elem(self, elem: Sequence[str]):
        # To measure VI, set elem = ['VOLT', 'CURR'].
        tokens = [validate_enum_attr(e, {"VOLT", "CURR"}, "form element") for e in elem]
        token = ",".join(tokens)
        self.write(f":FORM:ELEM:SENS {token}")

    def measure(self, channel_sel_token: str = "(@1)"):
        resp = self.query(f":MEAS? {channel_sel_token}").strip()
        try:
            return [float(s) for s in resp.split(",")]
        except ValueError as e:
            raise InstrumentParseError(f"Failed to parse B2902 measurement response: {resp!r}.") from e


class DSO9104A(BaseInstrument):

    def _validate_channel(self, channel: int) -> int:
        if channel not in _DSO9104A_CHANNELS:
            raise InstrumentParameterError(
                f"Invalid DSO9104A channel {channel!r}. Valid channels are {sorted(_DSO9104A_CHANNELS)}."
            )
        return channel

    def _normalize_channel_list(self, channel: int | list[int]) -> list[int]:
        ch_list = [channel] if isinstance(channel, int) else channel
        for ch in ch_list:
            self._validate_channel(ch)
        return ch_list

    def run(self):
        self.write(":run")

    def stop(self):
        self.write(":stop")

    def single(self):
        self.write(":single")

    def digitize(self):
        self.write(":digitize")

    def autoscale_vertical(self, channel: int):
        channel = self._validate_channel(channel)
        self.write(f":autoscale:vertical channel{channel}")

    def autoscale(self):
        self.write(":autoscale")

    # -------------------- Fs, x, y, trigger system --------------------
    def set_sample_rate(self, fs: float | str):
        # fs = AUTO | MAX | <rate>
        if isinstance(fs, str):
            fs = validate_enum_attr(fs, {"AUTO", "MAX"}, "sample rate")
        self.write(f":acquire:srate {fs}")

    def get_sample_rate(self) -> float:
        return float(self.query(":acquire:srate?"))

    def set_x_range(self, xrange: float):
        # xrange is a real number for the horizontal time, in seconds.
        # xrange in [50ps, 200s]
        self.write(f":timebase:range {xrange}")

    def get_x_range(self) -> float:
        return float(self.query(":timebase:range?"))

    def set_x_offset(self, xoffset: float):
        self.write(f":timebase:position {xoffset}")

    def get_x_offset(self) -> float:
        return float(self.query(":timebase:position?"))

    def set_y_scale(self, scale: float, channel: int | list[int]):
        for ch in self._normalize_channel_list(channel):
            self.write(f":channel{ch}:scale {scale}")

    def get_y_scale(self, channel: int) -> float:
        channel = self._validate_channel(channel)
        return float(self.query(f":channel{channel}:scale?"))

    def set_y_offset(self, offset: float, channel: int | list[int]):
        for ch in self._normalize_channel_list(channel):
            self.write(f":channel{ch}:offset {offset}")

    def get_y_offset(self, channel: int) -> float:
        channel = self._validate_channel(channel)
        return float(self.query(f":channel{channel}:offset?"))

    def set_trigger_mode(self, mode: str):
        """
        mode = EDGE | GLITch | PATTern | STATe | DELay | TIMeout | TV |
            COMM | RUNT | SEQuence | SHOLd | TRANsition | WINDow |
            PWIDth | ADVanced | SBUS<N>
        """
        self.write(f":trigger:mode {mode}")

    def get_trigger_mode(self) -> str:
        return self.query(":trigger:mode?").strip()

    def set_trigger_sweep(self, sweep: str):
        """
        sweep = AUTO | TRIGgered | SINGle
        """
        sweep = validate_enum_attr(sweep, {"AUTO", "TRIGGERED", "TRIG", "SINGLE"}, "trigger sweep")
        self.write(f":trigger:sweep {sweep}")

    def get_trigger_sweep(self) -> str:
        return self.query(":trigger:sweep?").strip()

    def set_trigger_level(self, channel: int, level: float):
        channel = self._validate_channel(channel)
        self.write(f":trigger:level channel{channel}, {level}")

    # -------------------- Channel display --------------------
    def get_channel_enable(self, channel: int) -> bool:
        channel = self._validate_channel(channel)
        raw = self.query(f":channel{channel}:display?").strip()
        try:
            enable = bool(int(raw))
        except ValueError as e:
            raise InstrumentParseError(f"Failed to parse channel display response: {raw!r}.") from e
        return enable

    def set_channel_enable(self, enable: bool, channel: int):
        channel = self._validate_channel(channel)
        if enable:
            self.write(f":channel{channel}:display ON")
        else:
            self.write(f":channel{channel}:display OFF")

    # -------------------- Waveform: to workspace --------------------
    def _get_single_waveform(self, channel: int) -> dict:
        channel = self._validate_channel(channel)
        self.write(f":waveform:source channel{channel}")
        resp = self.query(":waveform:data?")
        resp = resp.strip().rstrip(",")

        try:
            waveform = {
                "xOrg": float(self.query(":waveform:xorigin?").strip()),
                "xInc": float(self.query(":waveform:xincrement?").strip()),
                "xUnits": self.query(":waveform:xunits?").strip(),
                "yOrg": float(self.query(":waveform:yorigin?").strip()),
                "yInc": float(self.query(":waveform:yincrement?").strip()),
                "yUnits": self.query(":waveform:yunits?").strip(),
                "yData": [float(s) for s in resp.split(",")],
            }
        except ValueError as e:
            raise InstrumentParseError(f"Failed to parse waveform response for channel {channel}.") from e

        return waveform

    def capture_waveform(self, channel: int | list[int], *, wait_time=0.1) -> dict | list[dict]:
        self.write(":waveform:streaming off")
        self.write(":waveform:format ascii")
        self.write(":digitize")
        time.sleep(wait_time)
        try:
            if isinstance(channel, int):
                waveform = self._get_single_waveform(channel)
            else:
                waveform = [self._get_single_waveform(ch) for ch in channel]
        finally:
            self.write(":run")

        return waveform

    # -------------------- Waveform: to file --------------------
    def capture_and_save(
        self,
        channel: int | list[int],
        h5file: str,
        *,
        is_overwrite: bool = True,
        meta: dict | None = None,
        wait_time: float = 0.1,
    ):
        if (not is_overwrite) and (Path(h5file).exists()):
            raise FileExistsError(f"{h5file} has already existed!")

        # channel index check
        ch_list = self._normalize_channel_list(channel)
        for ch in ch_list:
            if not self.get_channel_enable(ch):
                raise InstrumentStateError(f"Channel {ch} is disabled.")

        # read and save waveform
        wvf = self.capture_waveform(ch_list, wait_time=wait_time)
        with h5py.File(h5file, mode="w") as f:
            # load sample rate
            f.attrs["sample_rate"] = self.get_sample_rate()

            # load user-defined metadata
            if meta is not None:
                f.attrs["meta"] = json.dumps(meta)

            # load waveforms
            for ind, w in zip(ch_list, wvf):
                g = f.create_group(f"CH{ind}")
                for key, val in w.items():
                    g.create_dataset(name=key, data=val)
