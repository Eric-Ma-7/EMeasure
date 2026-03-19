from ._core import BaseInstrument
from typing import Sequence

class B2902(BaseInstrument):
    def set_mode(self, mode: str, channel:int):
        if mode.lower() in {'i', 'curr', 'current'}:
            self.write(f':SOUR{channel}:FUNC:MODE CURR')
        elif mode.lower() in {'v', 'volt', 'voltage'}:
            self.write(f':SOUR{channel}:FUNC:MODE VOLT')
    
    def get_mode(self, channel:int):
        return self.query(f':SOUR{channel}:FUNC:MODE?').strip()
    
    def set_output_on(self, is_on, channel:int):
        if is_on:
            self.write(f':OUTP{channel} ON')
        else:
            self.write(f':OUTP{channel} OFF')
    
    def get_output_on(self, channel:int) -> bool:
        resp = int(self.query(f':OUTP{channel}:STAT?'))
        if resp == 1:
            return True
        elif resp == 0:
            return False
        else:
            raise ValueError(f'An Unknow OUTP:STAT is read: {resp}')
    
    # --------------- SOURCE CURR/VOLT ---------------
    
    def set_curr(self, curr:float, channel:int):
        self.write(f':SOUR{channel}:CURR {curr}')
    
    def get_curr_setpoint(self, channel: int) -> float:
        return float(self.query(f':SOUR{channel}:CURR?'))
    
    def set_volt(self, volt:float, channel:int):
        self.write(f':SOUR{channel}:VOLT {volt}')
    
    def get_volt_setpoint(self, channel: int) -> float:
        return float(self.query(f':SOUR{channel}:VOLT?'))
    
    def set_src_value(self, val:float, channel:int):
        mode = self.get_mode(channel)
        if mode == 'CURR':
            self.set_curr(val, channel)
        elif mode == 'VOLT':
            self.set_volt(val, channel)
        else:
            raise ValueError(f'An unknown source mode is receivec: {mode}')
    
    def get_src_value(self, channel:int) -> float:
        mode = self.get_mode(channel)
        if mode == 'CURR':
            return self.get_curr_setpoint(channel)
        elif mode == 'VOLT':
            return self.get_volt_setpoint(channel)
        else:
            raise ValueError(f'An unknown source mode is receivec: {mode}')
    
    def set_curr_src_range(self, curr_range:float, channel:int):
        self.write(f':SOUR{channel}:CURR:RANG {curr_range}')
    
    def set_volt_src_range(self, volt_range:float, channel:int):
        self.write(f':SOUR{channel}:VOLT:RANG {volt_range}')
    
    def set_curr_src_range_auto(self, is_auto:bool, channel:int):
        if is_auto:
            self.write(f':SOUR{channel}:CURR:RANG:AUTO ON')
        else:
            self.write(f':SOUR{channel}:CURR:RANG:AUTO OFF')
    
    def set_volt_src_range_auto(self, is_auto:bool, channel:int):
        if is_auto:
            self.write(f':SOUR{channel}:VOLT:RANG:AUTO ON')
        else:
            self.write(f':SOUR{channel}:VOLT:RANG:AUTO OFF')
    
    def set_src_range_auto(self, is_auto:bool, channel:int):
        mode = self.get_mode(channel)
        if mode == 'CURR':
            return self.set_curr_src_range_auto(is_auto, channel)
        elif mode == 'VOLT':
            return self.set_volt_src_range_auto(is_auto, channel)
        else:
            raise ValueError(f'An unknown source mode is receivec: {mode}')
    
    def set_remote_sense(self, is_remote:bool, channel:int):
        if is_remote:
            self.write(f':SENS{channel}:REM ON')
        else:
            self.write(f':SENS{channel}:REM OFF')
    
    def get_remote_sense(self, channel:int) -> bool:
        resp = self.query(f':SENS{channel}:REM?').strip().upper()
        if resp == 'ON':
            return True
        elif resp == 'OFF':
            return False
        else:
            raise ValueError(f'A Unknow :SENSx:REM is received: {resp}')
    
    def set_form_elem(self, elem: Sequence[str]):
        token = ''
        self.write(f':FORM:ELEM:SENS {token}')
    
    def measure(self, ):
        resp = self.write(':MEAS? ()')