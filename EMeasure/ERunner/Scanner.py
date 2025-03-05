from abc import ABC, abstractmethod
from enum import StrEnum, auto
from typing import Generator
from collections import namedtuple

import time
import numpy as np



class SCAN_MODE(StrEnum):
    FORWARD  = auto()
    BACKWARD = auto()
    LOOP     = auto()


class ScanTools():
    
    @staticmethod
    def dict2list(param:dict[list|np.ndarray]) -> list:
        # check the lengthes of every variables are equal
        var_len = [len(val) for key,val in param.items()]
        if len(set(var_len)) > 1:
            raise ValueError(f'All variables in param must be equal.')
        else:
            var_len = var_len[0]
            param_set = [
                {k:param[k][i] for k in param.keys()} for i in range(var_len)
            ]
            return param_set

    
    @staticmethod
    def reshape_param(param:np.ndarray, mode:SCAN_MODE) -> list:
        if mode == SCAN_MODE.FORWARD:
            return param
        elif mode == SCAN_MODE.BACKWARD:
            return list(reversed(param))
        elif mode == SCAN_MODE.LOOP:
            return param + list(reversed(param))
        else:
            raise ValueError(f'Unsupported SCAN MODE occured: {mode}')



class Scanner1D(ABC):
    
    def __init__(self, 
                 param:dict[list|np.ndarray], 
                 mode:SCAN_MODE=SCAN_MODE.FORWARD) -> None:
        
        super().__init__()
        self.param = ScanTools.reshape_param(
            param=ScanTools.dict2list(param), 
            mode=mode
        )
        

    @abstractmethod
    def initializer(self):
        pass
    
    
    @abstractmethod
    def finalizer(self):
        pass
    
    
    @abstractmethod
    def setter(self, param_to_set:dict):
        pass
    
    
    @abstractmethod
    def getter(self):
        pass
    
    
    def loop(self) -> Generator:
        for i in range(len(self.param)):
            pset = self.param[i]
            self.setter(pset)
            frame = self.getter()
            yield i, pset, frame
            
    
    def __len__(self) -> int:
        return len(self.param)
    
    
    def __enter__(self):
        self.initializer()
        return self.loop()
    
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.finalizer()



class Scanner2D(ABC):
    
    def __init__(self, 
                 outer:dict[list|np.ndarray], 
                 inner:dict[list|np.ndarray],
                 outer_mode:SCAN_MODE=SCAN_MODE.FORWARD,
                 inner_mode:SCAN_MODE=SCAN_MODE.FORWARD) -> None:
        
        super().__init__()
        
        self.outer = ScanTools.reshape_param(
            param = ScanTools.dict2list(outer), 
            mode = outer_mode
        )
        
        self.inner = ScanTools.reshape_param(
            param = ScanTools.dict2list(inner),
            mode = inner_mode
        )
        

    @abstractmethod
    def initializer(self):
        pass
    
    
    @abstractmethod
    def finalizer(self):
        pass
    
    
    @abstractmethod
    def setter_inner(self, param_to_set:dict):
        pass
    
    
    @abstractmethod
    def setter_outer(self, param_to_set:dict):
        pass
    
    
    @abstractmethod
    def getter(self):
        pass
    
    
    def loop(self) -> Generator:
        for i in range(len(self.outer)):
            p_outer = self.outer[i]
            self.setter_outer(p_outer)
            
            for j in range(len(self.inner)):
                p_inner = self.inner[j]
                self.setter_inner(p_inner)
                
                frame = self.getter()
                yield (i, j), {**p_outer, **p_inner}, frame
    
    
    @property
    def shape(self) -> tuple[int]:
        return (len(self.outer), len(self.inner))
    
    
    def __len__(self) -> int:
        return len(self.outer) * len(self.inner)

    
    def __enter__(self):
        self.initializer()
        return self.loop()
    
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.finalizer()