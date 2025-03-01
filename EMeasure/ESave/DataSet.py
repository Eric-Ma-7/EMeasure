import numpy as np
import threading
import copy

from typing import List, Dict, Any
from collections import defaultdict



class DataSet():
    
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data = defaultdict(list)
    
    
    def append(self, frame: dict) -> None:
        with self._lock:
            for key, value in frame.items():
                self._data[key].append(value)
    
    
    def __len__(self) -> int:
        with self._lock:
            if len(self._data) == 0:
                return 0
            else:
                length = [len(self._data[key]) for key in self._data.keys()]
        
        if len(np.unique(length)) == 1:
            return length[0]
        else:
            raise ValueError(f'The length of each elements are not equal')
    
    
    def __getitem__(self, key: str) -> Any:
        with self._lock:
            if key in self._data.keys():
                return self._data[key]
            else:
                raise KeyError(f'There is NO {key} in the dataset. Valid variables are {self._data.keys()}')
    
    
    def keys(self) -> List[str]:
        with self._lock:
            return self._data.keys()