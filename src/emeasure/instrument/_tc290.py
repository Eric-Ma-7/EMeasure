from ._core import BaseInstrument

import time

class TC290(BaseInstrument):
    def __init__(self, visa_address, rm = None, *, write_delay = 0.1):
        super().__init__(visa_address, rm)
        self._write_delay = write_delay
    
    def connect(self, baud_rate:int=115200):
        super().connect()
        self._res.baud_rate = baud_rate
    
    def disconnect(self):
        return super().disconnect()
    
    def write(self, cmd):
        super().write(cmd)
        time.sleep(self._write_delay)
    
    def get_temp(self) -> float:
        resp = self.query(f'KRDG?').strip()
        return float(resp.split(',')[0])
    
    def get_temp_setpoint(self) -> float:
        return float(self.query('SETP? 1'))
    
    def set_temp_setpoint(self, temp:float):
        self.write(f'SETP 1,{temp}')
    
    def get_ramp(self) -> tuple[bool, float]:
        resp = self.query('RAMP? 1').strip().split(',')
        if int(resp[0]) == 0:
            enable = False
        elif int(resp[0]) == 1:
            enable = True
        else:
            raise ValueError(f'ENABLE must be 0 or 1. Now {resp[0]}')
        return enable, float(resp[1])
    
    def set_ramp(self, enable:bool, rate:float) -> None:
        if enable:
            self.write(f'RAMP 1,1,{rate}')
        else:
            self.write(f'RAMP 1,0,{rate}')
    
    def is_ramping(self) -> bool:
        resp = self.query(f'RAMPST?').strip()
        if resp == 0:
            return False
        elif resp == 1:
            return True
        else:
            raise ValueError('Invalid ramping state is accepted.')
    
    def set_heater_range(self, range:str|int) -> None:
        if isinstance(range, int):
            if range in (0, 1, 2, 3):
                self.write(f'RANGE 1,{range}')
        elif isinstance(range, str):
            match range.upper():
                case 'OFF':
                    self.write(f'RANGE 1,0')
                case 'LOW':
                    self.write(f'RANGE 1,1')
                case 'MED':
                    self.write(f'RANGE 1,2')
                case 'HIGH':
                    self.write(f'RANGE 1,3')
        else:
            raise ValueError('range must be 0-3 or OFF, LOW, MED, HIGH')
    
    def get_heater_range(self) -> str:
        resp = int(self.query('RANGE? 1').strip())
        match resp:
            case 0:
                return 'OFF'
            case 1:
                return 'LOW'
            case 2:
                return 'MED'
            case 3:
                return 'HIGH'
            case _:
                raise ValueError('Invalid heater range is accepted')

