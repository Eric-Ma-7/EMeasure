import asyncio
import pyvisa
from .EIns import EIns

class ITC(EIns):

    def __init__(self, resource_name):
        super().__init__(resource_name)
    

    async def connect(self):
        await super().connect()
        self.device.set_visa_attribute(pyvisa.constants.VI_ATTR_TERMCHAR, 0xa)
        self.device.set_visa_attribute(pyvisa.constants.VI_ATTR_TERMCHAR_EN, 0x1)
    

    async def disconnect(self):
        return await super().disconnect()
    

    async def get_IDN(self):
        response = await self.query('*IDN?')
        self.IDN = response[len('IDN:'):].strip()
        return self.IDN


    async def get_UID_temperature(self, UID):
        command = f"READ:DEV:{UID}:TEMP:SIG:TEMP"
        response = await self.query(command)
        response = response.strip()
        try:
            response = response.rstrip('K')
            response = response[len(f"STAT:DEV:{UID}:TEMP:SIG:TEMP:"):]
            value = float(response)
            return value
        except ValueError as e:
            print(f"Failed to convert response to float: {e}")
            return None
    

    async def get_probe_temperature(self):
        T = await self.get_UID_temperature('DB8.T1')
        return T
    

    async def get_VTI_temperature(self):
        T = await self.get_UID_temperature('MB1.T1')
        return T
    

    async def get_pressure(self):
        command = "READ:DEV:DB5.P1:PRES:SIG:PRES"
        response = await self.query(command)
        response = response.strip()
        try:
            response = response.rstrip('mB')
            response = response[len("STAT:DEV:DB5.P1:PRES:SIG:PRES:"):]
            value = float(response)
            return value
        except ValueError as e:
            print(f"Failed to convert response to float: {e}")
            return None
    

    async def get_DB4NV_flow(self):
        command = "READ:DEV:DB5.P1:PRES:LOOP:FSET"
        response = await self.query(command)
        response = response.strip()
        try:
            response = response[len("STAT:DEV:DB5.P1:PRES:LOOP:FSET:"):]
            value = float(response)
            return value
        except ValueError as e:
            print(f"Failed to convert response to float: {e}")
            return None
    

    async def get_DB4NV_flow_control(self):
        command = "READ:DEV:DB5.P1:PRES:LOOP:FAUT"
        response = await self.query(command)
        response = response.strip()
        response = response[len("STAT:DEV:DB5.P1:PRES:LOOP:FAUT:"):]
        return response