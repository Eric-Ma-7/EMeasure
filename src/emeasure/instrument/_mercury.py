from ._core import BaseInstrument, InstrumentError
from ._utils import validate_enum_attr
from typing import Optional, Tuple

import re
import pyvisa
import time
import threading

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


def _validate_dir(direction: str):
    if direction.upper() not in {'X', 'Y', 'Z'}:
        raise ValueError("DIR must be X, Y, or Z.")


class MercuryiPS(Mercury):
    _ACTN = {'HOLD', 'RTOS', 'RTOZ'}

    def __init__(self, visa_address, rm=None):
        super().__init__(visa_address, rm)
    
    def get_field(self, direction: str) -> float:
        _validate_dir(direction)
        return self.query_number(f'READ:DEV:GRP{direction.upper()}:PSU:SIG:PFLD')

    def get_action(self, direction: str) -> str:
        _validate_dir(direction)
        return self.query_str(f'READ:DEV:GRP{direction.upper()}:PSU:ACTN')
    
    def set_action(self, actn: str, direction: str):
        _validate_dir(direction)
        token = validate_enum_attr(actn, self._ACTN, 'IPS_ACTN')
        self.write_check_valid(f'SET:DEV:GRP{direction.upper()}:PSU:ACTN:{token}')
    
    def set_ramp_rate(self, rate: float, direction: str):
        _validate_dir(direction)
        if rate > 0.2:
            raise ValueError(f'Ramp rate must be smaller than 0.2 T/min. Now {rate} T/min.')
        self.write_check_valid(f'SET:DEV:GRP{direction.upper()}:PSU:SIG:RFST:{rate:.4f}')
    
    def set_target_field(self, B_target: float, direction: str):
        _validate_dir(direction)
        if B_target > 14:
            raise ValueError(f'Target magnetic field must be smaller than 14 T. Now {B_target} T.')
        self.write_check_valid(f'SET:DEV:GRP{direction.upper()}:PSU:SIG:FSET:{B_target:.6f}')
    
    # -------------------- Drive to field --------------------
    def wait_until_hold(self, direction: str, query_interval: float = 2):
        while self.get_action(direction) != 'HOLD':
            time.sleep(query_interval)
    
    def drive_to_field(self, B_target: float, rate: float, direction: str, *, query_interval: float = 2.0):
        self.set_action('HOLD', direction)
        self.set_target_field(B_target, direction)
        self.set_ramp_rate(rate, direction)
        self.set_action('RTOS', direction)
        self.wait_until_hold(direction, query_interval)