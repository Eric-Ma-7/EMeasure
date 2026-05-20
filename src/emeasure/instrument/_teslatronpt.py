from ._core import BaseInstrument
from ._utils import validate_enum_attr
from ._mercury import Mercury
from typing import Union, Sequence


import pyvisa
import asyncio
import time
import math
import threading

class MotorController(BaseInstrument):
    def __init__(self, visa_address, rm = None):
        super().__init__(visa_address, rm)
    
    def connect(self):
        super().connect()
        self._res.write_termination = '\r\n'
        self._res.read_termination  = '\r\n'
        self._res.baud_rate = 115200
    
    def disconnect(self):
        super().disconnect()
    
    def deg2code(self, deg:float) -> int:
        return math.ceil((deg % 360) * 54050 / 360)
    
    def code2deg(self, code:int) -> float:
        return float(code) * 360 / 54050
    
    def to_zero(self):
        self.write('[z,1,1501]')
    
    def to_deg(self, target:float, speed:float=5):
        if speed <= 0 or speed > 5:
            raise ValueError('Speed must be in (0,5] deg/sec.')
        speed_code = self.deg2code(speed)
        target_code = self.deg2code(target)
        self.write(f'[r,0,{speed_code:04d},{target_code:06d}]')
    
    def get_deg_code(self) -> int:
        self.write('[?]')
        resp = self._res.read_bytes(12)
        resp = resp.decode('utf-8')
        return int(resp[5:-1])

    def get_deg(self):
        return self.code2deg(self.get_deg_code())
    
    def drive_to_deg(self, target:float, speed:float=5):
        if speed <= 0 or speed > 5:
            raise ValueError('Speed must be in (0,5] deg/sec.')
        speed_code = self.deg2code(speed)
        target_code = self.deg2code(target)
        now_code = self.get_deg_code()

        t = abs(target_code - now_code) / speed_code

        self.write(f'[r,0,{speed_code:04d},{target_code:06d}]')
        
        time.sleep(t)
        for _ in range(10):
            if target_code == self.get_deg_code():
                break
            time.sleep(0.2)
        else:
            raise TimeoutError(f'Motor is NOT at the target position.')
    
    async def adrive_to_deg(self, target:float, speed:float=5):
        if speed <= 0 or speed > 5:
            raise ValueError('Speed must be in (0,5] deg/sec.')
        speed_code = self.deg2code(speed)
        target_code = self.deg2code(target)
        now_code = self.get_deg_code()

        t = abs(target_code - now_code) / speed_code

        self.write(f'[r,0,{speed_code:04d},{target_code:06d}]')
        
        await asyncio.sleep(t)
        for _ in range(10):
            if target_code == self.get_deg_code():
                break
            await asyncio.sleep(0.2)
        else:
            raise TimeoutError(f'Motor is NOT at the target position.')


