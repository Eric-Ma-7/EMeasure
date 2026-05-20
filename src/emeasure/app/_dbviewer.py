import sys
import os
import sqlite3
import pandas as pd

from contextlib import closing
from pathlib import Path

# from PyQt5 import QtWidgets, QtCore
# from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QGridLayout
# from PyQt5.QtGui import QFont

from PySide6 import QtWidgets, QtCore
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QGridLayout
from PySide6.QtGui import QFont

import pyqtgraph as pg

def read_sql(db_path: str, vars:list[str]):
    if not Path(db_path).exists():
        raise FileNotFoundError(f"{db_path} NOT found.")
    
    vstr = ", ".join(vars)
    with closing(sqlite3.connect(db_path)) as conn:
        info = pd.read_sql_query("SELECT * from experiments", conn, index_col='id')
        table_name = info['table_name'].iloc[-1]
        df = pd.read_sql_query(f"SELECT {vstr} from {table_name}", conn)
    return df


class LinePlotWindow(QMainWindow):
    def __init__(
            self, db_path: str, rcxy: list[tuple[int,int,str,str]],
            *,
            refresh_time = 200
    ):
        super().__init__()

        # Connect to database
        self.db_path = db_path
        self.rcxy = rcxy.copy()
        x_all = [xi for _, _, xi,  _ in self.rcxy]
        y_all = [yi for _, _,  _, yi in self.rcxy]
        self.vars = list(set(x_all + y_all))

        # Basic window setup
        self.setWindowTitle("Real-Time Plot")
        self.resize(800, 800)
        self.status = self.statusBar()

        # Create plot widgets
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        gridLayout = QGridLayout(central_widget)

        self.plots = []
        self.curves = []
        for ri, ci, xi, yi in self.rcxy:
            pw = pg.PlotWidget(title=f"{xi} ~ {yi}")
            pw.getViewBox().setMouseMode(pg.ViewBox.RectMode)
            pw.showGrid(x=True, y=True)
            pw.setLabel("bottom", xi)
            pw.setLabel("left", yi)

            curv = pw.plot([], [], pen='y', symbol='o', symbolBrush='y')
            gridLayout.addWidget(pw, ri, ci)
            self.plots.append(pw)
            self.curves.append(curv)

        # Timer for refreshing data
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(refresh_time)

    def update_plot(self):
        try:
            df = read_sql(self.db_path, self.vars)
        except Exception as e:
            df = None
            self.status.showMessage(str(e))

        if df is not None:
            for curv, (_, _, xi, yi) in zip(self.curves, self.rcxy):
                try:
                    curv.setData(
                        x=df[xi].to_numpy(dtype=float),
                        y=df[yi].to_numpy(dtype=float)
                    )
                    self.status.showMessage("")
                except Exception as e:
                    self.status.showMessage(str(e))

