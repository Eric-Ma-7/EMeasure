import numpy as np
import h5py
import threading
from collections import defaultdict


class DataSaver():
    
    def __init__(self, 
                 fname:str, 
                 size:int|tuple[int], 
                 attrs:dict|None = None,
                 default_val:np.integer|np.floating|np.complexfloating=np.nan) -> None:
        self._lock = threading.Lock()
        
        self._fname = fname
        self._size = size
        self._defaul_val = default_val
        self._attrs = attrs
        
        self._is_recorded = np.full(size, False, dtype=bool)
        self._data = defaultdict(self._defaul_data)
        
    
    
    def _defaul_data(self) -> np.ndarray:
        return np.full(self._size, self._defaul_val)
    
    
    def set_attrs(self, attrs:dict[str,]) -> None:
        self._attrs = attrs
    
    
    @property
    def shape(self):
        return self._size
    
    
    def keys(self):
        with self._lock:
            return self._data.keys()
    
    
    def __getitem__(self, key) -> np.ndarray:
        with self._lock:
            return self._data[key]
    
    
    def add(self, frame:dict, index:int|tuple[int]):
        with self._lock:
            self._is_recorded[index] = True
            for key,val in frame.items():
                self._data[key][index] = val
    
    
    def save(self, nan:float=0, posinf:float=0, neginf:float=0):
        with self._lock:
            with h5py.File(self._fname, 'w') as f:
                g_info = f.create_group('info')
                g_info.create_dataset(name='is_recorded', data=self._is_recorded)
                
                if self._attrs:
                    for key,val in self._attrs.items():
                        f.attrs[key] = val
                
                for key,val in self._data.items():
                    val = np.nan_to_num(val, nan=nan, posinf=posinf, neginf=neginf)
                    f.create_dataset(name=key, data=val)
    