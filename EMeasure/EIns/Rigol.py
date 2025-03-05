from .EIns import EIns
import time


class DG1022(EIns):

    def __init__(self, resource_name:str) -> None:
        super().__init__(resource_name)
    

    def query(self, command:str) -> None:
        '''
        For RIGOL DG1022, if try to read from the intrument after writing to it instataneously,
        the program will throw a TIMEOUT error.
        A short waiting time is necessary for the instrument to response.
        '''
        with self._lock:
            if self.device:
                try:
                    self.device.write(command)
                    time.sleep(5e-2)
                    response = self.device.read()
                    return response
                except Exception as e:
                    print(f"Failed to query '{command}' from {self.resource_name}: {e}")
                    return None


    def _header_add_channel(self, cmd:str, channel:int=1) -> str:
        if channel == 1:
            return cmd
        elif channel == 2:
            return cmd + ':ch2'
        else:
            raise ValueError(f'Channel is expected to be 1 or 2, but {channel} is received.')


    def get_waveform_info(self, channel:int=1) -> dict:
        header = self._header_add_channel('apply', channel)
        resp = self.query(f'{header}?').strip()
        resp = resp[len("CHx:'"):-1].split(',')
        return {
            'type': resp[0],
            'frequency': float(resp[1]),
            'amplitude': float(resp[2]),
            'offset': float(resp[3])
        }
    

    def set_waveform(self, type:str, 
                     frequency:float, 
                     amplitude:float, 
                     offset:float, 
                     channel:int=1) -> None:
        
        header = self._header_add_channel(f'apply:{type}', channel)
        self.write(f'{header} {frequency},{amplitude},{offset}')


    def get_output_state(self, channel:int=1) -> str:
        header = self._header_add_channel('output', channel)
        return self.query(f'{header}?')
    

    def set_output_state(self, state, channel:int=1) -> None:
        header = self._header_add_channel('output', channel)
        self.write(f'{header} {state}')
    
    
    def get_voltage_amplitude(self, channel:int=1) -> float:
        header = self._header_add_channel('voltage', channel)
        return float(self.query(f'{header}?'))
    
    
    def set_voltage_amplitude(self, amplitude:float, channel:int=1) -> None:
        header = self._header_add_channel('voltage', channel)
        self.write(f'{header} {amplitude}')
    
    
    def get_voltage_offset(self, channel:int=1) -> float:
        header = self._header_add_channel('voltage:offset', channel)
        return float(self.query(f'{header}?'))
    
    
    def set_voltage_offset(self, offset:float, channel:int=1) -> None:
        header = self._header_add_channel('voltage:offset', channel)
        self.write(f'{header} {offset}')
    
    
    def get_voltage_high(self, channel:int=1) -> float:
        header = self._header_add_channel('voltage:high', channel)
        return float(self.query(f'{header}?'))
    
    
    def set_voltage_high(self, voltage_high:float, channel:int=1) -> None:
        header = self._header_add_channel('voltage:high', channel)
        self.write(f'{header} {voltage_high}')
    
    
    def get_voltage_low(self, channel:int=1) -> float:
        header = self._header_add_channel('voltage:low', channel)
        return float(self.query(f'{header}?'))
    
    
    def set_voltage_low(self, voltage_low:float, channel:int=1) -> None:
        header = self._header_add_channel('voltage:low', channel)
        self.write(f'{header} {voltage_low}')
    
    
    def get_voltage_unit(self, channel:int=1) -> str:
        '''
        unit = VPP | VRMS | DBM
        '''
        header = self._header_add_channel('voltage:unit', channel)
        return self.query(f'{header}?')
    
    
    def set_voltage_unit(self, unit:str, channel:int=1) -> None:
        '''
        unit = VPP | VRMS | DBM
        '''
        header = self._header_add_channel('voltage:unit', channel)
        self.write(f'{header} {unit}')
    
    
    def get_frequency(self, channel:int=1) -> float:
        header = self._header_add_channel('frequency', channel)
        return float(self.query(f'{header}?'))
    
    
    def set_frequency(self, frequency:float, channel:int=1) -> None:
        header = self._header_add_channel('frequency', channel)
        self.write(f'{header} {frequency}')

    
    def set_phase_align(self) -> None:
        self.write('phase:align')