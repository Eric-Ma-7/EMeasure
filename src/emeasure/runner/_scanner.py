import time
import threading
import numpy as np

from typing import Callable, Optional, Sequence
from dataclasses import dataclass

from ..instrument import TeslatronPT




@dataclass
class Scan1D:
    name: str
    values: Sequence[float]
    setter: Callable[[float], None]
    relax_time: float = 0.1
    befor_run_hook: Optional[Callable] = None
    after_run_hook: Optional[Callable] = None

    def __len__(self) -> int:
        return len(self.values)
    
    def __iter__(self):
        if self.befor_run_hook is not None:
            self.befor_run_hook()
        
        for value in self.values:
            self.setter(value)
            time.sleep(self.relax_time)
            yield {self.name: value}

        if self.after_run_hook is not None:
            self.after_run_hook()


class ScanTeslatronPTiPS(threading.Thread):
    def __init__(
        self,
        fridge: TeslatronPT,
        field_list: float | Sequence[float],
        rate_list: float | Sequence[float],
        pause_time: float | Sequence[float],

        poll_interval: float = 2,
        hook_poll: Optional[Callable] = None,
        auto_rtoz: bool = True,
    ):
        super().__init__(daemon=True)
        
        self.fridge = fridge
        self.field_list = list(field_list)
        self.rate_list = list(rate_list)
        self.pause_time = list(pause_time)
        self.poll_interval = poll_interval
        self.hook_poll = hook_poll
        self.auto_rtoz = auto_rtoz

        if len(self.rate_list) == 1:
            self.rate_list = self.rate_list * len(self.field_list)
        if len(self.pause_time) == 1:
            self.pause_time = self.pause_time * len(self.field_list)
        
        if any(abs(field) > 12 for field in self.field_list):
            raise ValueError("Maximum Field is 12T.")
        
        if any(rate > 0.2 for rate in self.rate_list):
            raise ValueError("Maximum ramping rate is 0.2T/min.")
    
    def time_estimate(self) -> float:
        ramp_min = np.sum(np.abs(np.diff(self.field_list)) / np.arange(self.rate_list[:-1]))
        pause_sec = np.sum(self.pause_time)
        return ramp_min * 60 + pause_sec

    def run(self):
        # ensure TeslatronPT is connected
        self.fridge.connect()

        # check iPS heater is ON
        if not self.fridge.ips.get_heater_status():
            print('[iPS Scanner] Heater is off. Turning ON.')
            self.fridge.ips.set_heater_on(is_wait=True)
        
        for field, rate, ptime in zip(self.field_list, self.rate_list, self.pause_time):
            self.fridge.ips.set_target_field(field)
            self.fridge.ips.set_ramp_rate(rate)
            self.fridge.ips.set_action('RTOS')

            while self.fridge.ips.get_action() == 'RTOS':
                if self.hook_poll is not None:
                    self.hook_poll()
                time.sleep(self.poll_interval)

            
            if not self.fridge.ips.get_action() == 'HOLD':
                raise ValueError(f"Unexpected ACTN for iPS: {self.fridge.ips.get_action()}")

            time.sleep(ptime)

        if self.auto_rtoz:
            self.fridge.ips.set_action('RTOZ')
        
