from ._core import BaseInstrument, _validate_enum_attr
from typing import Any, Sequence, Iterator
import time
import pyvisa
import asyncio
import numpy as np

class LockInError(Exception):
    """Generic lock-in amplifier error."""

class LockInHarmonicsError(LockInError):
    """Raised when setting the (sub-)harmonic measurement without turning on the harmonics option."""

class NF5650(BaseInstrument):
    _DET_MODE = {'SING', 'DUAL1', 'DUAL2', 'CASC', 'SINGLE', 'CASCADE'}
    _REF_SRC  = {'RINP', 'IOSC',  'SINP'}
    _REF_TYPE = {'SIN',  'TPOS',  'TNEG'}
    _SIG_COUP = {'DC', 'AC'}
    _SIG_GND  = {'FLO', 'GRO', 'FLOAT', 'GROUND'}
    _SIG_IV_GAIN = {'IE6', 'IE8'}
    _SIG_CONN = {'I', 'A', 'AB'}
    _PSD = {'PRI', 'SEC'}
    _SENSE_DR = {'HIGH', 'MED', 'LOW'}
    _SENSE_FILTER_SLOPE = {'6', '12', '18', '24'}
    _SENSE_FILTER_TYPE = {'MOV', 'EXP'}
    _SRC_IOSC = {'PRI', 'SEC', 'PRIMARY', 'SECONDARY'}
    _CALC_FORM = {
        1: {
            'SING':  {'REAL', 'MLIN', 'NOIS', 'AUX1'},
            'DUAL1': {'REAL', 'MLIN', 'IMAG', 'PHAS', 'NOIS', 'AUX1', 'REAL2', 'MLIN2'},
            'DUAL2': {'REAL', 'MLIN', 'IMAG', 'PHAS', 'NOIS', 'AUX1', 'REAL2', 'MLIN2'},
            'CASC':  {'REAL', 'MLIN', 'IMAG', 'PHAS', 'NOIS', 'AUX1', 'REAL2', 'MLIN2'},
        },
        2: {
            'SING':  {'IMAG', 'PHAS', 'AUX1', 'AUX2'},
            'DUAL1': {'IMAG', 'PHAS', 'AUX1', 'AUX2', 'REAL2', 'MLIN2', 'IMAG2', 'PHAS2'},
            'DUAL2': {'IMAG', 'PHAS', 'AUX1', 'AUX2', 'REAL2', 'MLIN2', 'IMAG2', 'PHAS2'},
            'CASC':  {'IMAG', 'PHAS', 'AUX1', 'AUX2', 'REAL2', 'MLIN2', 'IMAG2', 'PHAS2'},
        },
        3 : {
            'SING':  {'REAL', 'MLIN'},
            'DUAL1': {'REAL', 'MLIN', 'IMAG', 'PHAS', 'REAL2', 'MLIN2'},
            'DUAL2': {'REAL', 'MLIN', 'IMAG', 'PHAS', 'REAL2', 'MLIN2'},
            'CASC':  {'REAL', 'MLIN', 'IMAG', 'PHAS', 'REAL2', 'MLIN2'},
        },
        4 : {
            'SING':  {'IMAG', 'PHAS'},
            'DUAL1': {'IMAG', 'PHAS', 'REAL2', 'MLIN2', 'IMAG2', 'PHAS2'},
            'DUAL2': {'IMAG', 'PHAS', 'REAL2', 'MLIN2', 'IMAG2', 'PHAS2'},
            'CASC':  {'IMAG', 'PHAS', 'REAL2', 'MLIN2', 'IMAG2', 'PHAS2'},
        }
    }
    _SENSE_DATA = {
        'STAT': 1, 'STATUS': 1,
        'DATA1': 2, 'DATA2': 4, 'DATA3': 8, 'DATA4': 16,
        'FREQ': 32
    }
    
    def __init__(self, visa_address, rm = None):
        super().__init__(visa_address, rm)
    
    def connect(self):
        super().connect()
        visa_type = self._res.get_visa_attribute(pyvisa.constants.VI_ATTR_INTF_TYPE)
        if visa_type == pyvisa.constants.VI_INTF_TCPIP:
            self._res.read_termination = "\n"
            self._res.write_termination = "\n"
    
    # ---------------- :DET ----------------
    def set_detect_mode(self, mode: str) -> None:
        token = _validate_enum_attr(mode, self._DET_MODE, 'DET_MODE')
        self.write(f':DET {token}')
    
    def get_detect_mode(self) -> str:
        return self.query(':DET?').strip().upper()
    
    # ---------------- :FREQ1:HARM ----------------
    def set_priPSD_harmonics_on(self, is_on: bool = True) -> None:
        if is_on:
            self.write(':FREQ:HARM ON')
        else:
            self.write(':FREQ:HARM OFF')
    
    def get_priPSD_harmonics_on(self) -> bool:
        state = self.query(':FREQ:HARM?').strip()
        if state == '1':
            return True
        elif state == '0':
            return False
        else:
            raise ValueError(f'An unknown response is obtained while querying :FREQ:HARM? : {state}')
    
    def set_priPSD_harmonics(self, numerator: int, denominator: int = 1) -> None:
        if (numerator < 1 or numerator > 63) or (denominator < 1 or denominator > 63):
            raise ValueError('The numerator and denominator must be INT in [1, 63]')
        self.write(f':FREQ:MULT {numerator}')
        self.write(f':FREQ:SMUL {denominator}')
    
    def get_priPSD_harmonics(self) -> tuple[int, int]:
        numerator = int(self.query(':FREQ:MULT?'))
        denominator = int(self.query(':FREQ:SMUL?'))
        return numerator, denominator
    
    # ---------------- :FREQ2:HARM ----------------
    def set_secPSD_harmonics_on(self, is_on: bool = True) -> None:
        if is_on:
            self.write(':FREQ2:HARM ON')
        else:
            self.write(':FREQ2:HARM OFF')

    def get_secPSD_harmonics_on(self) -> bool:
        state = self.query(':FREQ2:HARM?').strip()
        if state == '1':
            return True
        elif state == '0':
            return False
        else:
            raise ValueError(f'An unknown response is obtained while querying :FREQ2:HARM? : {state}')
    
    def set_secPSD_harmonics(self, numerator: int) -> None:
        if numerator < 1 or numerator > 63:
            raise ValueError('The numerator and denominator must be INT in [1, 63]')
        # if not self.get_secPSD_harmonics_on():
        #     raise LockInHarmonicsError('You MUST turn on the harmonics measurement for secondary PSD.')
        self.write(f':FREQ2:MULT {numerator}')
    
    def get_secPSD_harmonics(self) -> int:
        return int(self.query(':FREQ2:MULT?'))

    # ---------------- Reference Signal ----------------
    def set_ref_src(self, ref_src: str) -> None:
        token = _validate_enum_attr(ref_src, self._REF_SRC, 'REF_SRC')
        self.write(f':ROUT2 {token}')
    
    def get_ref_src(self) -> str:
        return self.query(':ROUT2?').strip()
    
    def set_ref_type(self, ref_type: str) -> None:
        token = _validate_enum_attr(ref_type, self._REF_TYPE, 'REF_TYPE')
        self.write(f':INP2:TYPE {token}')
    
    def get_ref_type(self) -> str:
        return self.query(':INP2:TYPE?').strip()
    
    # ---------------- Input Signal ----------------
    def set_sig_coupling(self, coupling: str) -> None:
        token = _validate_enum_attr(coupling, self._SIG_COUP, 'SIG_COUP')
        self.write(f':INP:COUP {token}')
    
    def get_sig_coupling(self) -> str:
        return self.query(':INP:COUP?').strip()
    
    def set_sig_notch(self, harm1: bool, harm2: bool) -> None:
        cmd1 = f':INP:FILT:NOTC1 {int(harm1)}'
        cmd2 = f':INP:FILT:NOTC2 {int(harm2)}'
        self.write(f'{cmd1};{cmd2}')
    
    def get_sig_notch(self) -> tuple[bool, bool]:
        harm1 = bool(int(self.query(':INP:FILT:NOTC1?')))
        harm2 = bool(int(self.query(':INP:FILT:NOTC2?')))
        return harm1, harm2
    
    def set_sig_gnd(self, gnd:str) -> None:
        token = _validate_enum_attr(gnd, self._SIG_GND, 'SIG_GND')
        self.write(f':INP:LOW {token}')
    
    def get_sig_gnd(self) -> str:
        return self.query(':INP:LOW?').strip()
    
    def set_sig_IV_gain(self, gain: str) -> None:
        token = _validate_enum_attr(gain, self._SIG_IV_GAIN, 'SIG_IV_GAIN')
        self.write(f':INP:GAIN {token}')
    
    def get_sig_IV_gain(self) -> str:
        return self.query(':INP:GAIN?').strip()
    
    def set_sig_connector(self, conn:str) -> None:
        token = _validate_enum_attr(conn, self._SIG_CONN, 'SIG_CONN')
        self.write(f':ROUT {token}')
    
    def get_sig_connector(self) -> str:
        return self.query(':ROUT?').strip()
    
    # ---------------- Sense of Input Signal ----------------
    def set_DR(self, sense_DR: str) -> None:
        token = _validate_enum_attr(sense_DR, self._SENSE_DR, 'SENSE_DR')
        self.write(f':DRES {token}')
    
    def get_DR(self) -> str:
        return self.query(':DRES?').strip()
    
    def set_priPSD_filter_slope(self, slope: int|str) -> None:
        token = _validate_enum_attr(str(int(slope)), self._SENSE_FILTER_SLOPE, 'SENSE_FILTER_SLOPE')
        self.write(f':FILT:SLOP {token}')
    
    def get_priPSD_filter_slope(self) -> str:
        return self.query(f':FILT:SLOP?').strip()
    
    def set_secPSD_filter_slope(self, slope: int|str) -> None:
        token = _validate_enum_attr(str(int(slope)), self._SENSE_FILTER_SLOPE, 'SENSE_FILTER_SLOPE')
        self.write(f':FILT2:SLOP {token}')
    
    def get_secPSD_filter_slope(self) -> str:
        return self.query(f':FILT2:SLOP?').strip()

    def set_priPSD_filter_type(self, filter_type: str) -> None:
        token = _validate_enum_attr(filter_type, self._SENSE_FILTER_TYPE, 'SENSE_FILTER_TYPE')
        self.write(f':FILT:TYPE {token}')
    
    def get_priPSD_filter_type(self) -> str:
        return self.query(':FILT:TYPE?').strip()
    
    def set_secPSD_filter_type(self, filter_type: str) -> None:
        token = _validate_enum_attr(filter_type, self._SENSE_FILTER_TYPE, 'SENSE_FILTER_TYPE')
        self.write(f':FILT2:TYPE {token}')
    
    def get_secPSD_filter_type(self) -> str:
        return self.query(':FILT2:TYPE?').strip()
    
    def set_priPSD_filter_Tc(self, Tc: float) -> None:
        if Tc >= 5e-6 and Tc <= 50e3:
            self.write(f':FILT:TCON {Tc}')
        else:
            raise ValueError('Time constant for the primary PSD must be in [5e-6, 50e3].')
    
    def get_priPSD_filter_Tc(self) -> float:
        return float(self.query(':FILT:TCON?'))
    
    def set_secPSD_filter_Tc(self, Tc:float) -> None:
        if Tc >= 5e-6 and Tc <= 50e3:
            self.write(f':FILT2:TCON {Tc}')
        else:
            raise ValueError('Time constant for the secondary PSD must be in [5e-6, 50e3].')
    
    def get_secPSD_filter_Tc(self) -> float:
        return float(self.query(':FILT2:TCON?'))
    
    def set_priPSD_phase(self, phase: float) -> None:
        if phase > -720 and phase < 720:
            self.write(f':PHAS {phase}')
        else:
            raise ValueError('Phase for the primary PSD must be in [-720, 720]')
    
    def get_priPSD_phase(self) -> float:
        return float(self.query(':PHAS?'))
    
    def set_secPSD_phase(self, phase: float) -> None:
        if phase > -720 and phase < 720:
            self.write(f':PHAS2 {phase}')
        else:
            raise ValueError('Phase for the secondary PSD must be in [-720, 720]')
    
    def get_secPSD_phase(self) -> float:
        return float(self.query(':PHAS2?'))
    
    def set_priPSD_curr_range(self, curr_range:float) -> None:
        gain = self.get_sig_IV_gain()
        if gain == 'IE6':
            if curr_range < 100e-15 or curr_range > 1e-6:
                raise ValueError('Current Range must be in [100e-15, 1e-6], when IV_GAIN = IE6')
        else:
            if curr_range < 10e-15 or curr_range > 10e-9:
                raise ValueError('Current Range must be in [10e-15, 10e-9], when IV_GAIN = IE8')
        self.write(f':CURR:AC:RANGE {curr_range:g}')
    
    def get_priPSD_curr_range(self) -> float:
        return float(self.query(':CURR:AC:RANGE?'))
    
    def set_secPSD_curr_range(self, curr_range:float) -> None:
        gain = self.get_sig_IV_gain()
        if gain == 'IE6':
            if curr_range < 100e-15 or curr_range > 1e-6:
                raise ValueError('Current Range must be in [100e-15, 1e-6], when IV_GAIN = IE6')
        else:
            if curr_range < 10e-15 or curr_range > 10e-9:
                raise ValueError('Current Range must be in [10e-15, 10e-9], when IV_GAIN = IE8')
        if self.get_detect_mode() in {'DUAL1', 'DUAL2'}:
            if curr_range > self.get_priPSD_curr_range():
                raise ValueError('Current Range of secPSD must be SMALLER than priPSD in DUAL mode')
        self.write(f':CURR2:AC:RANGE {curr_range:g}')
    
    def get_secPSD_curr_range(self) -> float:
        return float(self.query(':CURR2:AC:RANGE?'))

    def set_priPSD_volt_range(self, volt_range: float) -> None:
        if volt_range < 10e-9 or volt_range > 1:
            raise ValueError('Voltange Range must in [10e-9, 1].')
        self.write(f':VOLT:AC:RANGE {volt_range}')
    
    def get_priPSD_volt_range(self) -> float:
        return float(self.query(':VOLT:AC:RANGE?'))
    
    def set_secPSD_volt_range(self, volt_range: float) -> None:
        if volt_range < 10e-9 or volt_range > 1:
            raise ValueError('Voltange Range must in [10e-9, 1].')
        if self.get_detect_mode() in {'DUAL1', 'DUAL2'}:
            if volt_range > self.get_priPSD_volt_range():
                raise ValueError('Voltage Range of secPSD must be SMALLER than priPSD in DUAL mode')
        self.write(f':VOLT2:AC:RANGE {volt_range}')
    
    def get_secPSD_volt_range(self) -> float:
        return float(self.query(':VOLT2:AC:RANGE?'))
    
    # ---------------- CALCn:FORM ----------------
    def set_calc_form(self, form:str, ch:int) -> None:
        if ch not in {1, 2, 3, 4}:
            raise ValueError('Channel index must be in (1,2,3,4).')
        mode = self.get_detect_mode()
        token = _validate_enum_attr(form, self._CALC_FORM[ch][mode], f'CALC{ch}_FORM_{mode}')
        self.write(f':CALC{ch}:FORM {token}')
    
    def get_calc_form(self, ch: int) -> str:
        return self.query(f':CALC{ch}:FORM?').strip()
    
    # ---------------- Snapshot ----------------
    def snapshot(self) -> dict[str, Any]:
        config = {
            'DETECT_MODE': self.get_detect_mode(),

            'REF_SRC': self.get_ref_src(),
            'REF_TYPE': self.get_ref_type(),

            'SIG_COUPLING': self.get_sig_coupling(),
            'SIG_NOTCH': self.get_sig_notch(),
            'SIG_GND': self.get_sig_gnd(),
            'SIG_CONNECTOR': self.get_sig_connector(),
            'SIG_IV_GAIN': self.get_sig_IV_gain(),

            'DR': self.get_DR(),
            'SENSE_PRI_FILTER_SLOPE': self.get_priPSD_filter_slope(),
            'SENSE_SEC_FILTER_SLOPE': self.get_secPSD_filter_slope(),
            'SENSE_PRI_FILTER_TYPE': self.get_priPSD_filter_type(),
            'SENSE_SEC_FILTER_TYPE': self.get_secPSD_filter_type(),
            'SENSE_PRI_FILTER_TC': self.get_priPSD_filter_Tc(),
            'SENSE_SEC_FILTER_TC': self.get_secPSD_filter_Tc(),
            'SENSE_PRI_PHASE': self.get_priPSD_phase(),
            'SENSE_SEC_PHASE': self.get_secPSD_phase(),

            'PRI_HARM_ON': self.get_priPSD_harmonics_on(),
            'PRI_HARM': self.get_priPSD_harmonics(),
            'SEC_HARM_ON': self.get_secPSD_harmonics_on(),
            'SEC_HARM': self.get_secPSD_harmonics(),

            'SENSE_PRI_CURR_RANGE': self.get_priPSD_curr_range(),
            'SENSE_SEC_CURR_RANGE': self.get_secPSD_curr_range(),
            'SENSE_PRI_VOLT_RANGE': self.get_priPSD_volt_range(),
            'SENSE_SEC_VOLT_RANGE': self.get_secPSD_volt_range(),
            
            'CALC1_FORM': self.get_calc_form(1),
            'CALC2_FORM': self.get_calc_form(2),
            'CALC3_FORM': self.get_calc_form(3),
            'CALC4_FORM': self.get_calc_form(4),
        }

        return config
    
    def recover(self, config: dict[str, Any]) -> None:
        self.set_detect_mode(config['DETECT_MODE'])
        self.set_ref_src(config['REF_SRC'])
        self.set_ref_type(config['REF_TYPE'])

        self.set_sig_coupling(config['SIG_COUPLING'])
        self.set_sig_notch(*tuple(config['SIG_NOTCH']))
        self.set_sig_gnd(config['SIG_GND'])
        self.set_sig_connector(config['SIG_CONNECTOR'])
        self.set_sig_IV_gain(config['SIG_IV_GAIN'])

        self.set_DR(config['DR'])
        self.set_priPSD_filter_slope(config['SENSE_PRI_FILTER_SLOPE'])
        self.set_secPSD_filter_slope(config['SENSE_SEC_FILTER_SLOPE'])
        self.set_priPSD_filter_type(config['SENSE_PRI_FILTER_TYPE'])
        self.set_secPSD_filter_type(config['SENSE_SEC_FILTER_TYPE'])
        self.set_priPSD_filter_Tc(config['SENSE_PRI_FILTER_TC'])
        self.set_secPSD_filter_Tc(config['SENSE_SEC_FILTER_TC'])
        self.set_priPSD_phase(config['SENSE_PRI_PHASE'])
        self.set_secPSD_phase(config['SENSE_SEC_PHASE'])

        self.set_priPSD_harmonics_on(config['PRI_HARM_ON'])
        self.set_priPSD_harmonics(*tuple(config['PRI_HARM']))
        self.set_secPSD_harmonics_on(config['SEC_HARM_ON'])
        self.set_secPSD_harmonics(config['SEC_HARM'])

        if config['SIG_CONNECTOR'] == 'I':
            self.set_priPSD_curr_range(config['SENSE_PRI_CURR_RANGE'])
            self.set_secPSD_curr_range(config['SENSE_SEC_CURR_RANGE'])
        else:
            self.set_priPSD_volt_range(config['SENSE_PRI_VOLT_RANGE'])
            self.set_secPSD_volt_range(config['SENSE_SEC_VOLT_RANGE'])
        
        self.set_calc_form(config['CALC1_FORM'], 1)
        self.set_calc_form(config['CALC2_FORM'], 2)
        self.set_calc_form(config['CALC3_FORM'], 3)
        self.set_calc_form(config['CALC4_FORM'], 4)
    
    # ---------------- Fetch Data ----------------
    def set_sense_data(self, measurement_data: Sequence[str]):
        token = 0
        for md in measurement_data:
            token += self._SENSE_DATA[md.upper()]
        self.write(f':DATA {int(token)}')
    
    def _fetch_once(self) -> tuple[float]:
        resp = self.query(':FETCH?').strip()
        data = [float(d) for d in resp.split(',')]
        return tuple(data)
    
    def fetch(self) -> tuple[float]:
        return self._fetch_once()
    
    async def afetch(self):
        resp = await self.aquery(':FETCH?')
        data = [float(d) for d in resp.strip().split(',')]
        return tuple(data)
    
    # ---------------- Auto Tuning ----------------
    def wait_for_auto_measure(self, polling_cycle:float = 0.5):
        while (int(self.query(':STAT:OPER:COND?')) & 4) != 0:
            time.sleep(polling_cycle)
    
    async def await_for_auto_measure(self, polling_cycle:float = 0.5):
        while (int(self.query(':STAT:OPER:COND?')) & 4) != 0:
            await asyncio.sleep(polling_cycle)
    
    def auto_once_volt_range(self):
        self.write(':VOLT:AC:RANG:AUTO:ONCE')
    
    def auto_once_curr_range(self):
        self.write(':CURR:AC:RANGE:AUTO:ONCE')
    
    # ---------------- Source Subsystem ----------------
    def get_priPSD_osc_freq(self) -> float:
        return float(self.query(':SOUR:FREQ?'))
    
    def set_priPSD_osc_freq(self, freq:float):
        if freq < 5e-4 or freq > 2.6e5:
            raise ValueError('Frequency must be in [5e-4, 2.6e5] Hz.')
        self.write(f':SOUR:FREQ {freq}')
    
    def get_secPSD_osc_freq(self) -> float:
        return float(self.query(':SOUR:FREQ2?'))

    def set_secPSD_osc_freq(self, freq:float):
        if freq < 5e-4 or freq > 2.6e5:
            raise ValueError('Frequency must be in [5e-4, 2.6e5] Hz.')
        self.write(f':SOUR:FREQ2 {freq}')
    
    def get_osc_output_PSD(self) -> str:
        return self.query(':SOUR:IOSC?').strip()
    
    def set_osc_output_PSD(self, psd: str):
        token = _validate_enum_attr(psd, self._SRC_IOSC, 'SRC_IOSC')
        self.write(f':SOUR:IOSC {token}')

    def get_osc_volt(self) -> float:
        return float(self.query(':SOUR:VOLT?'))
    
    def set_osc_volt(self, Vrms: float):
        if Vrms < 0.0 or Vrms > 1.0:
            raise ValueError('OSC_OUT_VOLT must be in [0,1] Vrms.')
        self.write(f':SOUR:VOLT {Vrms}')
    
    def get_osc_range(self) -> float:
        return float(self.query(':SOUR:VOLT:RANG?'))
    
    def set_osc_range(self, osc_range: float):
        self.write(f':SOUR:VOLT:RANG {osc_range}')
        
    
    # ---------------- Source5/6 (AUX OUT) Subsystem ----------------
    def set_auxout1_volt(self, volt: float):
        if volt > 10.5 or volt < -10.5:
            raise ValueError('AUX OUT 1 must be in [-10.5, 10.5] V.')
        self.write(f':SOUR5:VOLT:OFFS {volt}')
    
    def set_auxout2_volt(self, volt:float):
        if volt > 10.5 or volt < -10.5:
            raise ValueError('AUX OUT 2 must be in [-10.5, 10.5] V.')
        self.write(f':SOUR6:VOLT:OFFS {volt}')
    
    def get_auxout1_volt(self) -> float:
        return float(self.query(':SOUR5:VOLT:OFFS?'))
    
    def get_auxout2_volt(self) -> float:
        return float(self.query(':SOUR6:VOLT:OFFS?'))
    
    def set_auxout1_volt_ramp(self, volt: float, dV: float, dt: float):
        if np.abs(dV) < 0.001:
            raise ValueError('The resolution for AUX OUT is 0.001 V.')
        V_start = self.get_auxout1_volt()
        N = int(np.abs(volt - V_start) / dV) + 1
        v_ramp = np.linspace(V_start, volt, N)
        for v in v_ramp:
            self.set_auxout1_volt(v)
            time.sleep(dt)
    
    def set_auxout2_volt_ramp(self, volt: float, dV: float, dt: float):
        if np.abs(dV) < 0.001:
            raise ValueError('The resolution for AUX OUT is 0.001 V.')
        V_start = self.get_auxout2_volt()
        N = int(np.abs(volt - V_start) / dV) + 1
        v_ramp = np.linspace(V_start, volt, N)
        for v in v_ramp:
            self.set_auxout2_volt(v)
            time.sleep(dt)
    
    async def aset_auxout1_volt_ramp(self, volt: float, dV: float, dt: float):
        if np.abs(dV) < 0.001:
            raise ValueError('The resolution for AUX OUT is 0.001 V.')
        V_start = self.get_auxout1_volt()
        N = int(np.abs(volt - V_start) / dV) + 1
        v_ramp = np.linspace(V_start, volt, N)
        for v in v_ramp:
            self.set_auxout1_volt(v)
            await asyncio.sleep(dt)
    
    async def aset_auxout2_volt_ramp(self, volt: float, dV: float, dt: float):
        if np.abs(dV) < 0.001:
            raise ValueError('The resolution for AUX OUT is 0.001 V.')
        V_start = self.get_auxout2_volt()
        N = int(np.abs(volt - V_start) / dV) + 1
        v_ramp = np.linspace(V_start, volt, N)
        for v in v_ramp:
            self.set_auxout2_volt(v)
            await asyncio.sleep(dt)



