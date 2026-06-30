from ._core import BaseInstrument
from ._utils import ramp_drive
from ._exceptions import (
    InstrumentParameterError,
    InstrumentParseError,
    InstrumentResponseError,
)

from typing import Sequence, Optional


def _parse_float_response(resp: str, context: str) -> float:
    """Parse a single float response and raise an instrument-level error on failure."""
    try:
        return float(resp.strip())
    except (TypeError, ValueError) as e:
        raise InstrumentParseError(
            f"Failed to parse response for {context}: {resp!r}"
        ) from e


def _parse_float_sequence(resp: str, context: str, *, sep: str | None = None) -> tuple[float, ...]:
    """Parse a numeric response into a tuple of floats.

    Args:
        resp: Raw instrument response.
        context: Command or operation name used in the error message.
        sep: Separator passed to str.split(). Use None for whitespace splitting.
    """
    try:
        return tuple(float(x) for x in resp.strip().split(sep))
    except (TypeError, ValueError) as e:
        raise InstrumentParseError(
            f"Failed to parse response for {context}: {resp!r}"
        ) from e


class K6221(BaseInstrument):
    def __init__(self, visa_address, rm=None):
        super().__init__(visa_address, rm)

    # --------------- DC Source --------------- #
    def set_curr(self, I: float):
        self.write(f'SOUR:CURR {I}')

    def get_curr(self) -> float:
        return _parse_float_response(self.query('SOUR:CURR?'), 'SOUR:CURR?')

    def set_output_on(self, is_on: bool = True):
        if is_on:
            self.write('OUTP ON')
        else:
            self.write('OUTP OFF')

    def get_output_on(self) -> bool:
        resp = self.query('OUTP?').strip().upper()
        if resp in {'ON', '1'}:
            return True
        elif resp in {'OFF', '0'}:
            return False
        else:
            raise InstrumentResponseError(
                f'Unexpected response for OUTP?: {resp!r}'
            )

    def set_volt_limit(self, limit: float):
        if 0.1 <= limit <= 105:
            self.write(f'SOUR:CURR:COMP {limit}')
        else:
            raise InstrumentParameterError(
                'Voltage compliance must be in [0.1, 105].'
            )

    def get_volt_limit(self) -> float:
        return _parse_float_response(self.query('SOUR:CURR:COMP?'), 'SOUR:CURR:COMP?')

    def set_curr_range(self, curr_range: float):
        self.write(f'SOUR:CURR:RANG {curr_range}')

    def set_curr_range_auto(self, is_auto: bool = True):
        if is_auto:
            self.write('SOUR:CURR:RANG:AUTO ON')
        else:
            self.write('SOUR:CURR:RANG:AUTO OFF')

    def clear_source(self):
        self.write('SOUR:CLE')

    # --------------- SINE WAVE Source --------------- #
    def set_source_wave_sin(self, freq: float, ampl: float, offs: float = 0) -> None:
        self.write('SOUR:WAVE:FUNC SIN')
        self.write(f'SOUR:WAVE:FREQ {freq}')
        self.write(f'SOUR:WAVE:AMPL {ampl}')
        self.write(f'SOUR:WAVE:OFFS {offs}')
        self.write('SOUR:WAVE:RANG BEST')
        self.write('SOUR:WAVE:PMAR 0')
        self.write('SOUR:WAVE:PMAR:STAT ON')

    def arm_and_trigger_waveform(self) -> None:
        self.write('SOUR:WAVE:ARM')
        self.write('SOUR:WAVE:INIT')

    def stop_waveform(self) -> None:
        self.write('SOUR:WAVE:ABOR')


