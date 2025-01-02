import asyncio
import pyvisa
from .EIns import EIns


class MercuryIPS(EIns):
    def __init__(self, resource_name):
        super().__init__(resource_name)
    

    async def connect(self):
        await super().connect()
        self.device.set_visa_attribute(pyvisa.constants.VI_ATTR_TERMCHAR, 0xa)
        self.device.set_visa_attribute(pyvisa.constants.VI_ATTR_TERMCHAR_EN, 0x1)
    

    async def disconnect(self):
        return await super().disconnect()
    

    async def _write_check(self, command):
        response = await self.query(command)
        response = response.strip()
        flag = response[len(f"STAT:{command}:"):]
        if flag != 'VALID':
            raise ValueError(f"Failed to execute command: {command}")
    

    async def _read_value(self, command, unit=''):
        response = await self.query(command)
        response = response.strip()
        try:
            response = response.rstrip(unit)
            response = response[(len(command)+1):]
            value = float(response)
            return value
        except ValueError as e:
            print(f"Failed to convert response to float: {e}")
            return None


    async def get_IDN(self):
        response = await self.query('*IDN?')
        self.IDN = response[len('IDN:'):].strip()
        return self.IDN
    

    async def get_field(self, dir):
        return await self._read_value(f'READ:DEV:GRP{dir.upper()}:PSU:SIG:PFLD','T')
    

    async def set_target_field(self, B, dir):
        await self._write_check(f'SET:DEV:GRP{dir.upper()}:PSU:SIG:FSET:{B:.4f}')
    

    async def set_ramp_rate(self, rate, dir):
        await self._write_check(f'SET:DEV:GRP{dir.upper()}:PSU:SIG:RFST:{rate:.4f}')
    

    async def set_action_hold(self, dir):
        await self._write_check(f'SET:DEV:GRP{dir.upper()}:PSU:ACTN:HOLD')
    

    async def set_action_rtos(self, dir):
        await self._write_check(f'SET:DEV:GRP{dir.upper()}:PSU:ACTN:RTOS')
    

    async def set_action_rtoz(self, dir):
        await self._write_check(f'SET:DEV:GRP{dir.upper()}:PSU:ACTN:RTOZ')
    

    async def get_action(self, dir):
        command = f'READ:DEV:GRP{dir.upper()}:PSU:ACTN'
        response = await self.query(command)
        response = response.strip()
        action = response[(len(command)+1):]
        return action