class iTC(Mercury):
    def __init__(self, visa_address, rm=None):
        super().__init__(visa_address, rm)
    
    def get_UID_temp(self, UID: str) -> float:
        return self.query_number(f'READ:DEV:{UID}:TEMP:SIG:TEMP')
    
    def get_probe_temp(self) -> float:
        return self.get_UID_temp('DB8.T1')
    
    def get_VTI_temp(self) -> float:
        return self.get_UID_temp('MB1.T1')
    
    def get_pres(self) -> float:
        return self.query_number('READ:DEV:DB5.P1:PRES:SIG:PRES')
    
    def get_flow(self) -> float:
        return self.query_number('READ:DEV:DB5.P1:PRES:LOOP:FSET')
    

    # --------------- PROBE TEMP --------------- #
    def set_probe_temp_setpoint(self, Tprobe: float):
        if Tprobe < 0 or Tprobe > 300:
            raise ValueError("ITC_PROBE_TEMP must in [0, 300] K.")
        self.write_check_valid(f"SET:DEV:DB8.T1:TEMP:LOOP:TSET:{Tprobe}")
    
    def get_probe_temp_setpoint(self) -> float:
        return self.query_number("READ:DEV:DB8.T1:TEMP:LOOP:TSET")
    
    def set_probe_loop_enable(self, is_enable: bool=True):
        if is_enable:
            self.write_check_valid("SET:DEV:DB8.T1:TEMP:LOOP:ENAB:ON")
        else:
            self.write_check_valid("SET:DEV:DB8.T1:TEMP:LOOP:ENAB:OFF")
    
    def get_probe_loop_enable(self) -> bool:
        return self.query_bool("READ:DEV:DB8.T1:TEMP:LOOP:ENAB")
    
    def set_probe_heater(self, percentage: float):
        if percentage < 0 and percentage > 100:
            raise ValueError("ITC_PROBE_HEATER must be in [0, 100]%.")
        self.write_check_valid(f"SET:DEV:DB8.T1:TEMP:LOOP:HSET:{percentage}")
    
    def get_probe_heater(self) -> float:
        return self.query_number("READ:DEV:DB8.T1:TEMP:LOOP:HSET")
    

    # --------------- VTI TEMP --------------- #
    def set_VTI_temp_setpoint(self, Tvti: float):
        if Tvti < 0 or Tvti > 300:
            raise ValueError("ITC_VTI_TEMP must in [0, 300] K.")
        self.write_check_valid(f"SET:DEV:MB1.T1:TEMP:LOOP:TSET:{Tvti}")
    
    def get_VTI_temp_setpoint(self) -> float:
        return self.query_number("READ:DEV:MB1.T1:TEMP:LOOP:TSET")
    
    def set_VTI_loop_enable(self, is_enable: bool=True):
        if is_enable:
            self.write_check_valid("SET:DEV:MB1.T1:TEMP:LOOP:ENAB:ON")
        else:
            self.write_check_valid("SET:DEV:MB1.T1:TEMP:LOOP:ENAB:OFF")
    
    def get_VTI_loop_enable(self) -> bool:
        return self.query_bool("READ:DEV:MB1.T1:TEMP:LOOP:ENAB")
    
    def set_VTI_heater(self, percentage: float):
        if percentage < 0 and percentage > 100:
            raise ValueError("ITC_VTI_HEATER must be in [0, 100]%.")
        self.write_check_valid(f"SET:DEV:MB1.T1:TEMP:LOOP:HSET:{percentage}")
    
    def get_VTI_heater(self) -> float:
        return self.query_number("READ:DEV:MB1.T1:TEMP:LOOP:HSET")
    
    # --------------- PRESSURE & NVFLOW --------------- #
    def set_pres_setpoint(self, pres:float):
        if pres < 0 and pres > 2000:
            raise ValueError("ITC_PRES must be in [0, 2000] mbar.")
        self.write_check_valid(f"SET:DEV:DB5.P1:PRES:LOOP:PRST:{pres}")
    
    def get_pres_setpoint(self) -> float:
        return self.query_number("READ:DEV:DB5.P1:PRES:LOOP:PRST")
    
    def set_pres_loop_enable(self, is_enable:bool=True):
        if is_enable:
            self.write_check_valid("SET:DEV:DB5.P1:PRES:LOOP:FAUT:ON")
        else:
            self.write_check_valid("SET:DEV:DB5.P1:PRES:LOOP:FAUT:OFF")
    
    def get_pres_loop_enable(self) -> bool:
        return self.query_bool("READ:DEV:DB5.P1:PRES:LOOP:FAUT")
    
    def set_flow_setpoint(self, flow):
        if flow < 0 and flow > 100:
            raise ValueError("ITC_PRES must be in [0, 100] %.")
        self.write_check_valid(f"SET:DEV:DB5.P1:PRES:LOOP:FSET:{flow}")
    
    def get_flow_setpoint(self) -> float:
        return self.query_number("READ:DEV:DB5.P1:PRES:LOOP:FSET")
   

