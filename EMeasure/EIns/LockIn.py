from .EIns import EIns
from typing import List, Dict
from enum import IntEnum


class NF5650_STATUS(IntEnum):
    NORM    = 0
    PROTECT = 1
    INPUT   = 2
    OUTPUT  = 4
    AUX     = 8
    UNLOCK  = 16


class NF5650(EIns):
    def __init__(self, resource_name):
        super().__init__(resource_name)
        
    
    def set_sense_data(self, *data) -> None:
        data_mapping = {'status':1, 'data1': 2, 'data2': 4, 'data3': 8, 'data4': 16, 'freq':32}
        selected_data = sum(data_mapping[d.lower()] for d in data if d.lower() in data_mapping)
        if selected_data == 0:
            raise ValueError("At least one of data1, data2, data3, data4 must be specified")
        command = f'SENS:DATA {selected_data}'
        self.write(command)


    def fetch_data(self):
        response = self.query('FETCH?')
        data = response.strip().split(',')
        return tuple([float(d) for d in data])
    
    
    def get_intosc_frequency(self) -> float:
        return float(self.query(f':source:frequency?'))
    
    
    def set_intosc_frequency(self, freq:float) -> None:
        self.write(f':source:frequency {freq}')
    
    
    def get_intosc_voltage(self) -> float:
        return float(self.query(':source:voltage?'))
    
    
    def set_intosc_voltage(self, voltage:float) -> None:
        self.write(f':source:voltage {voltage}')
    
    
    def get_intosc_voltage_range(self) -> float:
        return float(self.query(':source:voltage:range'))
    
    
    def set_intosc_voltage_range(self, vrange:float) -> None:
        self.write(f':source:voltage:range {vrange}')