import asyncio
import pyvisa
from .EIns import EIns
from .IPS import MercuryIPS

class ITC(EIns):

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

    ############### Commands about temperatures ###############

    async def get_UID_temperature(self, UID):
        return await self._read_value(f"READ:DEV:{UID}:TEMP:SIG:TEMP", "K")
    

    async def get_probe_temperature(self):
        T = await self.get_UID_temperature('DB8.T1')
        return T
    

    async def get_VTI_temperature(self):
        T = await self.get_UID_temperature('MB1.T1')
        return T


    async def set_VTI_temperature(self, Tvti):
        if (Tvti < 0) or (Tvti > 2000):
            raise ValueError("VTI temperature must be 0-2000")
        else:
            await self._write_check(f"SET:DEV:MB1.T1:TEMP:LOOP:FSET:{Tvti:.4f}")
    

    async def set_probe_temperature(self, Tprobe):
        if (Tprobe < 0) or (Tprobe > 2000):
            raise ValueError("Probe temperature must be 0-2000")
        else:
            await self._write_check(f"SET:DEV:DB8.T1:TEMP:LOOP:FSET:{Tprobe:.4f}")

    
    async def get_VTI_temperature_set(self):
        return await self._read_value("READ:DEV:MB1.T1:TEMP:LOOP:TSET", "K")
    

    async def get_probe_temperature_set(self):
        return await self._read_value("READ:DEV:DB8.T1:TEMP:LOOP:TSET", "K")
    

    async def set_VTI_temperature_loop(self, state):
        if state.upper() not in ['ON','OFF']:
            raise ValueError("State must be 'ON' or 'OFF'")
        await self._write_check(f"SET:DEV:MB1.T1:TEMP:LOOP:ENAB:{state.upper()}")
    

    async def set_probe_temperature_loop(self, state):
        if state.upper() not in ['ON','OFF']:
            raise ValueError("State must be 'ON' or 'OFF'")
        await self._write_check(f"SET:DEV:DB8.T1:TEMP:LOOP:ENAB:{state.upper()}")
    

    async def get_VTI_temperature_loop(self):
        response = await self.query("READ:DEV:MB1.T1:TEMP:LOOP:ENAB")
        response = response.strip()
        response = response[len("STAT:DEV:MB1.T1:TEMP:LOOP:ENAB:"):]
        return response
    

    async def get_probe_temperature_loop(self):
        response = await self.query("READ:DEV:DB8.T1:TEMP:LOOP:ENAB")
        response = response.strip()
        response = response[len("STAT:DEV:DB8.T1:TEMP:LOOP:ENAB:"):]
        return response


    async def get_VTI_heater(self):
        return await self._read_value("READ:DEV:MB1.T1:TEMP:LOOP:HSET")
    

    async def get_probe_heater(self):
        return await self._read_value("READ:DEV:DB8.T1:TEMP:LOOP:HSET")


    ############### Commands about pressures ###############


    async def get_pressure(self):
        return await self._read_value("READ:DEV:DB5.P1:PRES:SIG:PRES", "mB")
    

    async def get_NV_flow(self):
        return await self._read_value("READ:DEV:DB5.P1:PRES:LOOP:FSET", "mB")
    

    async def get_NV_flow_control(self):
        command = "READ:DEV:DB5.P1:PRES:LOOP:FAUT"
        response = await self.query(command)
        response = response.strip()
        response = response[len("STAT:DEV:DB5.P1:PRES:LOOP:FAUT:"):]
        return response


    async def set_NV_flow_control(self, state):
        if state.upper() not in ['ON','OFF']:
            raise ValueError("State must be 'ON' or 'OFF'")
        await self._write_check(f"SET:DEV:DB5.P1:PRES:LOOP:FAUT:{state.upper()}")
    

    async def set_NV_flow(self, flow):
        if (flow > 100) or (flow < 0):
            raise ValueError("Flow must be 0-100")
        else:
            await self._write_check(f"SET:DEV:DB5.P1:PRES:LOOP:FSET:{flow:.4f}")
    

    async def set_pressure(self, pres):
        if (pres < 0) or (pres > 30):
            raise ValueError("Pressure must be 0-30 mBar")
        else:
            await self._write_check(f"SET:DEV:DB5.P1:PRES:LOOP:PRST:{pres:.4f}")
    

    async def get_pressure_set(self):
        return await self._read_value("READ:DEV:DB5.P1:PRES:LOOP:PRST", "mB")



class IPS(MercuryIPS):
    
    def __init__(self, resource_name):
        super().__init__(resource_name)
    

    async def get_magnet_temperature(self):
        return await self._read_value('READ:DEV:MB1.T1:TEMP:SIG:TEMP','K')