class K2612(BaseInstrument):
    def _ch2smux(self, channel: str) -> str:
        if channel.lower() in {'a', 'b'}:
            return f'smu{channel.lower()}'
        else:
            raise InstrumentParameterError(
                "Channel must be 'a' or 'b'."
            )

    def set_volt(self, volt: float, channel: str):
        smux = self._ch2smux(channel)
        self.write(f'{smux}.source.levelv = {volt}')

    def set_curr(self, curr: float, channel: str):
        smux = self._ch2smux(channel)
        self.write(f'{smux}.source.leveli = {curr}')

    def get_iv(self, channel: str) -> Sequence[float]:
        smux = self._ch2smux(channel)
        resp = self.query(f'print({smux}.measure.iv())')
        return _parse_float_sequence(resp, f'print({smux}.measure.iv())')

    def get_volt(self, channel: str) -> float:
        smux = self._ch2smux(channel)
        return _parse_float_response(
            self.query(f'print({smux}.measure.v())'),
            f'print({smux}.measure.v())',
        )

    def get_curr(self, channel: str) -> float:
        smux = self._ch2smux(channel)
        return _parse_float_response(
            self.query(f'print({smux}.measure.i())'),
            f'print({smux}.measure.i())',
        )

    def set_output_on(self, is_on: bool, channel: str):
        smux = self._ch2smux(channel)
        if is_on:
            self.write(f'{smux}.source.output = 1')
        else:
            self.write(f'{smux}.source.output = 0')

    def get_output_on(self, channel: str) -> bool:
        smux = self._ch2smux(channel)
        cmd = f'print({smux}.source.output)'
        resp_raw = self.query(cmd).strip()
        resp = _parse_float_response(resp_raw, cmd)

        if resp == 1:
            return True
        elif resp == 0:
            return False
        else:
            raise InstrumentResponseError(
                f"Unexpected response for {cmd}: {resp_raw!r}"
            )

    def set_volt_limit(self, volt_limit: float, channel: str):
        smux = self._ch2smux(channel)
        self.write(f'{smux}.source.limitv = {volt_limit}')

    def set_curr_limit(self, curr_limit: float, channel: str):
        smux = self._ch2smux(channel)
        self.write(f'{smux}.source.limiti = {curr_limit}')

    def set_volt_range(self, volt_range: float, channel: str):
        smux = self._ch2smux(channel)
        self.write(f'{smux}.source.rangev = {volt_range}')

    def set_curr_range(self, curr_range: float, channel: str):
        smux = self._ch2smux(channel)
        self.write(f'{smux}.source.rangei = {curr_range}')

    def set_sense_mode(self, sense_mode: str, channel: str):
        smux = self._ch2smux(channel)
        if sense_mode.lower() in {'4-wire', '4w', '4wire', 'remote'}:
            self.write(f'{smux}.sense = {smux}.SENSE_REMOTE')
        elif sense_mode.lower() in {'2-wire', '2w', '2wire', 'local'}:
            self.write(f'{smux}.sense = {smux}.SENSE_LOCAL')
        else:
            raise InstrumentParameterError(
                "Sense mode must be '2-wire/local' or '4-wire/remote'."
            )

    def set_source_func(self, src_func: str, channel: str):
        smux = self._ch2smux(channel)
        if src_func.lower() in {'curr', 'i', 'current'}:
            self.write(f'{smux}.source.func = {smux}.OUTPUT_DCAMPS')
        elif src_func.lower() in {'volt', 'v', 'voltage'}:
            self.write(f'{smux}.source.func = {smux}.OUTPUT_DCVOLTS')
        else:
            raise InstrumentParameterError(
                "Source function must be 'current/curr/i' or 'voltage/volt/v'."
            )

    def set_curr_ramp(self, curr: float, dI: float, dt: float, channel: str):
        i0 = self.get_curr(channel)
        ramp_drive(lambda i: self.set_curr(i, channel), i0, curr, dI, dt)

    def set_volt_ramp(self, volt: float, dV: float, dt: float, channel: str):
        v0 = self.get_volt(channel)
        ramp_drive(lambda v: self.set_volt(v, channel), v0, volt, dV, dt)


class K2182(BaseInstrument):
    def fetch(self):
        response = self.query(":fetch?")
        return _parse_float_response(response, ":fetch?")


