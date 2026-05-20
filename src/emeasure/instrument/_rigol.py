from ._core import BaseInstrument
from ._utils import validate_enum_attr

import time
import numpy as np

def _header_add_ch(cmd: str, channel: int=1) -> str:
    if channel == 1:
        return cmd
    elif channel == 2:
        return cmd + ':ch2'
    else:
        raise ValueError(f'Channel is expected to be 1 or 2, but {channel} is received.')


class DG1022(BaseInstrument):
    _VOLT_UNIT = {"VPP", "VRMS", "DBM"}
    _WAVE_FUNC = {
        "SIN", "SQU", "RAMP", "PULS", "NOIS", "DC",
        "SINUSOID", "SQUARE", "PULSE", "NOISE"
    }

    def __init__(
            self, 
            visa_address:str = "USB0::0x1AB1::0x0588::DG1D123603646::INSTR", 
            rm = None, 
            *, 
            write_delay = 0.1
    ):
        super().__init__(visa_address, rm)
        self._write_delay = write_delay
    
    # -------------------- Lifecycle & I/O --------------------
    def connect(self, *, wait_time:float=0.5):
        super().connect()
        time.sleep(wait_time)
    
    def write(self, cmd):
        super().write(cmd)
        time.sleep(self._write_delay)
    
    def query(self, cmd):
        super().write(cmd)
        time.sleep(self._write_delay)
        resp = super().read()
        return resp
    
    def get_IDN(self) -> str:
        return self.query("*IDN?").strip()
    
    # -------------------- get & set --------------------
    def _set_raw(self, cmd: str, value, *, channel: int = 1):
        header = _header_add_ch(cmd, channel)
        self.write(f"{header} {value}")

    def _get_raw(self, cmd: str, *, channel: int = 1) -> str:
        header = _header_add_ch(cmd, channel)
        return self.query(f"{header}?").strip()
    
    def _set_bool(self, cmd: str, value: bool, *, channel: int = 1):
        self._set_raw(cmd, "ON" if value else "OFF", channel=channel)

    def _get_bool(self, cmd: str, *, channel: int = 1) -> bool:
        resp = self._get_raw(cmd, channel=channel).strip().upper()
        if resp in ("1", "ON", "TRUE"):
            return True
        if resp in ("0", "OFF", "FALSE"):
            return False
        raise ValueError(f"Cannot parse bool from response: {resp!r}")

    def _set_float(self, cmd: str, value: float, *, channel: int = 1):
        self._set_raw(cmd, value, channel=channel)

    def _get_float(self, cmd: str, *, channel: int = 1) -> float:
        return float(self._get_raw(cmd, channel=channel))

    def _set_str(self, cmd: str, value: str, *, channel: int = 1):
        self._set_raw(cmd, value, channel=channel)

    def _get_str(self, cmd: str, *, channel: int = 1) -> str:
        return self._get_raw(cmd, channel=channel)
    
    
    # -------------------- APPLY --------------------
    def apply_sin(self, freq:float, ampl:float, offs:float=0, *, channel:int=1):
        header = _header_add_ch("APPL:SIN", channel)
        self.write(f"{header} {freq},{ampl},{offs}")
    
    def apply_sqr(self, freq:float, ampl:float, offs:float=0, *, channel:int=1):
        header = _header_add_ch("APPL:SQU", channel)
        self.write(f"{header} {freq},{ampl},{offs}")
    
    def apply_ramp(self, freq:float, ampl:float, offs:float=0, *, channel:int=1):
        header = _header_add_ch("APPL:RAMP", channel)
        self.write(f"{header} {freq},{ampl},{offs}")
    
    def apply_pulse(self, freq:float, ampl:float, offs:float=0, *, channel:int=1):
        header = _header_add_ch("APPL:PULS", channel)
        self.write(f"{header} {freq},{ampl},{offs}")
    
    def apply_noise(self, ampl:float, offs:float=0, *, channel:int=1):
        header = _header_add_ch("APPL:NOIS", channel)
        self.write(f"{header} DEF,{ampl},{offs}")
    
    def apply_dc(self, dc:float, *, channel:int=1):
        header = _header_add_ch("APPL:DC", channel)
        self.write(f"{header} DEF,DEF,{dc}")
    
    # -------------------- OUTPUT --------------------
    def set_output_on(self, is_on:bool=True, channel:int=1):
        self._set_bool("OUTP", is_on, channel=channel)
    
    def get_output_on(self, channel:int=1) -> bool:
        return self._get_bool("OUTP", channel=channel)

    def set_output_load(self, load:float|str, channel:int=1):
        """
        OUTPut:LOAD {<Ohm> | INFinity | MINimum | MAXmum}
        """
        header = _header_add_ch("OUTP:LOAD", channel)
        self.write(f"{header} {load}")
    
    def get_output_load(self, channel:int=1):
        header = _header_add_ch("OUTP:LOAD", channel)
        resp = self.query(f"{header}?").strip()
        if resp.lower() == "infinity":
            return np.inf
        else:
            return float(resp)
    
    # -------------------- Frequency --------------------
    def set_freq(self, freq:float, channel:int=1):
        self._set_float("FREQ", freq, channel=channel)
    
    def get_freq(self, channel:int=1) -> float:
        return self._get_float("FREQ", channel=channel)
    
    # -------------------- Voltage --------------------
    def set_volt_ampl(self, ampl:float, unit="VPP", channel:int=1):
        self.set_volt_unit(unit)
        self._set_float("VOLT", ampl, channel=channel)
    
    def get_volt_ampl(self, channel:int=1):
        return self._get_float("VOLT", channel=channel)
    
    def set_volt_unit(self, unit:float, channel:int=1):
        """
        unit = VPP | VRMS | DBM (only under non-infinity output load)
        """
        unit_token = validate_enum_attr(unit, self._VOLT_UNIT, "VOLT_UNIT")
        if np.isinf(self.get_output_load()) and (unit_token == "DBM"):
            raise ValueError("DBM is illegal in infinity-load output mode.")
        self._set_str("VOLT:UNIT", unit_token, channel=channel)
    
    def get_volt_unit(self, channel:int=1):
        self._get_str("VOLT:UNIT", channel=channel)
    
    def set_volt_high(self, Vhigh:float, channel:int=1):
        self._set_float("VOLT:HIGH", Vhigh, channel=channel)
    
    def get_volt_high(self, channel:int=1):
        return self._get_float("VOLT:HIGH", channel=channel)
    
    def set_volt_low(self, Vlow:float, channel:int=1):
        self._set_float("VOLT:LOW", Vlow, channel=channel)
    
    def get_volt_low(self, channel:int=1):
        return self._get_float("VOLT:LOW", channel=channel)
    
    def set_volt_offs(self, Voffs:float, channel:int=1):
        self._set_float("VOLT:OFFS", Voffs, channel=channel)
    
    def get_volt_offs(self, channel:int=1):
        return self._get_float("VOLT:OFFS", channel=channel)
    
    # -------------------- Voltage --------------------
    def set_pulse_period(self, period:float, channel:int=1):
        self._set_float("PULS:PER", period, channel=channel)
    
    def get_pulse_period(self, channel:int=1):
        return self._get_float("PULS:PER", channel=channel)
    
    def set_pulse_width(self, width:float, channel:int=1):
        self._set_float("PULS:WIDT", width, channel=channel)
    
    def get_pulse_width(self, channel:int=1):
        return self._get_float("PULS:WIDT", channel=channel)
    
    def set_pulse_dcycle(self, dcycle:float, channel:int=1):
        self._set_float("PULS:DCYC", dcycle, channel=channel)
    
    def get_pulse_dcycle(self, channel:int=1):
        return self._get_float("PULS:DCYC", channel=channel)
    
    # -------------------- Phase --------------------
    def set_phase(self, phase:float, channel:int=1):
        if phase > 180 or phase < -180:
            raise ValueError(f"PHASE must be in [-180,180] deg.")
        self._set_float("PHAS", phase, channel=channel)
    
    def get_phase(self, channel:int=1):
        return self._get_float("PHAS", channel=channel)
    
    def set_phase_align(self):
        self.write("PHAS:ALIGN")
    
    # -------------------- Function --------------------
    def set_func(self, func:str, channel:int=1):
        validate_enum_attr(func, self._WAVE_FUNC, "WAVE_FUNC")
        self._set_str("FUNC", func, channel=channel)
    
    def get_func(self, channel:int=1):
        return self._get_str("FUNC", channel=channel)
    
    def set_square_dcycle(self, dcycle:float, channel:int=1):
        self._set_float("FUNC:SQU:DCYC", dcycle, channel=channel)
    
    def get_square_dcycle(self, channel:int=1):
        return self._get_float("FUNC:SQU:DCYC", channel=channel)
    
    def set_ramp_symm(self, symm:float, channel:int=1):
        self._set_float("FUNC:RAMP:SYMM", symm, channel=channel)
    
    def get_ramp_symm(self, channel:int=1):
        self._get_float("FUNC:RAMP:SYMM", channel=channel)

    
    