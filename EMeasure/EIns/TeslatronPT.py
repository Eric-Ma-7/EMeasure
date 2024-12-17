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
    

    async def get_probe_temperature(self):
        command = "READ:DEV:DB8.T1:TEMP:SIG:TEMP"
        response = await self.query(command)
        response = response.strip()
        try:
            response = response.rstrip('K')
            response = response[len('STAT:DEV:DB8.T1:TEMP:SIG:TEMP:'):]
            value = float(response)
            return value
        except ValueError as e:
            print(f"Failed to convert response to float: {e}")
            return None