from .EIns import EIns
import numpy as np

from typing import List, Dict


class DSO9104A(EIns):

    def __init__(self, resource_name:str) -> None:
        super().__init__(resource_name)
    
    
    def query_value(self, command:str) -> float | None:
        resp = self.query(command).strip()
        try:
            return float(resp)
        except ValueError as e:
            print(f"Failed to convert response to float: {e}")
            return None
    
    
    def _get_waveform(self, channel:int) -> dict:
        self.write(f':waveform:source channel{channel}')
        resp = self.query(':waveform:data?')
        resp = resp.strip().rstrip(',')
        
        waveform = {
            'xOrg': float(self.query(':waveform:xorigin?').strip()),
            'xInc': float(self.query(':waveform:xincrement?').strip()),
            'xUnits': self.query(':waveform:xunits?').strip(),
            'yOrg': float(self.query(':waveform:yorigin?').strip()),
            'yInc': float(self.query(':waveform:yincrement?').strip()),
            'yUnits': self.query(':waveform:yunits?').strip(),
            'yData': [float(s) for s in resp.split(',')]
        }
        
        return waveform
        
    
    
    def capture_waveform(self, channel:int|List[int]):
        self.write(':waveform:streaming off')
        self.write(':waveform:format ascii')
        self.write(':digitize')
        
        try:
            if isinstance(channel, int):
                waveform = self._get_waveform(channel)
            else:
                waveform = [self._get_waveform(ch) for ch in channel]
        finally:
            self.write(':run')
        
        return waveform
    

    def set_sample_rate(self, fs:float|str) -> None:
        # fs = AUTO | MAX | <rate>
        self.write(f':acquire:srate {fs}')
    

    def get_sample_rate(self) -> float|None:
        return self.query_value(':acquire:srate?')
    
    
    def set_x_range(self, xrange:float) -> None:
        # xrange is a real number for the horizontal time, in seconds.
        # xrange in [50ps, 200s]
        self.write(f':timebase:range {xrange}')
    

    def get_x_range(self) -> float|None:
        return self.query_value(':timebase:range?')
    
    
    def set_y_scale(self, scale:float, channel:int|List[int]) -> None:
        if isinstance(channel, list):
            for ch in channel:
                self.write(f':channel{ch}:scale {scale}')
        else:
            self.write(f':channel{channel}:scale {scale}')
    

    def get_y_scale(self, channel:int) -> float|None:
        return self.query_value(f':channel{channel}:scale?')
    
    
    def set_y_offset(self, offset:float, channel:int|List[int]) -> None:
        if isinstance(channel, list):
            for ch in channel:
                self.write(f':channel{ch}:offset {offset}')
        else:
            self.write(f':channel{channel}:offset {offset}')
    

    def get_y_offset(self, channel:int) -> float|None:
        return self.query_value(f':channel{channel}:offset?')
    
    
    def set_trigger_mode(self, mode:str) -> None:
        '''
        mode = EDGE | GLITch | PATTern | STATe | DELay | TIMeout | TV | 
            COMM | RUNT | SEQuence | SHOLd | TRANsition | WINDow | 
            PWIDth | ADVanced | SBUS<N>
        '''
        self.write(f':trigger:mode {mode}')
    
    
    def get_trigger_mode(self) -> str:
        return self.query(':trigger:mode?')
    
    
    def set_trigger_level(self, channel:int, level:float) -> None:
        self.write(f':trigger:level channel{channel}, {level}')
    
    
    # TODO:
    # def get_trigger_level(self, channel:int) -> float:
    #     return 0
    
    
    def set_acquire_mode(self, mode:str) -> None:
        '''
        mode = ETIMe | RTIMe | PDETect | HRESolution | SEGMented | SEGPdetect | SEGHres
        '''
        self.write(f':acquire:mode {mode}')
    
    
    def get_acquire_mode(self) -> str:
        return self.query(':acquire:mode?')

    
    def autoscale_vertical(self, channel: int) -> None:
        self.write(f':autoscale:vertical channel{channel}')
    
    
    def autoscale(self) -> None:
        self.write(':autoscale')
        
    
    def run(self) -> None:
        self.wrire(':run')
    
    
    def stop(self) -> None:
        self.write(':stop')
    
    
    def single(self) -> None:
        self.write(':single')
    
    
    def digitize(self) -> None:
        self.write(':digitize')
