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
    """Keithley 6221 AC/DC current-source driver.

    Waveform amplitudes are peak values in amperes. The waveform methods below
    intentionally map to individual SCPI settings so experiment code controls
    the command order explicitly.
    """

    WAVE_AMPL_MIN = 2e-12
    WAVE_AMPL_MAX = 105e-3
    WAVE_FREQ_MIN = 1e-3
    WAVE_FREQ_MAX = 100e3
    WAVE_OFFS_MIN = -105e-3
    WAVE_OFFS_MAX = 105e-3

    def __init__(self, visa_address, rm=None):
        super().__init__(visa_address, rm)

    @staticmethod
    def _as_float(value: float, name: str) -> float:
        try:
            out = float(value)
        except (TypeError, ValueError) as e:
            raise InstrumentParameterError(
                f'{name} must be a finite number, got {value!r}.'
            ) from e

        if out != out or out in {float('inf'), float('-inf')}:
            raise InstrumentParameterError(
                f'{name} must be a finite number, got {value!r}.'
            )

        return out

    @classmethod
    def _check_range(
        cls,
        value: float,
        name: str,
        minimum: float,
        maximum: float,
    ) -> float:
        out = cls._as_float(value, name)
        if not minimum <= out <= maximum:
            raise InstrumentParameterError(
                f'{name} must be in [{minimum}, {maximum}], got {value!r}.'
            )
        return out

    @staticmethod
    def _normalize_wave_range_mode(range_mode: str) -> str:
        token = str(range_mode).strip().lower().replace('_', '-')
        if token in {'best', 'best-fixed', 'bestfixed'}:
            return 'BEST'
        if token in {'fixed', 'fix'}:
            return 'FIXED'
        raise InstrumentParameterError(
            "Waveform range mode must be 'best' or 'fixed'."
        )

    @staticmethod
    def _parse_bool_response(resp: str, context: str) -> bool:
        token = resp.strip().upper()
        if token in {'1', 'ON'}:
            return True
        if token in {'0', 'OFF'}:
            return False
        raise InstrumentResponseError(
            f'Unexpected response for {context}: {resp!r}'
        )

    @staticmethod
    def _normalize_phase_marker_line(line: int) -> int:
        if isinstance(line, bool):
            raise InstrumentParameterError(
                'Phase-marker line must be an integer from 1 to 6.'
            )
        try:
            line_int = int(line)
        except (TypeError, ValueError) as e:
            raise InstrumentParameterError(
                'Phase-marker line must be an integer from 1 to 6.'
            ) from e
        if line_int != line or not 1 <= line_int <= 6:
            raise InstrumentParameterError(
                'Phase-marker line must be an integer from 1 to 6.'
            )
        return line_int

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

    def get_curr_range(self) -> float:
        return _parse_float_response(
            self.query('SOUR:CURR:RANG?'),
            'SOUR:CURR:RANG?',
        )

    def set_curr_range_auto(self, is_auto: bool = True):
        if is_auto:
            self.write('SOUR:CURR:RANG:AUTO ON')
        else:
            self.write('SOUR:CURR:RANG:AUTO OFF')

    def clear_source(self):
        self.write('SOUR:CLE')

    # --------------- Waveform source (6221 only) --------------- #
    def set_wave_function(self, function: str) -> None:
        token = str(function).strip().lower()
        mapping = {
            'sin': 'SIN',
            'sine': 'SIN',
            'sinusoid': 'SIN',
            'square': 'SQU',
            'squ': 'SQU',
            'ramp': 'RAMP',
        }
        command_value = mapping.get(token)
        if command_value is None:
            if token.startswith('arb') and token[3:] in {'', '0', '1', '2', '3', '4'}:
                command_value = f'ARB{token[3:]}' if token[3:] else 'ARB'
            else:
                raise InstrumentParameterError(
                    "Wave function must be 'sine', 'square', 'ramp', or 'arb0' to 'arb4'."
                )
        self.write(f'SOUR:WAVE:FUNC {command_value}')

    def get_wave_function(self) -> str:
        return self.query('SOUR:WAVE:FUNC?').strip()

    def set_wave_frequency(self, freq: float) -> None:
        freq = self._check_range(
            freq,
            'waveform frequency',
            self.WAVE_FREQ_MIN,
            self.WAVE_FREQ_MAX,
        )
        self.write(f'SOUR:WAVE:FREQ {freq}')

    def get_wave_frequency(self) -> float:
        return _parse_float_response(
            self.query('SOUR:WAVE:FREQ?'),
            'SOUR:WAVE:FREQ?',
        )

    def set_wave_amplitude(self, ampl: float) -> None:
        ampl = self._check_range(
            ampl,
            'waveform peak amplitude',
            self.WAVE_AMPL_MIN,
            self.WAVE_AMPL_MAX,
        )
        self.write(f'SOUR:WAVE:AMPL {ampl}')

    def get_wave_amplitude(self) -> float:
        """Return waveform peak amplitude in amperes."""
        return _parse_float_response(
            self.query('SOUR:WAVE:AMPL?'),
            'SOUR:WAVE:AMPL?',
        )

    def set_wave_offset(self, offs: float) -> None:
        offs = self._check_range(
            offs,
            'waveform offset',
            self.WAVE_OFFS_MIN,
            self.WAVE_OFFS_MAX,
        )
        self.write(f'SOUR:WAVE:OFFS {offs}')

    def get_wave_offset(self) -> float:
        return _parse_float_response(
            self.query('SOUR:WAVE:OFFS?'),
            'SOUR:WAVE:OFFS?',
        )

    def set_wave_range(self, value: float) -> None:
        """Select the fixed current range used for waveform output.

        ``value`` is the current magnitude that the selected range must
        accommodate, not necessarily one of the instrument's discrete range
        values. The Model 6221 selects the lowest range that can source it.
        This setting is used when waveform ranging is set to ``FIXED`` and the
        waveform is subsequently armed.
        """
        value = self._check_range(
            value,
            'waveform range value',
            -105e-3,
            105e-3,
        )
        self.write(f'SOUR:CURR:RANG {value}')

    def set_wave_range_mode(self, range_mode: str) -> None:
        """Set BEST or FIXED waveform ranging before the wave is armed.

        The Model 6221 rejects this command with error +404 while a waveform
        is armed.
        """
        mode = self._normalize_wave_range_mode(range_mode)
        self.write(f'SOUR:WAVE:RANG {mode}')

    def get_wave_range_mode(self) -> str:
        response = self.query('SOUR:WAVE:RANG?').strip().upper()
        if response.startswith('BEST'):
            return 'best'
        if response.startswith('FIX'):
            return 'fixed'
        raise InstrumentResponseError(
            f'Unexpected response for SOUR:WAVE:RANG?: {response!r}'
        )

    def set_wave_phase_marker_on(self, is_on: bool = True) -> None:
        if not isinstance(is_on, bool):
            raise InstrumentParameterError('Phase-marker state must be a bool.')
        self.write(f'SOUR:WAVE:PMAR:STAT {"ON" if is_on else "OFF"}')

    def set_wave_phase_marker(self, phase: float) -> None:
        phase = self._check_range(phase, 'phase-marker angle', 0, 360)
        self.write(f'SOUR:WAVE:PMAR {phase}')

    def set_wave_phase_marker_line(self, line: int) -> None:
        line_int = self._normalize_phase_marker_line(line)
        self.write(f'SOUR:WAVE:PMAR:OLIN {line_int}')

    def get_wave_phase_marker_on(self) -> bool:
        return self._parse_bool_response(
            self.query('SOUR:WAVE:PMAR:STAT?'),
            'SOUR:WAVE:PMAR:STAT?',
        )

    def get_wave_phase_marker(self) -> float:
        return _parse_float_response(
            self.query('SOUR:WAVE:PMAR?'),
            'SOUR:WAVE:PMAR?',
        )

    def get_wave_phase_marker_line(self) -> int:
        value = _parse_float_response(
            self.query('SOUR:WAVE:PMAR:OLIN?'),
            'SOUR:WAVE:PMAR:OLIN?',
        )
        return int(value)

    def set_wave_duration_time(self, duration: float | str) -> None:
        if isinstance(duration, str) and duration.strip().lower() in {
            'inf', 'infinite', 'infinity',
        }:
            self.write('SOUR:WAVE:DUR:TIME INF')
            return

        duration = self._check_range(
            duration,
            'waveform duration',
            100e-9,
            999999.999,
        )
        self.write(f'SOUR:WAVE:DUR:TIME {duration}')

    def set_wave_duration_cycles(self, cycles: float | str) -> None:
        if isinstance(cycles, str) and cycles.strip().lower() in {
            'inf', 'infinite', 'infinity',
        }:
            self.write('SOUR:WAVE:DUR:CYCL INF')
            return

        cycles = self._check_range(
            cycles,
            'waveform duration in cycles',
            0.001,
            99999999900,
        )
        self.write(f'SOUR:WAVE:DUR:CYCL {cycles}')

    def get_wave_duration_time(self) -> float:
        return _parse_float_response(
            self.query('SOUR:WAVE:DUR:TIME?'),
            'SOUR:WAVE:DUR:TIME?',
        )

    def get_wave_duration_cycles(self) -> float:
        return _parse_float_response(
            self.query('SOUR:WAVE:DUR:CYCL?'),
            'SOUR:WAVE:DUR:CYCL?',
        )

    def arm_waveform(self) -> None:
        self.write('SOUR:WAVE:ARM')

    def start_waveform(self) -> None:
        self.write('SOUR:WAVE:INIT')

    def arm_and_trigger_waveform(self) -> None:
        self.arm_waveform()
        self.start_waveform()

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

    def set_volt_range_auto(
        self,
        is_auto: bool,
        channel: str,
    ) -> None:
        """Enable or disable voltage-source autoranging."""
        if not isinstance(is_auto, bool):
            raise InstrumentParameterError('Auto-range state must be a bool.')
        smux = self._ch2smux(channel)
        state = f'{smux}.AUTORANGE_ON' if is_auto else f'{smux}.AUTORANGE_OFF'
        self.write(f'{smux}.source.autorangev = {state}')

    def set_curr_range_auto(
        self,
        is_auto: bool,
        channel: str,
    ) -> None:
        """Enable or disable current-source autoranging."""
        if not isinstance(is_auto, bool):
            raise InstrumentParameterError('Auto-range state must be a bool.')
        smux = self._ch2smux(channel)
        state = f'{smux}.AUTORANGE_ON' if is_auto else f'{smux}.AUTORANGE_OFF'
        self.write(f'{smux}.source.autorangei = {state}')

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

    def initialize_channel(
        self,
        source_mode: str,
        sense_mode: str,
        source_range: float,
        sense_limit: float,
        channel: str,
        output_on: bool = False,
    ) -> None:
        """Initialize one SMU channel with a zero source level.

        The channel output is switched off before changing its source mode,
        sense mode, source range, and sense limit. The selected source level
        is then set to zero. The output is enabled at the end only when
        ``output_on`` is ``True``.

        Args:
            source_mode: ``'current'``/``'curr'``/``'i'`` or
                ``'voltage'``/``'volt'``/``'v'``.
            sense_mode: ``'2-wire'``/``'local'`` or
                ``'4-wire'``/``'remote'``.
            source_range: Current range in A or voltage range in V, selected
                automatically according to ``source_mode``.
            sense_limit: Voltage compliance in V for current-source mode, or
                current compliance in A for voltage-source mode.
            channel: SMU channel, ``'a'`` or ``'b'``.
            output_on: Whether to enable the channel after initialization.
                Defaults to ``False``.
        """
        mode = str(source_mode).strip().lower()
        sense = str(sense_mode).strip().lower()

        if mode in {'curr', 'i', 'current'}:
            mode = 'current'
        elif mode in {'volt', 'v', 'voltage'}:
            mode = 'voltage'
        else:
            raise InstrumentParameterError(
                "Source mode must be 'current/curr/i' or 'voltage/volt/v'."
            )

        if sense not in {
            '4-wire', '4w', '4wire', 'remote',
            '2-wire', '2w', '2wire', 'local',
        }:
            raise InstrumentParameterError(
                "Sense mode must be '2-wire/local' or '4-wire/remote'."
            )

        try:
            source_range = float(source_range)
            sense_limit = float(sense_limit)
        except (TypeError, ValueError) as e:
            raise InstrumentParameterError(
                'Source range and sense limit must be finite numbers.'
            ) from e

        if (
            source_range != source_range
            or source_range in {float('inf'), float('-inf')}
            or source_range <= 0
        ):
            raise InstrumentParameterError(
                'Source range must be a finite number greater than zero.'
            )

        if (
            sense_limit != sense_limit
            or sense_limit in {float('inf'), float('-inf')}
            or sense_limit <= 0
        ):
            raise InstrumentParameterError(
                'Sense limit must be a finite number greater than zero.'
            )

        if not isinstance(output_on, bool):
            raise InstrumentParameterError(
                'Output state must be a bool.'
            )

        # Validate the channel before issuing any command.
        self._ch2smux(channel)

        # Keep the output disabled while changing the source configuration.
        self.set_output_on(False, channel)
        self.set_source_func(mode, channel)
        self.set_sense_mode(sense, channel)

        if mode == 'current':
            self.set_curr_range(source_range, channel)
            self.set_volt_limit(sense_limit, channel)
            self.set_curr(0, channel)
        else:
            self.set_volt_range(source_range, channel)
            self.set_curr_limit(sense_limit, channel)
            self.set_volt(0, channel)

        # Apply the requested output state only after the source level is zero.
        self.set_output_on(output_on, channel)

    def configure_output(
        self,
        source_mode: str,
        sense_mode: str,
        source_range: float,
        sense_limit: float,
        channel: str,
        output_on: bool = False,
    ) -> None:
        """Compatibility alias for :meth:`initialize_channel`."""
        self.initialize_channel(
            source_mode=source_mode,
            sense_mode=sense_mode,
            source_range=source_range,
            sense_limit=sense_limit,
            channel=channel,
            output_on=output_on,
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


class K2461(BaseInstrument):
    """Keithley 2461 High-Current SourceMeter driver using SCPI.

    Notes
    -----
    The 2461 has one SMU channel only.

    This driver assumes the 2461 is using the SCPI command set.
    """

    # -------------------- source level limits --------------------
    VOLT_MIN = -105.0
    VOLT_MAX = 105.0

    # DC source current limit. Pulse mode can go higher.
    CURR_MIN = -7.35
    CURR_MAX = 7.35

    # -------------------- source range limits --------------------
    VOLT_RANGE_MIN = 0.0
    VOLT_RANGE_MAX = 100.0

    CURR_RANGE_MIN = 0.0
    CURR_RANGE_MAX = 10.0

    # -------------------- source limit / compliance limits --------------------
    # Current limit when sourcing voltage: :SOUR:VOLT:ILIM <A>
    CURR_LIMIT_MIN = 100e-9
    CURR_LIMIT_MAX = 7.35

    # Voltage limit when sourcing current: :SOUR:CURR:VLIM <V>
    VOLT_LIMIT_MIN = 20e-3
    VOLT_LIMIT_MAX = 105.0

    # -------------------- measure range limits --------------------
    MEAS_CURR_RANGE_MIN = 1e-6
    MEAS_CURR_RANGE_MAX = 10.0

    MEAS_VOLT_RANGE_MIN = 0.2
    MEAS_VOLT_RANGE_MAX = 100.0

    MEAS_RES_RANGE_MIN = 2.0
    MEAS_RES_RANGE_MAX = 200e6

    def __init__(self, visa_address, rm=None):
        super().__init__(visa_address, rm)

    def connect(
        self,
        *,
        timeout_ms: int | None = 10000,
        query_delay: Optional[float] = 0.05,
        configure_ascii: bool = True,
    ) -> None:
        """Open VISA session and set common communication options."""
        super().connect()

        if self._res is not None:
            if timeout_ms is not None:
                self._res.timeout = int(timeout_ms)

            if query_delay is not None:
                self._res.query_delay = query_delay

            self._res.read_termination = "\n"
            self._res.write_termination = "\n"

        if configure_ascii:
            self.write(":FORM:DATA ASCii")
            self.write(":FORM:ASCii:PRECision 12")

    # ============================================================
    # Helpers
    # ============================================================

    @staticmethod
    def _as_float(value: float, name: str) -> float:
        try:
            out = float(value)
        except (TypeError, ValueError) as e:
            raise InstrumentParameterError(
                f"{name} must be a finite number, got {value!r}."
            ) from e

        if out != out or out in (float("inf"), float("-inf")):
            raise InstrumentParameterError(
                f"{name} must be a finite number, got {value!r}."
            )

        return out

    @classmethod
    def _check_range(cls, value: float, name: str, lo: float, hi: float) -> float:
        out = cls._as_float(value, name)

        if not (lo <= out <= hi):
            raise InstrumentParameterError(
                f"{name} must be in [{lo}, {hi}], got {value!r}."
            )

        return out

    @staticmethod
    def _onoff(is_on: bool) -> str:
        return "ON" if bool(is_on) else "OFF"

    @staticmethod
    def _parse_bool_response(resp: str, context: str) -> bool:
        token = resp.strip().upper()

        if token in {"1", "ON", "TRUE"}:
            return True

        if token in {"0", "OFF", "FALSE"}:
            return False

        raise InstrumentResponseError(
            f"Unexpected response for {context}: {resp!r}"
        )

    @staticmethod
    def _normalize_source_func(src_func: str) -> str:
        token = str(src_func).strip().lower()

        if token in {"current", "curr", "i"}:
            return "CURRent"

        if token in {"voltage", "volt", "v"}:
            return "VOLTage"

        raise InstrumentParameterError(
            "Source function must be 'current/curr/i' or 'voltage/volt/v'."
        )

    @staticmethod
    def _normalize_measure_func(meas_func: str) -> str:
        token = str(meas_func).strip().lower()

        if token in {"current", "curr", "i"}:
            return "CURRent"

        if token in {"voltage", "volt", "v"}:
            return "VOLTage"

        if token in {"resistance", "res", "r", "ohm", "ohms"}:
            return "RESistance"

        raise InstrumentParameterError(
            "Measure function must be 'current/curr/i', "
            "'voltage/volt/v', or 'resistance/res/r/ohm'."
        )

    @staticmethod
    def _normalize_terminal(terminal: str) -> str:
        token = str(terminal).strip().lower()

        if token in {"front", "fron", "f"}:
            return "FRONt"

        if token in {"rear", "back", "r"}:
            return "REAR"

        raise InstrumentParameterError(
            "Terminal must be 'front' or 'rear'."
        )

    @staticmethod
    def _normalize_sense_mode(sense_mode: str) -> bool:
        token = str(sense_mode).strip().lower()

        if token in {"4-wire", "4w", "4wire", "remote", "rem"}:
            return True

        if token in {"2-wire", "2w", "2wire", "local", "loc"}:
            return False

        raise InstrumentParameterError(
            "Sense mode must be '2-wire/local' or '4-wire/remote'."
        )

    @staticmethod
    def _normalize_output_off_mode(mode: str) -> str:
        token = str(mode).strip().lower().replace("_", "-")

        if token in {"normal", "norm"}:
            return "NORMal"

        if token in {
            "high-z",
            "highz",
            "hi-z",
            "hiz",
            "hiimpedance",
            "high-impedance",
        }:
            return "HIMPedance"

        if token in {"zero", "0"}:
            return "ZERO"

        if token in {"guard", "guar"}:
            return "GUARd"

        raise InstrumentParameterError(
            "Output-off mode must be 'normal', 'high-z', 'zero', or 'guard'."
        )

    # ============================================================
    # Identification / status
    # ============================================================

    def get_idn(self) -> str:
        return self.query("*IDN?").strip()

    def reset(self) -> None:
        self.write("*RST")

    def clear_status(self) -> None:
        self.write("*CLS")

    def get_error(self) -> str:
        return self.query(":SYST:ERR?").strip()

    def get_errors(self, max_count: int = 20) -> list[str]:
        errors: list[str] = []

        for _ in range(max_count):
            err = self.get_error()
            errors.append(err)

            if err.startswith("0") or "No error" in err:
                break

        return errors

    # ============================================================
    # Terminal selection
    # ============================================================

    def set_terminal(self, terminal: str) -> None:
        term = self._normalize_terminal(terminal)
        self.write(f":ROUT:TERM {term}")

    def get_terminal(self) -> str:
        return self.query(":ROUT:TERM?").strip()

    # ============================================================
    # Source configuration
    # ============================================================

    def set_source_func(self, src_func: str) -> None:
        func = self._normalize_source_func(src_func)
        self.write(f":SOUR:FUNC {func}")

    def get_source_func(self) -> str:
        resp = self.query(":SOUR:FUNC?").strip().upper()

        if resp.startswith("CURR"):
            return "current"

        if resp.startswith("VOLT"):
            return "voltage"

        raise InstrumentResponseError(
            f"Unexpected response for :SOUR:FUNC?: {resp!r}"
        )

    def set_volt(self, volt: float) -> None:
        volt = self._check_range(
            volt,
            "source voltage",
            self.VOLT_MIN,
            self.VOLT_MAX,
        )
        self.write(f":SOUR:VOLT {volt}")

    def get_source_volt(self) -> float:
        return _parse_float_response(
            self.query(":SOUR:VOLT?"),
            ":SOUR:VOLT?",
        )

    def set_curr(self, curr: float) -> None:
        curr = self._check_range(
            curr,
            "source current",
            self.CURR_MIN,
            self.CURR_MAX,
        )
        self.write(f":SOUR:CURR {curr}")

    def get_source_curr(self) -> float:
        return _parse_float_response(
            self.query(":SOUR:CURR?"),
            ":SOUR:CURR?",
        )

    # ============================================================
    # Source range
    # ============================================================

    def set_volt_range(self, volt_range: float) -> None:
        volt_range = self._check_range(
            volt_range,
            "source voltage range",
            self.VOLT_RANGE_MIN,
            self.VOLT_RANGE_MAX,
        )

        if volt_range == 0:
            raise InstrumentParameterError("source voltage range must be > 0.")

        self.write(f":SOUR:VOLT:RANG {volt_range}")

    def get_volt_range(self) -> float:
        return _parse_float_response(
            self.query(":SOUR:VOLT:RANG?"),
            ":SOUR:VOLT:RANG?",
        )

    def set_curr_range(self, curr_range: float) -> None:
        curr_range = self._check_range(
            curr_range,
            "source current range",
            self.CURR_RANGE_MIN,
            self.CURR_RANGE_MAX,
        )

        if curr_range == 0:
            raise InstrumentParameterError("source current range must be > 0.")

        self.write(f":SOUR:CURR:RANG {curr_range}")

    def get_curr_range(self) -> float:
        return _parse_float_response(
            self.query(":SOUR:CURR:RANG?"),
            ":SOUR:CURR:RANG?",
        )

    def set_volt_range_auto(self, is_auto: bool = True) -> None:
        self.write(f":SOUR:VOLT:RANG:AUTO {self._onoff(is_auto)}")

    def set_curr_range_auto(self, is_auto: bool = True) -> None:
        self.write(f":SOUR:CURR:RANG:AUTO {self._onoff(is_auto)}")

    def get_volt_range_auto(self) -> bool:
        return self._parse_bool_response(
            self.query(":SOUR:VOLT:RANG:AUTO?"),
            ":SOUR:VOLT:RANG:AUTO?",
        )

    def get_curr_range_auto(self) -> bool:
        return self._parse_bool_response(
            self.query(":SOUR:CURR:RANG:AUTO?"),
            ":SOUR:CURR:RANG:AUTO?",
        )

    # ============================================================
    # Source limit / compliance
    # ============================================================

    def set_curr_limit(self, curr_limit: float) -> None:
        """Set current limit when sourcing voltage.

        SCPI:
            :SOUR:VOLT:ILIM <A>
        """
        curr_limit = self._check_range(
            curr_limit,
            "current limit",
            self.CURR_LIMIT_MIN,
            self.CURR_LIMIT_MAX,
        )
        self.write(f":SOUR:VOLT:ILIM {curr_limit}")

    def get_curr_limit(self) -> float:
        return _parse_float_response(
            self.query(":SOUR:VOLT:ILIM?"),
            ":SOUR:VOLT:ILIM?",
        )

    def set_volt_limit(self, volt_limit: float) -> None:
        """Set voltage limit when sourcing current.

        SCPI:
            :SOUR:CURR:VLIM <V>
        """
        volt_limit = self._check_range(
            volt_limit,
            "voltage limit",
            self.VOLT_LIMIT_MIN,
            self.VOLT_LIMIT_MAX,
        )
        self.write(f":SOUR:CURR:VLIM {volt_limit}")

    def get_volt_limit(self) -> float:
        return _parse_float_response(
            self.query(":SOUR:CURR:VLIM?"),
            ":SOUR:CURR:VLIM?",
        )

    def get_curr_limit_tripped(self) -> bool:
        return self._parse_bool_response(
            self.query(":SOUR:VOLT:ILIM:TRIP?"),
            ":SOUR:VOLT:ILIM:TRIP?",
        )

    def get_volt_limit_tripped(self) -> bool:
        return self._parse_bool_response(
            self.query(":SOUR:CURR:VLIM:TRIP?"),
            ":SOUR:CURR:VLIM:TRIP?",
        )

    # ============================================================
    # Output control
    # ============================================================

    def set_output_on(self, is_on: bool = True) -> None:
        self.write(f":OUTP {self._onoff(is_on)}")

    def get_output_on(self) -> bool:
        return self._parse_bool_response(
            self.query(":OUTP?"),
            ":OUTP?",
        )

    def set_output_off_mode(
        self,
        mode: str,
        src_func: str | None = None,
    ) -> None:
        """Set output-off mode.

        Parameters
        ----------
        mode:
            'normal', 'high-z', 'zero', or 'guard'.

        src_func:
            If None, apply to both voltage-source and current-source functions.
            Otherwise apply only to 'voltage' or 'current'.
        """
        mode_norm = self._normalize_output_off_mode(mode)

        if src_func is None:
            funcs = ("VOLTage", "CURRent")
        else:
            funcs = (self._normalize_source_func(src_func),)

        for func in funcs:
            self.write(f":OUTP:{func}:SMOD {mode_norm}")

    # ============================================================
    # Measure configuration
    # ============================================================

    def set_measure_func(self, meas_func: str) -> None:
        func = self._normalize_measure_func(meas_func)
        self.write(f':SENS:FUNC "{func}"')

    def get_measure_func(self) -> str:
        resp = self.query(":SENS:FUNC?").strip().upper()

        if "CURR" in resp:
            return "current"

        if "VOLT" in resp:
            return "voltage"

        if "RES" in resp:
            return "resistance"

        raise InstrumentResponseError(
            f"Unexpected response for :SENS:FUNC?: {resp!r}"
        )

    def set_measure_range(
        self,
        meas_range: float,
        meas_func: str | None = None,
    ) -> None:
        if meas_func is None:
            meas_func = self.get_measure_func()

        func = self._normalize_measure_func(meas_func)

        if func == "CURRent":
            lo, hi = self.MEAS_CURR_RANGE_MIN, self.MEAS_CURR_RANGE_MAX
            name = "measure current range"
        elif func == "VOLTage":
            lo, hi = self.MEAS_VOLT_RANGE_MIN, self.MEAS_VOLT_RANGE_MAX
            name = "measure voltage range"
        else:
            lo, hi = self.MEAS_RES_RANGE_MIN, self.MEAS_RES_RANGE_MAX
            name = "measure resistance range"

        meas_range = self._check_range(meas_range, name, lo, hi)
        self.write(f":SENS:{func}:RANG {meas_range}")

    def get_measure_range(
        self,
        meas_func: str | None = None,
    ) -> float:
        if meas_func is None:
            meas_func = self.get_measure_func()

        func = self._normalize_measure_func(meas_func)

        return _parse_float_response(
            self.query(f":SENS:{func}:RANG?"),
            f":SENS:{func}:RANG?",
        )

    def set_measure_range_auto(
        self,
        is_auto: bool = True,
        meas_func: str | None = None,
    ) -> None:
        if meas_func is None:
            funcs = ("CURRent", "VOLTage", "RESistance")
        else:
            funcs = (self._normalize_measure_func(meas_func),)

        for func in funcs:
            self.write(f":SENS:{func}:RANG:AUTO {self._onoff(is_auto)}")

    def set_measure_nplc(
        self,
        nplc: float,
        meas_func: str | None = None,
    ) -> None:
        nplc = self._check_range(nplc, "NPLC", 0.0005, 12.0)

        if meas_func is None:
            meas_func = self.get_measure_func()

        func = self._normalize_measure_func(meas_func)
        self.write(f":SENS:{func}:NPLC {nplc}")

    def set_sense_mode(
        self,
        sense_mode: str,
        meas_func: str | None = None,
    ) -> None:
        """Set local/remote sense.

        Parameters
        ----------
        sense_mode:
            '2-wire' / 'local' or '4-wire' / 'remote'.

        meas_func:
            If None, apply to current, voltage, and resistance measurement
            functions.
        """
        remote = self._normalize_sense_mode(sense_mode)
        state = self._onoff(remote)

        if meas_func is None:
            funcs = ("CURRent", "VOLTage", "RESistance")
        else:
            funcs = (self._normalize_measure_func(meas_func),)

        for func in funcs:
            self.write(f":SENS:{func}:RSEN {state}")

    def get_sense_mode(
        self,
        meas_func: str = "voltage",
    ) -> str:
        func = self._normalize_measure_func(meas_func)

        is_remote = self._parse_bool_response(
            self.query(f":SENS:{func}:RSEN?"),
            f":SENS:{func}:RSEN?",
        )

        return "remote" if is_remote else "local"

    # ============================================================
    # Measurement readout
    # ============================================================

    def read_data(
        self,
        buffer_name: str = "defbuffer1",
        elements: Sequence[str] = ("READ",),
    ) -> tuple[float, ...]:
        elem_list = ", ".join(elements)
        cmd = f':READ? "{buffer_name}", {elem_list}'
        resp = self.query(cmd).strip()
        return _parse_float_sequence(resp, cmd, sep=",")

    def fetch_data(
        self,
        buffer_name: str = "defbuffer1",
        elements: Sequence[str] = ("READ",),
    ) -> tuple[float, ...]:
        elem_list = ", ".join(elements)
        cmd = f':FETC? "{buffer_name}", {elem_list}'
        resp = self.query(cmd).strip()
        return _parse_float_sequence(resp, cmd, sep=",")

    def measure_read(self) -> float:
        values = self.read_data(elements=("READ",))

        if len(values) < 1:
            raise InstrumentParseError(
                f"Expected one reading from :READ?, got {values!r}"
            )

        return values[0]

    def get_curr(self) -> float:
        cmd = ':MEAS:CURR? "defbuffer1", READ'
        return _parse_float_response(self.query(cmd), cmd)

    def get_volt(self) -> float:
        cmd = ':MEAS:VOLT? "defbuffer1", READ'
        return _parse_float_response(self.query(cmd), cmd)

    def get_resistance(self) -> float:
        cmd = ':MEAS:RES? "defbuffer1", READ'
        return _parse_float_response(self.query(cmd), cmd)

    def get_iv(self) -> tuple[float, float]:
        """Return (current_A, voltage_V).

        If source and measure functions are complementary, this uses one
        :READ? call and returns (I, V). Otherwise, it falls back to separate
        current and voltage measurements.
        """
        src_func = self.get_source_func()
        meas_func = self.get_measure_func()

        if src_func != meas_func:
            data = self.read_data(elements=("READ", "SOUR"))

            if len(data) < 2:
                raise InstrumentParseError(
                    f"Expected READ and SOUR values from :READ?, got {data!r}"
                )

            reading, source = data[:2]

            if src_func == "voltage" and meas_func == "current":
                return reading, source

            if src_func == "current" and meas_func == "voltage":
                return source, reading

        curr = self.get_curr()
        volt = self.get_volt()
        return curr, volt

    # ============================================================
    # Convenience setup wrappers
    # ============================================================

    def configure_voltage_source(
        self,
        volt: float,
        curr_limit: float,
        *,
        volt_range: float | str | None = None,
        curr_measure_range: float | str | None = "auto",
        sense_mode: str | None = None,
        terminal: str | None = None,
    ) -> None:
        """Configure source-voltage / measure-current mode."""
        if terminal is not None:
            self.set_terminal(terminal)

        self.set_source_func("voltage")
        self.set_measure_func("current")

        if volt_range is None:
            pass
        elif isinstance(volt_range, str) and volt_range.strip().lower() == "auto":
            self.set_volt_range_auto(True)
        else:
            self.set_volt_range(float(volt_range))

        if curr_measure_range is None:
            pass
        elif (
            isinstance(curr_measure_range, str)
            and curr_measure_range.strip().lower() == "auto"
        ):
            self.set_measure_range_auto(True, "current")
        else:
            self.set_measure_range(float(curr_measure_range), "current")

        if sense_mode is not None:
            self.set_sense_mode(sense_mode)

        self.set_curr_limit(curr_limit)
        self.set_volt(volt)

    def configure_current_source(
        self,
        curr: float,
        volt_limit: float,
        *,
        curr_range: float | str | None = None,
        volt_measure_range: float | str | None = "auto",
        sense_mode: str | None = None,
        terminal: str | None = None,
    ) -> None:
        """Configure source-current / measure-voltage mode."""
        if terminal is not None:
            self.set_terminal(terminal)

        self.set_source_func("current")
        self.set_measure_func("voltage")

        if curr_range is None:
            pass
        elif isinstance(curr_range, str) and curr_range.strip().lower() == "auto":
            self.set_curr_range_auto(True)
        else:
            self.set_curr_range(float(curr_range))

        if volt_measure_range is None:
            pass
        elif (
            isinstance(volt_measure_range, str)
            and volt_measure_range.strip().lower() == "auto"
        ):
            self.set_measure_range_auto(True, "voltage")
        else:
            self.set_measure_range(float(volt_measure_range), "voltage")

        if sense_mode is not None:
            self.set_sense_mode(sense_mode)

        self.set_volt_limit(volt_limit)
        self.set_curr(curr)

    # ============================================================
    # Ramp helpers
    # ============================================================

    def set_curr_ramp(
        self,
        curr: float,
        dI: float,
        dt: float,
    ) -> None:
        i0 = self.get_source_curr()
        ramp_drive(lambda i: self.set_curr(i), i0, curr, dI, dt)

    def set_volt_ramp(
        self,
        volt: float,
        dV: float,
        dt: float,
    ) -> None:
        v0 = self.get_source_volt()
        ramp_drive(lambda v: self.set_volt(v), v0, volt, dV, dt)