class K2400(BaseInstrument):
    def connect(self, *, query_delay: Optional[float] = 0.05):
        super().connect()
        if query_delay is not None:
            self._res.query_delay = query_delay
        self.write(':FORM:ELEM VOLT,CURR')

    def set_output_on(self, is_on: bool = True):
        if is_on:
            self.write(':OUTP ON')
        else:
            self.write(':OUTP OFF')

    # -------------------- SOURCE configurations--------------------
    def set_source_func(self, src_func: str):
        if src_func.lower() in {'current', 'curr', 'i'}:
            self.write(':SOUR:FUNC CURR')
        elif src_func.lower() in {'voltage', 'volt', 'v'}:
            self.write(':SOUR:FUNC VOLT')
        else:
            raise InstrumentParameterError(
                ":SOUR:FUNC must be 'current/curr/i' or 'voltage/volt/v'."
            )

    def set_volt_range(self, vrange: float):
        if vrange < -210 or vrange > 210:
            raise InstrumentParameterError(
                ':SOUR:VOLT:RANG must be in [-210, 210] V.'
            )
        self.write(f':SOUR:VOLT:RANG {vrange}')

    def set_curr_range(self, irange: float):
        if irange < -1.05 or irange > 1.05:
            raise InstrumentParameterError(
                ':SOUR:CURR:RANG must be in [-1.05, 1.05] A.'
            )
        self.write(f':SOUR:CURR:RANGE {irange}')

    def set_volt_range_auto(self, is_auto: bool = True):
        if is_auto:
            self.write(':SOUR:VOLT:RANG:AUTO ON')
        else:
            self.write(':SOUR:VOLT:RANG:AUTO OFF')

    def set_curr_range_auto(self, is_auto: bool = True):
        if is_auto:
            self.write(':SOUR:CURR:RANG:AUTO ON')
        else:
            self.write(':SOUR:CURR:RANG:AUTO OFF')

    def set_curr_comp(self, icomp: float):
        if icomp < -1.05 or icomp > 1.05:
            raise InstrumentParameterError(
                ':CURR:PROT must be in [-1.05, 1.05] A.'
            )
        self.write(f':CURR:PROT {icomp}')

    def set_volt_comp(self, vcomp: float):
        if vcomp < -210 or vcomp > 210:
            raise InstrumentParameterError(
                ':VOLT:PROT must be in [-210, 210] V.'
            )
        self.write(f':VOLT:PROT {vcomp}')

    # -------------------- SENSE subsystem --------------------
    def set_form_elem(self, items: Sequence[str]):
        item_list = ','.join(items)
        self.write(f':FORM:ELEM {item_list}')

    def read_data(self) -> tuple[float, ...]:
        resp = self.query(':READ?').strip()
        return _parse_float_sequence(resp, ':READ?', sep=',')

    def get_iv(self) -> tuple[float, float]:
        data = self.read_data()

        if len(data) < 2:
            raise InstrumentParseError(
                f"Expected at least 2 values from :READ?, got {len(data)}: {data!r}"
            )

        volt, curr = data[:2]
        return curr, volt

    # -------------------- SOURCE output control --------------------
    def set_curr(self, curr: float):
        if curr < -1.05 or curr > 1.05:
            raise InstrumentParameterError(
                ':SOUR:CURR must be in [-1.05, 1.05] A.'
            )
        self.write(f':SOUR:CURR {curr}')

    def set_volt(self, volt: float):
        if volt < -210 or volt > 210:
            raise InstrumentParameterError(
                ':SOUR:VOLT must be in [-210, 210] V.'
            )
        self.write(f':SOUR:VOLT {volt}')

    def set_curr_ramp(self, curr: float, dI: float, dt: float):
        i0 = _parse_float_response(self.query(':SOUR:CURR?'), ':SOUR:CURR?')
        ramp_drive(self.set_curr, i0, curr, dI, dt)

    def set_volt_ramp(self, volt: float, dV: float, dt: float):
        v0 = _parse_float_response(self.query(':SOUR:VOLT?'), ':SOUR:VOLT?')
        ramp_drive(self.set_volt, v0, volt, dV, dt)
