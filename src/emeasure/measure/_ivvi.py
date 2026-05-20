from typing import Sequence, Optional, Callable
from dataclasses import dataclass
from ..instrument import K2612
from ..saver import SqliteSaver
import numpy as np

@dataclass(frozen=True)
class IV_K2612:
    k2612: K2612
    data: SqliteSaver

    curr: Sequence[float]
    dI: float = 10e-9
    dt: float = 0.01
    channel: str = "a"
    relax_time: float = 0.1

    is_remote: bool = False
    volt_limit: float = 20
    is_clear_src: bool = True

    def __post_init__(self):
        if self.dI <= 0:
            raise ValueError(f'dI = {self.dI} <= 0')
        if self.dt < 0:
            raise ValueError(f'dt = {self.dt} < 0.')

    def _check_curr_step(self) -> bool:
        ...

    def total_time(self) -> float:
        ramp_time = np.abs(np.diff(self.curr)) / self.dI * self.dt
        relax_time = (len(self.curr) - 1) * self.relax_time
        return ramp_time + relax_time

    def _check_output_on(self) -> bool:
        if self.k2612.get_output_on(self.channel):
            print(f"K2612_CH{self.channel} must be at OFF state before the measurement.")
            return False
        else:
            return True
    
    def _initialization(self):
        self.k2612.set_source_func("i", self.channel)
        if self.is_remote:
            self.k2612.set_sense_mode("remote", self.channel)
        else:
            self.k2612.set_sense_mode("local", self.channel)
        self.k2612.set_volt_limit(self.volt_limit)
    
    def _finalization(self):
        if self.is_clear_src:
            self.k2612.set_curr_ramp(0, )
