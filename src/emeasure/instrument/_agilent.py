from ._core import BaseInstrument
from typing import Sequence
from pathlib import Path
import h5py
import json
import time

class B2902(BaseInstrument):
    
    # --------------- Source mode & output ---------------
    def set_mode(self, mode: str, channel:int):
        if mode.lower() in {'i', 'curr', 'current'}:
            self.write(f':SOUR{channel}:FUNC:MODE CURR')
        elif mode.lower() in {'v', 'volt', 'voltage'}:
            self.write(f':SOUR{channel}:FUNC:MODE VOLT')
    
    def get_mode(self, channel:int):
        return self.query(f':SOUR{channel}:FUNC:MODE?').strip()
    
    def set_output_on(self, is_on, channel:int):
        if is_on:
            self.write(f':OUTP{channel} ON')
        else:
            self.write(f':OUTP{channel} OFF')
    
    def get_output_on(self, channel:int) -> bool:
        resp = int(self.query(f':OUTP{channel}:STAT?'))
        if resp == 1:
            return True
        elif resp == 0:
            return False
        else:
            raise ValueError(f'An Unknow OUTP:STAT is read: {resp}')
    
    # --------------- Source Value ---------------
    def set_curr(self, curr:float, channel:int):
        self.write(f':SOUR{channel}:CURR {curr}')
    
    def get_curr_setpoint(self, channel: int) -> float:
        return float(self.query(f':SOUR{channel}:CURR?'))
    
    def set_volt(self, volt:float, channel:int):
        self.write(f':SOUR{channel}:VOLT {volt}')
    
    def get_volt_setpoint(self, channel: int) -> float:
        return float(self.query(f':SOUR{channel}:VOLT?'))
    
    def set_src_value(self, val:float, channel:int):
        mode = self.get_mode(channel)
        if mode == 'CURR':
            self.set_curr(val, channel)
        elif mode == 'VOLT':
            self.set_volt(val, channel)
        else:
            raise ValueError(f'An unknown source mode is receivec: {mode}')
    
    def get_src_value(self, channel:int) -> float:
        mode = self.get_mode(channel)
        if mode == 'CURR':
            return self.get_curr_setpoint(channel)
        elif mode == 'VOLT':
            return self.get_volt_setpoint(channel)
        else:
            raise ValueError(f'An unknown source mode is receivec: {mode}')
    
    # --------------- Source Range ---------------
    def set_curr_src_range(self, curr_range:float, channel:int):
        self.write(f':SOUR{channel}:CURR:RANG {curr_range}')
    
    def set_volt_src_range(self, volt_range:float, channel:int):
        self.write(f':SOUR{channel}:VOLT:RANG {volt_range}')
    
    def set_src_range(self, src_range:float, channel:int):
        mode = self.get_mode(channel)
        if mode == 'CURR':
            return self.get_curr_src_range(src_range, channel)
        elif mode == 'VOLT':
            return self.get_volt_src_range(src_range, channel)
        else:
            raise ValueError(f'An unknown source mode is receivec: {mode}')
    
    def set_curr_src_range_auto(self, is_auto:bool, channel:int):
        if is_auto:
            self.write(f':SOUR{channel}:CURR:RANG:AUTO ON')
        else:
            self.write(f':SOUR{channel}:CURR:RANG:AUTO OFF')
    
    def set_volt_src_range_auto(self, is_auto:bool, channel:int):
        if is_auto:
            self.write(f':SOUR{channel}:VOLT:RANG:AUTO ON')
        else:
            self.write(f':SOUR{channel}:VOLT:RANG:AUTO OFF')
    
    def set_src_range_auto(self, is_auto:bool, channel:int):
        mode = self.get_mode(channel)
        if mode == 'CURR':
            return self.set_curr_src_range_auto(is_auto, channel)
        elif mode == 'VOLT':
            return self.set_volt_src_range_auto(is_auto, channel)
        else:
            raise ValueError(f'An unknown source mode is receivec: {mode}')
    
    # --------------- Remote Sense ---------------
    def set_remote_sense(self, is_remote:bool, channel:int):
        if is_remote:
            self.write(f':SENS{channel}:REM ON')
        else:
            self.write(f':SENS{channel}:REM OFF')
    
    def get_remote_sense(self, channel:int) -> bool:
        resp = self.query(f':SENS{channel}:REM?').strip().upper()
        if resp == 'ON':
            return True
        elif resp == 'OFF':
            return False
        else:
            raise ValueError(f'A Unknow :SENSx:REM is received: {resp}')
    
    # --------------- Measure VI ---------------
    def set_form_elem(self, elem: Sequence[str]):
        # To Measure VI, set elem = ['VOLT', 'CURR']
        token = ','.join(elem)
        self.write(f':FORM:ELEM:SENS {token}')
            
    def measure(self, channel_sel_token:str='(@1)'):
        resp = self.query(f':MEAS? {channel_sel_token}').strip()
        data = [float(s) for s in resp.split(',')]
        return data


