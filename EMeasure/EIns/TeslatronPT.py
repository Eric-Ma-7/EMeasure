import pyvisa
import math
import time

from .EIns import EIns
from .IPS import MercuryIPS

class ITC(EIns):

    def __init__(self, resource_name):
        super().__init__(resource_name)
    

    def connect(self):
        super().connect()
        self.device.set_visa_attribute(pyvisa.constants.VI_ATTR_TERMCHAR, 0xa)
        self.device.set_visa_attribute(pyvisa.constants.VI_ATTR_TERMCHAR_EN, 0x1)
    

    def disconnect(self):
        return super().disconnect()
    

    def _write_check(self, command):
        response = self.query(command)
        response = response.strip()
        flag = response[len(f"STAT:{command}:"):]
        if flag != 'VALID':
            raise ValueError(f"Failed to execute command: {command}")
    

    def _read_value(self, command, unit=''):
        response = self.query(command)
        response = response.strip()
        try:
            response = response.rstrip(unit)
            response = response[(len(command)+1):]
            value = float(response)
            return value
        except ValueError as e:
            print(f"Failed to convert response to float: {e}")
            return None


    def get_IDN(self):
        response = self.query('*IDN?')
        self.IDN = response[len('IDN:'):].strip()
        return self.IDN

    ############### Commands about temperatures ###############

    def get_UID_temperature(self, UID):
        return self._read_value(f"READ:DEV:{UID}:TEMP:SIG:TEMP", "K")
    

    def get_probe_temperature(self):
        T = self.get_UID_temperature('DB8.T1')
        return T
    

    def get_VTI_temperature(self):
        T = self.get_UID_temperature('MB1.T1')
        return T


    def set_VTI_temperature(self, Tvti):
        if (Tvti < 0) or (Tvti > 2000):
            raise ValueError("VTI temperature must be 0-2000")
        else:
            self._write_check(f"SET:DEV:MB1.T1:TEMP:LOOP:FSET:{Tvti:.4f}")
    

    def set_probe_temperature(self, Tprobe):
        if (Tprobe < 0) or (Tprobe > 2000):
            raise ValueError("Probe temperature must be 0-2000")
        else:
            self._write_check(f"SET:DEV:DB8.T1:TEMP:LOOP:FSET:{Tprobe:.4f}")

    
    def get_VTI_temperature_set(self):
        return self._read_value("READ:DEV:MB1.T1:TEMP:LOOP:TSET", "K")
    

    def get_probe_temperature_set(self):
        return self._read_value("READ:DEV:DB8.T1:TEMP:LOOP:TSET", "K")
    

    def set_VTI_temperature_loop(self, state):
        if state.upper() not in ['ON','OFF']:
            raise ValueError("State must be 'ON' or 'OFF'")
        self._write_check(f"SET:DEV:MB1.T1:TEMP:LOOP:ENAB:{state.upper()}")
    

    def set_probe_temperature_loop(self, state):
        if state.upper() not in ['ON','OFF']:
            raise ValueError("State must be 'ON' or 'OFF'")
        self._write_check(f"SET:DEV:DB8.T1:TEMP:LOOP:ENAB:{state.upper()}")
    

    def get_VTI_temperature_loop(self):
        response = self.query("READ:DEV:MB1.T1:TEMP:LOOP:ENAB")
        response = response.strip()
        response = response[len("STAT:DEV:MB1.T1:TEMP:LOOP:ENAB:"):]
        return response
    

    def get_probe_temperature_loop(self):
        response = self.query("READ:DEV:DB8.T1:TEMP:LOOP:ENAB")
        response = response.strip()
        response = response[len("STAT:DEV:DB8.T1:TEMP:LOOP:ENAB:"):]
        return response


    def get_VTI_heater(self):
        return self._read_value("READ:DEV:MB1.T1:TEMP:LOOP:HSET")
    

    def get_probe_heater(self):
        return self._read_value("READ:DEV:DB8.T1:TEMP:LOOP:HSET")


    ############### Commands about pressures ###############


    def get_pressure(self):
        return self._read_value("READ:DEV:DB5.P1:PRES:SIG:PRES", "mB")
    

    def get_NV_flow(self):
        return self._read_value("READ:DEV:DB5.P1:PRES:LOOP:FSET", "mB")
    

    def get_NV_flow_control(self):
        command = "READ:DEV:DB5.P1:PRES:LOOP:FAUT"
        response = self.query(command)
        response = response.strip()
        response = response[len("STAT:DEV:DB5.P1:PRES:LOOP:FAUT:"):]
        return response


    def set_NV_flow_control(self, state):
        if state.upper() not in ['ON','OFF']:
            raise ValueError("State must be 'ON' or 'OFF'")
        self._write_check(f"SET:DEV:DB5.P1:PRES:LOOP:FAUT:{state.upper()}")
    

    def set_NV_flow(self, flow):
        if (flow > 100) or (flow < 0):
            raise ValueError("Flow must be 0-100")
        else:
            self._write_check(f"SET:DEV:DB5.P1:PRES:LOOP:FSET:{flow:.4f}")
    

    def set_pressure(self, pres):
        if (pres < 0) or (pres > 30):
            raise ValueError("Pressure must be 0-30 mBar")
        else:
            self._write_check(f"SET:DEV:DB5.P1:PRES:LOOP:PRST:{pres:.4f}")
    

    def get_pressure_set(self):
        return self._read_value("READ:DEV:DB5.P1:PRES:LOOP:PRST", "mB")



class IPS(MercuryIPS):
    
    def __init__(self, resource_name):
        super().__init__(resource_name)
    

    def get_magnet_temperature(self):
        return self._read_value('READ:DEV:MB1.T1:TEMP:SIG:TEMP','K')



class MotorController(EIns):
    
    def __init__(self, resource_name) -> None:
        super().__init__(resource_name)
    

    def connect(self) -> None:
        super().connect()
        self.device.write_termination = '\r\n'
        self.device.read_termination = '\r\n'
        self.device.baud_rate = 115200
    

    @staticmethod
    def deg2code(deg:float) -> int:
        return math.ceil((deg % 360) * 54050 / 360)


    @staticmethod
    def code2deg(code:int) -> float:
        return float(code) * 360 / 54050


    def to_zero(self) -> None:
        self.write('[z,1,1501]')
    
    
    def to_deg(self, target:float, speed:float=5) -> None:
        speed_code = RotController.deg2code(speed)
        target_code = RotController.deg2code(target)
        self.write(f'[r,0,{speed_code:04d},{target_code:06d}]')
    
    
    def get_deg(self) -> float:
        return RotController.code2deg(self._get_deg_code())
    

    def _get_deg_code(self) -> int:
        self.write('[?]')
        resp = self.device.read_bytes(12)
        resp = resp.decode('utf-8')
        return int(resp[5:-1])
    
    
    def drive_to_deg(self, target:float, speed:float=5) -> None:
        speed_code = RotController.deg2code(speed)
        target_code = RotController.deg2code(target)

        current_deg_code = self._get_deg_code()
        t = abs(target_code - current_deg_code) / speed_code
        
        self.write(f'[r,0,{speed_code:04d},{target_code:06d}]')
        time.sleep(t)
        
        for _ in range(10):
            if target_code == self._get_deg_code():
                break
            time.sleep(0.2)
        else:
            raise TimeoutError(f'Motor is NOT at the target position. Now position {self._get_deg_code()} deg.')