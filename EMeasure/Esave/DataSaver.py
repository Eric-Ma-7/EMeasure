import queue
import pandas as pd
import os
import datetime

class DataSaver1D():

    def __init__(self, columns, filename=''):
        self._buffer = queue.Queue()
        self._data = pd.DataFrame(data=None, columns=columns)
        self._Ncol = len(columns)
        self._file = filename + datetime.datetime.now().strftime("_%Y%m%d%H%M%S.csv")
    

    def __len__(self):
        return len(self._data)
    

    def __getitem__(self, key):
        return self._data[key].to_numpy()


    def put(self, dataframe, **kwargs):
        if len(dataframe) != self._Ncol:
            raise ValueError(f'Length of dataframe {len(dataframe)} dose NOT match with the number of columns {self._Ncol}')
        else:
            self._buffer.put({
                'dataframe': dataframe,
                **kwargs
            })
    

    def get_one_from_buffer(self, save=True):
        if not self._buffer.empty():
            frame = self._buffer.get()
            self._data.loc[len(self)] = frame.pop('dataframe')
            if save:
                self._data.to_csv(self._file, index=False)
            return frame
        else:
            return None


    def get_all_from_buffer(self, save=True):
        while not self._buffer.empty():
            frame = self._buffer.get()
            self._data.loc[len(self)] = frame.pop('dataframe')
        if save:
            self._data.to_csv(self._file, index=False)
    

    def is_buffer_empty(self):
        return self._buffer.empty()