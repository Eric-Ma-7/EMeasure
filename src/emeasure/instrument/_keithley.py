from ._core import BaseInstrument, _validate_enum_attr
from typing import Optional, Any, Literal, Sequence

import numpy as np
import time
import asyncio

class K6221(BaseInstrument):
    def __init__(self, visa_address, rm = None):
        super().__init__(visa_address, rm)
        
    # --------------- DC Source --------------- #
    def set_curr(self, I:float):
        self.write(f'SOUR:CURR {I}')
    
    def get_curr(self) -> float:
        return float(self.query('SOUR:CURR?'))
    
    def set_output_on(self, is_on: bool = True):
        if is_on:
            self.write('OUTP ON')
        else:
            self.write('OUTP OFF')
    
    def get_output_on(self) -> bool:
        resp = self.query('OUTP?').strip().upper()
        if resp == 'ON':
            return True
        elif resp == 'OFF':
            return False
        else:
            raise IOError(f'A unknown output state is received: {resp}')
    
    def set_volt_limit(self, limit: float):
        if 0.1 < limit< 105:
            self.write(f'SOUR:CURR:COMP {limit}')
        else:
            raise ValueError('Voltage compliance must be in [0.1, 105]')
    
    def get_volt_limit(self) -> float:
        return float(self.query('SOUR:CURR:COMP?'))
    
    def set_curr_range(self, curr_range:float):
        self.write(f'SOUR:CURR:RANG {curr_range}')
    
    def set_curr_range_auto(self, is_auto:bool = True):
        if is_auto:
            self.write('SOUR:CURR:RANG:AUTO ON')
        else:
            self.write('SOUR:CURR:RANG:AUTO OFF')
    
    def clear_source(self):
        self.write('SOUR:CLE')
    
    # --------------- SINE WAVE Source --------------- #
    def set_source_wave_sin(self, freq: float, ampl: float, offs: float = 0) -> None:
        self.write( 'SOUR:WAVE:FUNC SIN')
        self.write(f'SOUR:WAVE:FREQ {freq}')
        self.write(f'SOUR:WAVE:AMPL {ampl}')
        self.write(f'SOUR:WAVE:OFFS {offs}')
        self.write( 'SOUR:WAVE:RANG BEST')
        self.write( 'SOUR:WAVE:PMAR 0')
        self.write( 'SOUR:WAVE:PMAR:STAT ON')
    
    def arm_and_trigger_waveform(self) -> None:
        self.write('SOUR:WAVE:ARM')
        self.write('SOUR:WAVE:INIT')
    
    def stop_waveform(self) -> None:
        self.write('SOUR:WAVE:ABOR')


