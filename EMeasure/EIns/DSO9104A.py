from .EIns import EIns
import numpy as np


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
        if isinstance(channel, list):
            for ch in channel:
                self.write(f':channel{ch}:offset {offset}')
        else:
            self.write(f':channel{channel}:offset {offset}')
    

    def set_y_scale(self, scale, channel):
        if isinstance(channel, list):
            for ch in channel:
                self.write(f':channel{ch}:scale {scale}')
        else:
            self.write(f':channel{channel}:scale {scale}')
    

    def set_x_range(self, xrange):
        # xrange is a real number for the horizontal time, in seconds.
        # xrange in [50ps, 200s]
        self.write(f':timebase:range {xrange}')
    

    def set_sample_rate(self, fs):
        # fs = AUTO | MAX | <rate>
        self.write(f':acquire:srate {fs}')
    

    def get_sample_rate(self):
        resp = self.query(':acquire:srate?').strip()
        try:
            return float(resp)
        except ValueError as e:
            print(f"Failed to convert response to float: {e}")
            return None
    

    def get_x_range(self):
        resp = self.query(':timebase:range?').strip()
        try:
            return float(resp)
        except ValueError as e:
            print(f"Failed to convert response to float: {e}")
            return None
    

    def get_y_scale(self, channel):
        resp = self.query(f':channel{channel}:scale?').strip()
        try:
            return float(resp)
        except ValueError as e:
            print(f"Failed to convert response to float: {e}")
            return None
    

    def get_y_offset(self, channel):
        resp = self.query(f':channel{channel}:offset?').strip()
        try:
            return float(resp)
        except ValueError as e:
            print(f"Failed to convert response to float: {e}")
            return None


    def auto_set_y(self, channel, xrange=10e-3, Fs=1e6, ptp2div=2, y0=0, yscale0=1, N=2, yscalemin=20e-3):
        '''
        auto tuning the y offset & range
        Parameter:
            channel: channel number or list of channel number
            xrange: x range when tuning
            Fs: Fs when tuing

            ptp2div: parameter to determin the peak-to-peak value in DIV
            y0: the initial value for y offset
            yscale0: the initial value for y div
            N: iterate for N times
        '''

        channel = channel if isinstance(channel,list) else [channel]

        xrange_set = self.get_x_range()
        Fs_set = self.get_sample_rate()

        self.set_x_range(xrange)
        self.set_sample_rate(Fs)

        for ch in channel:
            self.set_y_offset(y0, channel=ch)
            self.set_y_scale(yscale0, channel=ch)
        
        for _ in range(N):
            wvf = self.get_waveform(channel)
            for ch,w in zip(channel,wvf):
                yscale = np.ptp(w) / ptp2div
                yscale = yscale if yscale > yscalemin else yscalemin

                self.set_y_offset(np.min(w) + 0.5*np.ptp(w), channel=ch)
                self.set_y_scale(yscale, channel=ch)
        
        self.set_x_range(xrange_set)
        self.set_sample_rate(Fs_set)