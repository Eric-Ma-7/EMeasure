import asyncio
import pyvisa
from .EIns import EIns

class DSO9104A(EIns):

    def __init__(self, resource_name):
        super().__init__(resource_name)
    

    async def get_xy_info(self, channel):
        await self.write(f':waveform:source channel{channel}')
        xy_info = {
            'xOrg': await self.query(':waveform:xorigin?'),
            'xInc': await self.query(':waveform:xincrement?'),
            'yOrg': await self.query(':waveform:yorigin?'),
            'yInc': await self.query(':waveform:yincrement?'),
        }
        try:
            xy_info = {key: float(val) for key,val in xy_info.items()}
            return xy_info
        except ValueError as e:
            print(f"Failed to convert response to float: {e}")
            return None


    async def get_waveform(self, channel):
        xy_info = await self.get_xy_info(channel=channel)

        await self.write(':digitize')
        await self.write(':system:header off')
        await self.write(':waveform:byteorder LSBfirst')
        await self.write(':waveform:format ascii')
        await self.write(':waveform:streaming off')

        await self.write(f':waveform:source channel{channel}')
        resp = await self.query(':waveform:data?')
        resp = resp.strip().rstrip(',')
        try:
            y_data = [xy_info['yOrg'] + float(s) * xy_info['yInc'] for s in resp.split(',')]
        except ValueError as e:
            print(f"Failed to convert response to float: {e}")
            y_data = None

        await self.write(':waveform:streaming on')
        await self.write(':run')

        return y_data
    

    async def set_y_offset(self, offset, channel):
        await self.write(f':channel{channel}:offset {offset}')
    

    async def set_y_scale(self, scale, channel):
        await self.write(f':channel{channel}:scale {scale}')
    

    async def set_x_range(self, xrange):
        # xrange is a real number for the horizontal time, in seconds.
        # xrange in [50ps, 200s]
        await self.write(f':timebase:range {xrange}')
    

    async def set_sample_rate(self, fs):
        # fs = AUTO | MAX | <rate>
        await self.write(f':acquire:srate {fs}')