import asyncio
import pyvisa

class EIns:
    def __init__(self, resource_name):
        self.resource_name = resource_name
        self.rm = pyvisa.ResourceManager()
        self.device = None
        self.IDN = None
        self._lock = asyncio.Lock()
    

    async def connect(self):
        async with self._lock:
            try:
                self.device = await asyncio.to_thread(self.rm.open_resource, self.resource_name)
                # self.device = self.rm.open_resource(self.resource_name)
                print(f"Connected to {self.resource_name}")
            except Exception as e:
                print(f"Failed to connect to {self.resource_name}: {e}")
    

    async def disconnect(self):
        async with self._lock:
            if self.device:
                await asyncio.to_thread(self.device.close)
                # self.device.close()
                print(f"Disconnected from {self.resource_name}")
    

    async def write(self, command):
        async with self._lock:
            if self.device:
                try:
                    await asyncio.to_thread(self.device.write, command)
                    # print(f"Command '{command}' sent to {self.resource_name}")
                except Exception as e:
                    print(f"Failed to send command '{command}' to {self.resource_name}: {e}")
    

    async def read(self):
        async with self._lock:
            if self.device:
                try:
                    response = await asyncio.to_thread(self.device.read)
                    # print(f"Response from {self.resource_name}: {response.strip()}")
                    return response
                except Exception as e:
                    print(f"Failed to read response from {self.read}: {e}")
                    return None
    

    async def query(self, command):
        async with self._lock:
            if self.device:
                try:
                    response = await asyncio.to_thread(self.device.query, command)
                    # print(f"Query '{command}' sent to {self.resource_name}, response: {response.strip()}")
                    return response
                except Exception as e:
                    print(f"Failed to query '{command}' from {self.resource_name}: {e}")
                    return None
    

    async def sleep(self, t):
        async with self._lock:
            await asyncio.sleep(t)


    async def get_IDN(self):
        self.IDN = await self.query('*IDN?')
        return self.IDN