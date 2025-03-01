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


    def get_waveform_info(self, channel:int=1) -> dict:
        if channel == 1:
            resp = self.query('apply?').strip()
        else:
            resp = self.query('apply:ch2?').strip()
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
        
        if channel == 1:
            self.write(f'apply:{type} {frequency},{amplitude},{offset}')
        elif channel == 2:
            self.write(f'apply:{type}:ch2 {frequency},{amplitude},{offset}')
        else:
            raise ValueError(f'Channel is expected to be 1 or 2, but {channel} is received.')



    def get_output_state(self, channel:int=1):
        if channel == 1:
            return self.query(f'output?')
        elif channel == 2:
            return self.query(f'output:ch2?')
        else:
            raise ValueError(f'Channel is expected to be 1 or 2, but {channel} is received.')
    

    def set_output_state(self, state, channel:int=1):
        if channel == 1:
            return self.write(f'output {state}')
        elif channel == 2:
            return self.write(f'output:ch2 {state}')
        else:
            raise ValueError(f'Channel is expected to be 1 or 2, but {channel} is received.')