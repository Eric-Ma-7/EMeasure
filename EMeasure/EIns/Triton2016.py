import asyncio
import pyvisa
import pyvisa.constants
from .EIns import EIns

class Triton2016(EIns):

    def __init__(self, resource_name):
        super().__init__(resource_name)
    

    async def connect(self):
        try:
            self.device = self.rm.open_resource(self.resource_name)
            self.device.set_visa_attribute(pyvisa.constants.VI_ATTR_TERMCHAR, 0xa)
            self.device.set_visa_attribute(pyvisa.constants.VI_ATTR_TERMCHAR_EN, 0x1)
            print(f"Connected to {self.resource_name}")
        except Exception as e:
            print(f"Failed to connect to {self.resource_name}: {e}")
    

    async def disconnect(self):
        await super().disconnect()

    
    async def get_temperature(self, channel:int):
        command = f"READ:DEV:T{channel}:TEMP:SIG:TEMP"
        response = await self.query(command)
        try:
            temperature = response.strip()
            temperature = temperature[len(f"STAT:DEV:T{channel}:TEMP:SIG:TEMP:"):-1]
            return float(temperature)
        except ValueError as e:
            print(f"Failed to convert response to float: {e}")
            return None
    

    async def get_MCRuO2_temperature(self):
        return await self.get_temperature(channel=8)
    

    async def get_Magnet_temperature(self):
        return await self.get_temperature(channel=13)