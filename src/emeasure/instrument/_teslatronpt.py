from ._core import BaseInstrument, InstrumentError
from ._utils import validate_enum_attr
from typing import Optional, Tuple, Union, Sequence

import re
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

_NUM_RE = re.compile(r"([-+]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*([A-Za-zΩµu%/]+)?$")

class Mercury(BaseInstrument):
    def __init__(self, visa_address, rm = None):
        super().__init__(visa_address, rm)
        self._thread_lock = threading.Lock()
    
    def write(self, cmd):
        with self._thread_lock:
            super().write(cmd)
    
    def read(self):
        with self._thread_lock:
            resp = super().read()
        return resp
    
    def query(self, cmd):
        with self._thread_lock:
            resp = super().query(cmd)
        return resp
    
    def connect(self):
        with self._thread_lock:
            super().connect()
            self._res.set_visa_attribute(pyvisa.constants.VI_ATTR_TERMCHAR, 0xa)
            self._res.set_visa_attribute(pyvisa.constants.VI_ATTR_TERMCHAR_EN, 0x1)
    
    def disconnect(self):
        with self._thread_lock:
            super().disconnect()
    
    def write_check_valid(self, cmd: str) -> str:
        resp = (self.query(cmd) or "").strip()
        if ':VALID' not in resp:
            raise InstrumentError(f'Mercury iTC rejected command: {resp or "no response"}')
    
    def query_check_stat(self, cmd: str) -> str:
        resp = (self.query(cmd) or "").strip()
        if not resp.startswith('STAT:'):
            raise InstrumentError(f'Mercury iTC unexpected reply: {resp or "no response"}')
        else:
            return resp
    
    def query_number(self, cmd: str, return_unit: bool = False) -> Tuple[float, Optional[str]]:
        resp = self.query_check_stat(cmd)
        tail = resp.split(':')[-1].strip()
        m = _NUM_RE.search(tail)
        if not m:
            raise InstrumentError(f"Mercury iTC cannot parse numeric from: {resp}")
        if return_unit:
            return float(m.group(1)), (m.group(2) or None)
        else:
            return float(m.group(1))
        
    def query_bool(self, cmd: str) -> bool:
        resp = self.query_check_stat(cmd)
        tail = resp.split(":")[-1].strip().upper()
        if tail in {"ON", "1", "TRUE"}:
            return True
        if tail in {"OFF", "0", "FALSE"}:
            return False
        raise InstrumentError(f"Mercury iTC cannot parse bool from: {resp}")
    
    def query_str(self, cmd: str) -> str:
        resp = self.query_check_stat(cmd)
        tail = resp.split(":")[-1].strip().upper()
        return tail

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


class IpsScanner(threading.Thread):
    def __init__(
            self, 
            ips: iPS,
            B_list: Sequence[float], 
            rate_list: Sequence[float], 
            pause_time: Sequence[float],
            epoch_label: Sequence[int] = None,
            query_interval: float = 1
    ):
        super().__init__()
        self.ips = ips
        self.B_list = B_list
        self.rate_list = rate_list
        self.pause_time = pause_time
        self.epoch_label = epoch_label if epoch_label is not None else range(1, len(B_list) + 1)
        self.query_interval = query_interval

        self._epoch = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        
        self._is_rtoz = None
    
    @property
    def epoch(self):
        return self._epoch
    
    def stop(self, is_rtoz:bool = True):
        self._stop.set()
        self._is_rtoz = is_rtoz
    
    def run(self):
        for b, rate, ptime, ep in zip(self.B_list, self.rate_list, self.pause_time, self.epoch_label):
            self._epoch = ep
            
            self.ips.set_ramp_rate(rate)
            self.ips.set_target_field(b)
            self.ips.set_action('RTOS')

            while (self.ips.get_action() == 'RTOS') and (not self._stop.is_set()):
                time.sleep(self.query_interval)
            
            if self._stop.is_set():
                break

            self._epoch = 0
            time.sleep(ptime)
        
        if self._is_rtoz:
            self.ips.set_action('RTOZ')

class TeslatronPT:
    def __init__(self, rm = None, *, connect:bool=False):
        self.itc = iTC('TCPIP0::192.168.0.20::7020::SOCKET', rm=rm)
        self.ips = iPS('TCPIP0::192.168.0.30::7020::SOCKET', rm=rm)
        if connect:
            self.connect()
    
    def connect(self):
        self.itc.connect()
        self.ips.connect()
    
    def disconnect(self):
        self.itc.disconnect()
        self.ips.disconnect()
    
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
            'Bz': self.ips.get_field(),
            'iPS_action': self.ips.get_action(),
            'iPS_heater_ON': self.ips.get_heater_status()
        }
    
