import time
import numpy as np
from .EIns import EIns


class K2612(EIns):

    def __init__(self, resource_name):
        super().__init__(resource_name)
    

    def set_voltage(self, voltage, channel):
        command = f'smu{channel}.source.levelv = {voltage}'
        self.write(command)
    

    def set_current(self, current, channel):
        command = f'smu{channel}.source.leveli = {current}'
        self.write(command)
    

    def get_current(self, channel):
        command = f'print(smu{channel}.measure.i())'
        response = self.query(command)
        try:
            current = float(response.strip())
            return current
        except ValueError as e:
            print(f'Failed to conver response to float: {e}')
            return None
    

    def get_voltage(self, channel):
        command = f"print(smu{channel}.measure.v())"
        response = self.query(command)
        try:
            voltage = float(response.strip())
            return voltage
        except ValueError as e:
            print(f"Failed to convert response to float: {e}")
            return None


    def get_iv(self, channel):
        command = f"print(smu{channel}.measure.iv())"
        response = self.query(command)
        try:
            iv = [float(x) for x in response.split()]
            return tuple(iv)
        except ValueError as e:
            print(f"Failed to convert response to float: {e}")
            return None


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


    def set_output_state(self, state, channel):
        if state.lower() not in ['on','off']:
            raise ValueError("State must be 'on' or 'off'")
        state_command = '1' if state.lower() == 'on' else '0'
        command = f'smu{channel}.source.output = {state_command}'
        self.write(command)
    

    def set_voltage_limit(self, voltage_limit, channel):
        command = f"smu{channel}.source.limitv = {voltage_limit}"
        self.write(command)
    

    def set_current_limit(self, current_limit, channel):
        command = f"smu{channel}.source.limiti = {current_limit}"
        self.write(command)


    def set_current_range(self, current_range, channel):
        command = f"smu{channel}.source.rangei = {current_range}"
        self.write(command)


    def set_voltage_range(self, voltage_range, channel):
        command = f"smu{channel}.source.rangev = {voltage_range}"
        self.write(command)


    def set_measurement_mode(self, measurement_mode, channel):
        if measurement_mode.lower() not in ['2-wire', '4-wire']:
            raise ValueError("Measurement mode must be '2-wire' or '4-wire'")
        if measurement_mode.lower() == '4-wire':
            command = f"smu{channel}.sense = smu{channel}.SENSE_REMOTE"
        else:
            command = f"smu{channel}.sense = smu{channel}.SENSE_LOCAL"
        self.write(command)


    def set_mode(self, mode, channel):
        if mode.lower() not in ['current', 'voltage']:
            raise ValueError("Mode must be 'current' or 'voltage'")
        if mode.lower() == 'current':
            command = f"smu{channel}.source.func = smu{channel}.OUTPUT_DCAMPS"
        else:
            command = f"smu{channel}.source.func = smu{channel}.OUTPUT_DCVOLTS"
        self.write(command)



class K2182(EIns):

    def __init__(self, resource_name):
        super().__init__(resource_name)
    
    
    def get_data(self):
        command = ":fetch?"
        response = self.query(command)
        try:
            data = float(response.strip())
            return data
        except ValueError as e:
            print(f"Failed to convert response to float: {e}")
            return None