class DSO9104A(BaseInstrument):
    def run(self):
        self.wrire(':run')
    
    def stop(self):
        self.write(':stop')
    
    def single(self):
        self.write(':single')
    
    def digitize(self):
        self.write(':digitize')

    def autoscale_vertical(self, channel: int):
        self.write(f':autoscale:vertical channel{channel}')
    
    def autoscale(self):
        self.write(':autoscale')
    
    # -------------------- Fs, x, y, trigger system --------------------
    def set_sample_rate(self, fs:float|str):
        # fs = AUTO | MAX | <rate>
        self.write(f':acquire:srate {fs}')
    
    def get_sample_rate(self) -> float:
        return float(self.query(':acquire:srate?'))
    
    def set_x_range(self, xrange:float):
        # xrange is a real number for the horizontal time, in seconds.
        # xrange in [50ps, 200s]
        self.write(f':timebase:range {xrange}')
    
    def get_x_range(self) -> float:
        return float(self.query(':timebase:range?'))
    
    def set_x_offset(self, xoffset:float):
        self.write(f':timebase:position {xoffset}')
    
    def get_x_offset(self) -> float:
        return float(self.query(f':timebase:position?'))
    
    def set_y_scale(self, scale:float, channel:int|list[int]):
        if isinstance(channel, list):
            for ch in channel:
                self.write(f':channel{ch}:scale {scale}')
        else:
            self.write(f':channel{channel}:scale {scale}')
    
    def get_y_scale(self, channel:int) -> float:
        return float(self.query(f':channel{channel}:scale?'))
    
    def set_y_offset(self, offset:float, channel:int|list[int]):
        if isinstance(channel, list):
            for ch in channel:
                self.write(f':channel{ch}:offset {offset}')
        else:
            self.write(f':channel{channel}:offset {offset}')
    
    def get_y_offset(self, channel:int) -> float:
        return float(self.query(f':channel{channel}:offset?'))
    
    def set_trigger_mode(self, mode:str):
        '''
        mode = EDGE | GLITch | PATTern | STATe | DELay | TIMeout | TV | 
            COMM | RUNT | SEQuence | SHOLd | TRANsition | WINDow | 
            PWIDth | ADVanced | SBUS<N>
        '''
        self.write(f':trigger:mode {mode}')
    
    def get_trigger_mode(self) -> str:
        return self.query(':trigger:mode?')
    
    def set_trigger_sweep(self, sweep:str):
        '''
        sweep = AUTO | TRIGgered | SINGle
        '''
        self.write(f':trigger:sweep {sweep}')
    
    def get_trigger_sweep(self) -> str:
        return self.query(':trigger:sweep?').strip()
    
    def set_trigger_level(self, channel:int, level:float):
        self.write(f':trigger:level channel{channel}, {level}')
    
    # -------------------- Fs, x, y, trigger system --------------------
    def get_channel_enable(self, channel:int) -> bool:
        enable = bool(int(self.query(f":channel{channel}:display?")))
        return enable
    
    def set_channel_enable(self, enable: bool, channel: int):
        if enable:
            self.write(f':channel{channel}:display ON')
        else:
            self.write(f':channel{channel}:display OFF')
    
    # -------------------- Waveform: to workspace --------------------
    def _get_single_waveform(self, channel: int) -> dict:
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
    
    def capture_waveform(self, channel:int|list[int], *, wait_time=0.1) -> dict|list[dict]:
        self.write(':waveform:streaming off')
        self.write(':waveform:format ascii')
        self.write(':digitize')
        time.sleep(wait_time)
        try:
            if isinstance(channel, int):
                waveform = self._get_single_waveform(channel)
            else:
                waveform = [self._get_single_waveform(ch) for ch in channel]
        finally:
            self.write(':run')
        
        return waveform
    

    # -------------------- Waveform: to file --------------------
    def capture_and_save(
            self, channel:int|list[int], h5file: str, 
            *, 
            is_overwrite:bool=True, meta:dict=None,
            wait_time:float=0.1,
    ):
        if (not is_overwrite) and (Path(h5file).exists()):
            raise FileExistsError(f"{h5file} has already exsited!")
        
        # channel index check
        ch_list = [channel] if isinstance(channel, int) else channel
        for ch in ch_list:
            if ch not in {1,2,3,4}:
                raise ValueError("Channel index must in {1,2,3,4}")
            if not self.get_channel_enable(ch):
                raise RuntimeError(f"Channel {ch} is DISABLED.")
        
        # read and save waveform
        wvf = self.capture_waveform(ch_list, wait_time=wait_time)
        with h5py.File(h5file, mode='w') as f:
            # load sample rate
            f.attrs["sample_rate"] = self.get_sample_rate()

            # load user defined meta data
            if meta is not None:
                f.attrs["meta"] = json.dumps(meta)
            
            # load waveforms
            for ind, w in zip(ch_list, wvf):
                g = f.create_group(f"CH{ind}")
                for key, val in w.items():
                    g.create_dataset(name=key, data=val)

        
        

