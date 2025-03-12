from .EIns import EIns

import time
import numpy as np



class K2612(EIns):

    def __init__(self, resource_name:str) -> None:
        super().__init__(resource_name)
    

    def set_voltage(self, voltage:float, channel:str) -> None:
        self.write(f'smu{channel}.source.levelv = {voltage}')
    

    def set_current(self, current:float, channel:str) -> None:
        self.write(f'smu{channel}.source.leveli = {current}')
    

    def get_current(self, channel:str) -> float:
        response = self.query(f'print(smu{channel}.measure.i())')
        return float(response.strip())
    

    def get_voltage(self, channel:str) -> float:
        response = self.query(f"print(smu{channel}.measure.v())")
        return float(response.strip())


    def get_iv(self, channel:str) -> tuple[float]:
        response = self.query(f"print(smu{channel}.measure.iv())")
        iv = [float(x) for x in response.split()]
        return tuple(iv)
    


    def set_current_ramp(self, current, dI, dt, channel):
        now_current = self.get_current(channel=channel)
        if now_current is None:
            raise ValueError("Failed to get current current value")
        
        step = dI if current>now_current else -dI
        for i in np.arange(now_current, current, step):
            self.set_current(i, channel=channel)
            time.sleep(dt)
        
        self.set_current(current, channel=channel)
    

    def set_voltage_ramp(self, voltage, dV, dt, channel):
        now_voltage = self.get_voltage(channel=channel)
        if now_voltage is None:
            raise ValueError("Failed to get current voltage value")
        
        step = dV if voltage>now_voltage else -dV
        for v in np.arange(now_voltage, voltage, step):
            self.set_voltage(v, channel=channel)
            time.sleep(dt)

        self.set_voltage(voltage, channel=channel)


    def set_output_state(self, state:str, channel:str) -> None:
        if state.lower() not in ['on','off']:
            raise ValueError("State must be 'on' or 'off'")
        state_command = '1' if state.lower() == 'on' else '0'
        command = f'smu{channel}.source.output = {state_command}'
        self.write(command)
    

    def set_voltage_limit(self, voltage_limit:float, channel:str) -> None:
        command = f"smu{channel}.source.limitv = {voltage_limit}"
        self.write(command)
    

    def set_current_limit(self, current_limit:float, channel:str) -> None:
        command = f"smu{channel}.source.limiti = {current_limit}"
        self.write(command)


    def set_current_range(self, current_range:float, channel:str) -> None:
        command = f"smu{channel}.source.rangei = {current_range}"
        self.write(command)


    def set_voltage_range(self, voltage_range:float, channel:str) -> None:
        command = f"smu{channel}.source.rangev = {voltage_range}"
        self.write(command)


    def set_measurement_mode(self, measurement_mode:str, channel:str) -> None:
        if measurement_mode.lower() not in ['2-wire', '4-wire']:
            raise ValueError("Measurement mode must be '2-wire' or '4-wire'")
        if measurement_mode.lower() == '4-wire':
            command = f"smu{channel}.sense = smu{channel}.SENSE_REMOTE"
        else:
            command = f"smu{channel}.sense = smu{channel}.SENSE_LOCAL"
        self.write(command)


    def set_mode(self, mode:str, channel:str) -> None:
        if mode.lower() not in ['current', 'voltage']:
            raise ValueError("Mode must be 'current' or 'voltage'")
        if mode.lower() == 'current':
            command = f"smu{channel}.source.func = smu{channel}.OUTPUT_DCAMPS"
        else:
            command = f"smu{channel}.source.func = smu{channel}.OUTPUT_DCVOLTS"
        self.write(command)
    
    
    



class K2182(EIns):

    def __init__(self, resource_name:str) -> None:
        super().__init__(resource_name)
    
    
    def get_data(self):
        response = self.query(":fetch?")
        return float(response.strip())
