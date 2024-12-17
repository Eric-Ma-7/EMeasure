from functools import wraps
import asyncio
import time
import numpy as np


# call a getter for N times with time interval of dt and return all results
def repeater(N):

    def decorator(func):

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # frames = await asyncio.gather(*[func(*args, **kwargs) for _ in range(N)])
            frames = [await func(*args, **kwargs) for _ in range(N)]
            return frames
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            frames = [func(*args, **kwargs) for _ in range(N)]
            return frames
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator
    


# call a getter for N times and return the mean value of the results
def averager(N):
    
    def decorator(func):

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # frames = await asyncio.gather(*[func(*args, **kwargs) for _ in range(N)])
            frames = [await func(*args, **kwargs) for _ in range(N)]
            frames = np.array(frames)
            return np.mean(frames, axis=0)

        @wraps(func)
        async def sync_wrapper(*args, **kwargs):
            frames = [func(*args, **kwargs) for _ in range(N)]
            frames = np.array(frames)
            return np.mean(frames, axis=0)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator
            