class NF5650Array():
    def __init__(self, lockin_list: dict[str,str], *, rm = None):
        self._sense_data = []
        self._var_suffix = []
        
        self._alias: list[str] = []
        self._instr: list[NF5650] = []
        for alias, addr in lockin_list.items():
            self._alias.append(alias)
            self._instr.append(NF5650(visa_address=addr, rm=rm))

        self._fetch_tasks = None

    def connect(self):
        for _, instr in self.items():
            instr.connect()
    
    def disconnect(self):
        for _, instr in self.items():
            instr.disconnect()
    
    def __getitem__(self, alias:str) -> NF5650:
        if alias not in self.items():
            raise KeyError(f'NF5650 with alias of [{alias}] is not in this array. ')
        return self._instr[alias]
    
    def items(self) -> Iterator[tuple[str, NF5650]]:
        for alias, instr in zip(self._alias, self._instr):
            yield alias, instr

    def set_sense_data(self, measurement_data: Sequence[str], suffix: Sequence[str]):
        self._sense_data = measurement_data.copy()
        self._var_suffix = suffix.copy()
        for _, instr in self.items():
            instr.set_sense_data(measurement_data)
    
    def _fetch(self):
        frame = {}
        for alias, instr in self.items():
            data = instr.fetch()
            for var, d in zip(self._var_suffix, data):
                frame[f'{alias}_{var}'] = d
        return frame
    
    def _ensure_afetch_tasks(self):
        if not self._fetch_tasks:
            self._fetch_tasks = [instr.afetch() for alias, instr in self.items()]

    async def _afetch(self):
        self._ensure_afetch_tasks()
        datas = await asyncio.gather(*self._fetch_tasks)
        frame = {}
        for alias, data in zip(self._alias, datas):
            for var, d in zip(self._var_suffix, data):
                frame[f'{alias}_{var}'] = d
        return frame
    
    def fetch(self, asyn:bool=False):
        if asyn:
            return asyncio.run(self._afetch())
        else:
            return self._fetch()
    
    