class iPS(Mercury):
    _ACTN = {'HOLD', 'RTOS', 'RTOZ'}

    def __init__(self, visa_address, rm=None):
        super().__init__(visa_address, rm)
    
    def get_magnet_temp(self) -> float:
        return self.query_number('READ:DEV:MB1.T1:TEMP:SIG:TEMP')
    
    def get_PT2_temp(self) -> float:
        return self.query_number('READ:DEV:DB7.T1:TEMP:SIG:TEMP')
    
    def get_PT1_temp(self) -> float:
        return self.query_number('READ:DEV:DB8.T1:TEMP:SIG:TEMP')
    
    def get_field(self) -> float:
        return self.query_number('READ:DEV:GRPZ:PSU:SIG:PFLD')

    def get_action(self) -> str:
        return self.query_str('READ:DEV:GRPZ:PSU:ACTN')
    
    def set_action(self, actn: str):
        token = validate_enum_attr(actn, self._ACTN, 'IPS_ACTN')
        self.write_check_valid(f'SET:DEV:GRPZ:PSU:ACTN:{token}')
    
    def set_ramp_rate(self, rate: float):
        if rate > 0.2:
            raise ValueError(f'Ramp rate must be smaller than 0.2 T/min. Now {rate} T/min.')
        self.write_check_valid(f'SET:DEV:GRPZ:PSU:SIG:RFST:{rate:.4f}')
    
    def set_target_field(self, B_target: float):
        if B_target > 14:
            raise ValueError(f'Target magnetic field must be smaller than 14 T. Now {B_target} T.')
        self.write_check_valid(f'SET:DEV:GRPZ:PSU:SIG:FSET:{B_target:.6f}')
    
    # -------------------- Drive to field --------------------
    def wait_until_hold(self, query_interval: float = 2):
        while self.get_action() != 'HOLD':
            time.sleep(query_interval)
    
    def drive_to_field(self, B_target: float, rate: float, *, query_interval: float = 2.0):
        self.set_action('HOLD')
        self.set_target_field(B_target)
        self.set_ramp_rate(rate)
        self.set_action('RTOS')
        self.wait_until_hold(query_interval)
    
    # -------------------- Heater --------------------
    def set_heater_on(self, *, is_wait:bool=False):
        if not self.get_heater_status():
            self.write_check_valid('SET:DEV:GRPZ:PSU:SIG:SWHT:ON')
        if is_wait:
            self.wait_heater_on()

    def set_heater_off(self, *, is_wait:bool=False):
        if self.get_heater_status():
            self.write_check_valid('SET:DEV:GRPZ:PSU:SIG:SWHT:OFF')
        if is_wait:
            self.wait_heater_off()
    
    def get_heater_status(self):
        return self.query_bool('READ:DEV:GRPZ:PSU:SIG:SWHT')
    
    def wait_heater_on(self):
        delay = self.query_number('READ:DEV:GRPZ:PSU:SWONT')
        time.sleep(delay / 1000)
        while not self.get_heater_status():
            time.sleep(10)
    
    def wait_heater_off(self):
        delay = self.query_number('READ:DEV:GRPZ:PSU:SWOFT')
        time.sleep(delay / 1000)
        while self.get_heater_status():
            time.sleep(10)
    
    async def await_heater_on(self):
        delay = self.query_number('READ:DEV:GRPZ:PSU:SWONT')
        await asyncio.sleep(delay / 1000)
        while not self.get_heater_status():
            await asyncio.sleep(10)
    
    async def await_heater_off(self):
        delay = self.query_number('READ:DEV:GRPZ:PSU:SWOFT')
        await asyncio.sleep(delay / 1000)
        while self.get_heater_status():
            await asyncio.sleep(10)


class TeslatronPT:
    def __init__(self, rm = None, *, connect:bool=False):
        self.itc = iTC('TCPIP0::192.168.0.20::7020::SOCKET', rm=rm)
        self.ips = iPS('TCPIP0::192.168.0.30::7020::SOCKET', rm=rm)
        self._is_connected = False
        if connect:
            self.connect()
    
    def connect(self):
        if not self._is_connected:
            self.itc.connect()
            self.ips.connect()
            self._is_connected = True
    
    def disconnect(self):
        if self._is_connected:
            self.itc.disconnect()
            self.ips.disconnect()
            self._is_connected = False
    
    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.disconnect()
    
    def temp_snapshot(self) -> dict[str, float]:
        return {
            'probe_temp': self.itc.get_probe_temp(),
            'VTI_temp': self.itc.get_VTI_temp(),
            'pressure': self.itc.get_pres(),
            'NV_flow': self.itc.get_flow(),
            'magnet_temp': self.ips.get_magnet_temp(),
            'PT2_temp': self.ips.get_PT2_temp(),
            'PT1_temp': self.ips.get_PT1_temp()
        }
    
    def field_snapshot(self) -> dict[str, Union[str, float]]:
        return {
            'iPS_Bz': self.ips.get_field(),
            'iPS_action': self.ips.get_action(),
            'iPS_heater_ON': self.ips.get_heater_status()
        }
    
    def snapshot(self) -> dict[str, Union[str, float]]:
        return {
            **self.temp_snapshot(),
            **self.field_snapshot()
        }

    def warm_up(self, target_temp: float = 300):
        if target_temp < 0 or target_temp > 300:
            raise ValueError("PROBE_TEMP and VTI_TEMP must be in [0, 300]K.")
        self.itc.set_probe_loop_enable(True)
        self.itc.set_VTI_loop_enable(True)
        self.itc.set_probe_temp_setpoint(target_temp)
        self.itc.set_VTI_temp_setpoint(target_temp)