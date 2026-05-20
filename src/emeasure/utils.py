import numpy as np

def linspace(
    start: float, stop: float, N: int, 
    *,
    with_backward: bool = False,
) -> np.ndarray:
    x = np.linspace(start, stop, N)
    if with_backward:
        return np.hstack([x, x[::-1]])
    else:
        return x.copy()

def create_loop(
    center_value: float, max_value: float, N: int,
    with_left: bool = True
) -> np.ndarray:
    x = np.linspace(center_value, max_value, N)
    if with_left:
        return np.hstack([x, x[::-1], -x, -x[::-1]])
    else:
        return np.hstack([x, x[::-1]])

