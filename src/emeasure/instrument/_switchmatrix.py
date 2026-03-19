from ._core import BaseInstrument
import pyvisa

class SwitchMatrix(BaseInstrument):
    def __init__(self, visa_address, rm = None):
        super().__init__(visa_address, rm)
        self._map = [0] * 24
    
    def connect(self, query_delay:float = 0.1) -> None:
        super().connect()
        self._res.write_termination = '\n'
        self._res.read_termination = '\n'
        self._res.query_delay = query_delay

        visa_type = self._res.get_visa_attribute(pyvisa.constants.VI_ATTR_INTF_TYPE)
        if visa_type == pyvisa.constants.VI_INTF_GPIB:
            ...
        elif visa_type == pyvisa.constants.VI_INTF_ASRL:
            self._res.baud_rate = 115200
        else:
            raise ConnectionError(f'Unknown VISA interface {visa_type} for the SwitchMatrix')
    
    def _validate_rear(self, r: int):
        if type(r) is not int or not (1 <= r <= 24):
            raise IndexError(f"rear port {r} is invalid, must be int in [1, 24]")

    def _validate_front(self, f: int):
        if type(f) is not int or not (0 <= f <= 6):
            raise ValueError(f"front port {f} is invalid, must be int in [0, 6]")
    
    def apply(self):
        s = ''.join(str(x) for x in self._map)
        cmd = f'[{s[:8]},{s[8:16]},{s[16:24]}]'
        self.write(cmd)
    
    def clear(self):
        self._map = [0] * 24
        self.apply()
    
    def _set_one(self, rear:int, front:int):
        self._validate_front(front)
        self._validate_rear(rear)
        self._map[rear - 1] = front
    
    def _set_list(self, rear:list[int], front:list[int]):
        if len(rear) != len(front):
            raise ValueError('rear and front lists must be the same length.')
        for r, f in zip(rear, front):
            self._set_one(r, f)
    
    def set(self, rear:int|list[int], front:int|list[int]):
        self._map = [0] * 24
        if isinstance(rear, int) and isinstance(front, int):
            self._set_one(rear, front)
        elif isinstance(rear, list) and isinstance(front, list):
            self._set_list(rear, front)
        else:
            raise TypeError('rear/front must both be in int or list of int')
        self.apply()
    
    
