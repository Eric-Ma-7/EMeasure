import pyvisa
from .EIns import EIns


class MercuryIPS(EIns):
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
    

    def get_field(self, dir):
        return self._read_value(f'READ:DEV:GRP{dir.upper()}:PSU:SIG:PFLD','T')
    

    def set_target_field(self, B, dir):
        self._write_check(f'SET:DEV:GRP{dir.upper()}:PSU:SIG:FSET:{B:.4f}')
    

    def set_ramp_rate(self, rate, dir):
        self._write_check(f'SET:DEV:GRP{dir.upper()}:PSU:SIG:RFST:{rate:.4f}')
    

    def set_action_hold(self, dir):
        self._write_check(f'SET:DEV:GRP{dir.upper()}:PSU:ACTN:HOLD')
    

    def set_action_rtos(self, dir):
        self._write_check(f'SET:DEV:GRP{dir.upper()}:PSU:ACTN:RTOS')
    

    def set_action_rtoz(self, dir):
        self._write_check(f'SET:DEV:GRP{dir.upper()}:PSU:ACTN:RTOZ')
    

    def get_action(self, dir):
        command = f'READ:DEV:GRP{dir.upper()}:PSU:ACTN'
        response = self.query(command)
        response = response.strip()
        action = response[(len(command)+1):]
        return action