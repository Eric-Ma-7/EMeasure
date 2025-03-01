from .EmergencyStop import EmergencyStop
from ..ESave.DataSet import DataSet


from abc import ABC, abstractmethod
from typing import List

from collections import namedtuple

import time
    


class Scanner1D(ABC):
    
    def __init__(self, param) -> None:
        super().__init__()
        self.param = param
    
    
    @abstractmethod
    def initializer(self):
        pass
    
    
    @abstractmethod
    def finalizer(self):
        pass
    
    
    @abstractmethod
    def setter(self, p):
        pass
    
    
    @abstractmethod
    def getter(self):
        pass
    
    
    def __len__(self) -> int:
        return len(self.param)
    
    
    def __iter__(self):
        self.i = 0
        return self
    
    
    def __next__(self):
        if self.i < len(self.param):
            pset = self.param[self.i]
            self.setter(pset)
            frame = self.getter()
            self.i += 1
            return pset, frame
        else:
            raise StopIteration
    
    
    def __enter__(self):
        self.initializer()
        return self
    
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.finalizer()
        
    