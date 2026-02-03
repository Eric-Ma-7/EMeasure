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
    
    def set_measurement_mode(self, measurement_mode: str, channel: str):
        smux = self._ch2smux(channel)
        if measurement_mode.lower() == '4-wire':
            self.write(f'{smux}.sense = {smux}.SENSE_REMOTE')
        elif measurement_mode.lower() == '2-wire':
            self.write(f'{smux}.sense = {smux}.SENSE_LOCAL')
        else:
            raise ValueError("Measurement mode must be '2-wire' or '4-wire'.")
    
    def set_mode(self, mode: str, channel: str):
        smux = self._ch2smux(channel)
        if mode.lower() in {'curr', 'i', 'current'}:
            self.write(f'{smux}.source.func = {smux}.OUTPUT_DCAMPS')
        elif mode.lower() in {'volt', 'v', 'voltage'}:
            self.write(f'{smux}.source.func = {smux}.OUTPUT_DCVOLTS')
        else:
            raise ValueError("Mode must be 'current/curr/i' or 'voltage/volt/v'.")
    
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