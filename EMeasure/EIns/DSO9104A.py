from .EIns import EIns

class DSO9104A(EIns):

    def __init__(self, resource_name):
        super().__init__(resource_name)
    

    def get_xy_info(self, channel):
        self.write(f':waveform:source channel{channel}')
        xy_info = {
            'xOrg': self.query(':waveform:xorigin?'),
            'xInc': self.query(':waveform:xincrement?'),
            'yOrg': self.query(':waveform:yorigin?'),
            'yInc': self.query(':waveform:yincrement?'),
        }
        try:
            xy_info = {key: float(val) for key,val in xy_info.items()}
            return xy_info
        except ValueError as e:
            print(f"Failed to convert response to float: {e}")
            return None


    def get_waveform(self, channel):
        self.write(':digitize')
        self.write(':system:header off')
        self.write(':waveform:byteorder LSBfirst')
        self.write(':waveform:format ascii')
        self.write(':waveform:streaming off')

        channel = channel if isinstance(channel,list) else [channel]
        y_datas = []
        for ch in channel:
            self.write(f':waveform:source channel{ch}')
            resp = self.query(':waveform:data?')
            resp = resp.strip().rstrip(',')
            try:
                y_data = [float(s) for s in resp.split(',')]
            except ValueError as e:
                print(f"Failed to convert response to float: {e}")
                y_data = None
            y_datas.append(y_data)

        self.write(':waveform:streaming on')
        self.write(':run')

        return y_datas
    

    def set_y_offset(self, offset, channel):
        self.write(f':channel{channel}:offset {offset}')
    

    def set_y_scale(self, scale, channel):
        self.write(f':channel{channel}:scale {scale}')
    

    def set_x_range(self, xrange):
        # xrange is a real number for the horizontal time, in seconds.
        # xrange in [50ps, 200s]
        self.write(f':timebase:range {xrange}')
    

    def set_sample_rate(self, fs):
        # fs = AUTO | MAX | <rate>
        self.write(f':acquire:srate {fs}')