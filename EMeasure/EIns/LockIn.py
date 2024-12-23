from .EIns import EIns
import asyncio

class NF5650(EIns):
    def __init__(self, resource_name):
        super().__init__(resource_name)
        
    
    async def set_sense_data(self, *data):
        data_mapping = {'data1': 2, 'data2': 4, 'data3': 6, 'data4': 8}
        selected_data = sum(data_mapping[d.lower()] for d in data if d.lower() in data_mapping)
        if selected_data == 0:
            raise ValueError("At least one of data1, data2, data3, data4 must be specified")
        command = f'SENS:DATA {selected_data}'
        await self.write(command)


    async def fetch_data(self):
        command = 'FETCH?'
        response = await self.query(command)
        data = response.strip().split(',')
        try:
            measured_data = [float(d) for d in data]
            return measured_data
        except ValueError as e:
            print(f"Failed to parse measurement data: {e}")
            return None