class K2612(BaseInstrument):
    def _ch2smux(self, channel: str) -> str:
        if channel.lower() in {'a', 'b'}:
            return f'smu{channel}'
        else:
            raise ValueError('Channel must be a or b')

    def set_volt(self, volt: float, channel: str):
        smux = self._ch2smux(channel)
        self.write(f'{smux}.source.levelv = {volt}')
    
    def set_curr(self, curr: float, channel: str):
        smux = self._ch2smux(channel)
        self.write(f'{smux}.source.leveli = {curr}')
    
    def get_iv(self, channel:str) -> Sequence[float]:
        smux = self._ch2smux(channel)
        resp = self.query(f'print({smux}.measure.iv())')
        iv = [float(x) for x in resp.split()]
        return tuple(iv)
    
    def get_volt(self, channel: str) -> float:
        smux = self._ch2smux(channel)
        return float(self.query(f'print({smux}.measure.v())'))
    
    def get_curr(self, channel: str) -> float:
        smux = self._ch2smux(channel)
        return float(self.query(f'print({smux}.measure.i())'))
    
    def set_output_on(self, is_on: bool, channel: str):
        smux = self._ch2smux(channel)
        if is_on:
            self.write(f'{smux}.source.output = 1')
        else:
            self.write(f'{smux}.source.output = 0')
    
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
            raise ValueError("Sense mode must be '2-wire/local' or '4-wire/remote'.")
    
    def set_source_func(self, src_func: str, channel: str):
        smux = self._ch2smux(channel)
        if src_func.lower() in {'curr', 'i', 'current'}:
            self.write(f'{smux}.source.func = {smux}.OUTPUT_DCAMPS')
        elif src_func.lower() in {'volt', 'v', 'voltage'}:
            self.write(f'{smux}.source.func = {smux}.OUTPUT_DCVOLTS')
        else:
            raise ValueError("Source function must be 'current/curr/i' or 'voltage/volt/v'.")
    
    def set_curr_ramp(self, I_target: float, dI: float, dt: float, channel: str):
        I_now = self.get_curr(channel)
        N = int(np.abs(I_target - I_now) / dI + 1)
        currs = np.linspace(I_now, I_target, N)
        for curr in currs:
            self.set_curr(curr, channel)
            self.get_iv(channel)
            time.sleep(dt)
    
    def set_volt_ramp(self, V_target: float, dV: float, dt: float, channel: str):
        V_now = self.get_volt(channel)
        N = int(np.abs(V_target - V_now) / dV + 1)
        volts = np.linspace(V_now, V_target, N)
        for volt in volts:
            self.set_volt(volt, channel)
            self.get_iv(channel)
            time.sleep(dt)


class K2182(BaseInstrument):
    def fetch(self):
        response = self.query(":fetch?")
        return float(response.strip())


class K2400(BaseInstrument):
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
            raise ValueError(":SOUR:FUNC must be 'curret/curr/i' or 'voltage/volt/v'.")
    
    def set_volt_range(self, vrange: float):
        if vrange < -210 or vrange > 210:
            raise ValueError(':SOUR:VOLT:RANG must be in [-210, 210] V.')
        self.write(f':SOUR:VOLT:RANG {vrange}')
    
    def set_curr_range(self, irange:float):
        if irange < -1.05 or irange > 1.05:
            raise ValueError(':SOUR:CURR:RANG must be in [-1.05, 1.05] A.')
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
            raise ValueError(':CURR:PROT must be in [-1.05, 1.05] A.')
        self.write(f':CURR:PROT {icomp}')
    
    def set_volt_comp(self, vcomp: float):
        if vcomp < -210 or vcomp > 210:
            raise ValueError(':VOLT:PROT must be in [-210, 210] V.')
        self.write(f':VOLT:PROT {vcomp}')
    
    # -------------------- SENSE subsystem --------------------
    def set_form_elem(self, items: Sequence[str]):
        item_list = ','.join(items)
        self.write(f':FORM:ELEM {item_list}')
        self.write(':READ?')
    
    def read(self) -> tuple[float]:
        resp = self.query(':READ?').strip()
        data = [float(s) for s in resp.split(',')]
        return tuple(data)
    
    # -------------------- SOURCE output control --------------------
    def set_curr(self, curr: float):
        if curr < -1.05 or curr > 1.05:
            raise ValueError(':SOUR:CURR must be in [-1.05, 1.05] A.')
        self.write(f':SOUR:CURR {curr}')
        
    def set_volt(self, volt: float):
        if volt < -210 or volt > 210:
            raise ValueError(':SOUR:VOLT must be in [-210, 210] V.')
        self.volt(f':SOUR:VOLT {volt}')
    
    def set_curr_ramp(self, curr: float, dI: float, dt: float):
        i0 = float(self.query(':SOUR:CURR?'))
        N = int(np.abs((curr -  i0) / dI) + 1)
        for i in np.linspace(i0, curr, N):
            self.set_curr(i)
            time.sleep(dt)
    
    def set_volt_ramp(self, volt:float, dV: float, dt: float):
        v0 = float(self.query(':SOUR:VOLT?'))
        N = int(np.abs((volt -  v0) / dV) + 1)
        for v in np.linspace(v0, volt, N):
            self.set_volt(v)
            time.sleep(dt)
    
    