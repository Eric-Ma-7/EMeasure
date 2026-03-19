import numpy as np
import time
import asyncio
from typing import Mapping

def validate_enum_attr(var: str, valid_set: set[str], var_name: str):
    token = var.strip().upper()
    if token not in valid_set:
        raise ValueError(f'Invalid input {var} for {var_name}. Valid inputs are {valid_set}')
    else:
        return token

def generate_ramp_list(
    start:float, target:float, step:float, 
    *,
    with_start:bool=True, with_target:bool=True
):
    if target >= start:
        ramp = np.arange(start, target,  np.abs(step))
    else:
        ramp = np.arange(start, target, -np.abs(step))
        
    if not with_start:
        ramp = ramp[1:]
    
    if with_target:
        ramp = np.append(ramp, target)
    
    return ramp

def ramp_drive(set_value: Mapping[float, None], value_start: float, value_target: float, dv: float, dt: float):
    ramp = generate_ramp_list(value_start, value_target, dv, with_start=False, with_target=False)
    for v in ramp:
        set_value(v)
        time.sleep(dt)
    set_value(value_target)

async def aramp_drive(set_value: Mapping[float, None], value_start: float, value_target: float, dv: float, dt: float):
    ramp = generate_ramp_list(value_start, value_target, dv, with_start=False, with_target=False)
    for v in ramp:
        set_value(v)
        await asyncio.sleep(dt)
    set_value(value_target)