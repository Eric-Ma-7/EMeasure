from ..instrument import TeslatronPT
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QMainWindow
from ..UI.Ui_TeslatronPTApp import Ui_TeslatronPTApp

class TeslatronPTApp(QMainWindow, Ui_TeslatronPTApp):
    _TEMP_KEY = ['probe_temp', 'pressure', 'NV_flow', 'VTI_temp', 'magnet_temp', 'PT2_temp', 'PT1_temp']
    _FIELD_KEY = ['Bz', 'iPS_action', 'iPS_heater_ON']
    
    def __init__(
        self, 
        fridge: TeslatronPT,
        *,
        daq_interval:int = 1000
    ):
        super().__init__()
        self.setupUi(self)
        self.setWindowTitle("TeslatronPT 1.5K System Monitor")
        self.resize(470, 800)

        # ---------- initialization ----------
        self.fridge = fridge
        self.fridge.connect()
        self.treeWidget.topLevelItem(0).setExpanded(True)
        self.treeWidget.topLevelItem(1).setExpanded(True)

        self.update_timer = QTimer()
        self.update_timer.start(daq_interval)
        self.update_timer.timeout.connect(self.update_all)

        self.doubleSpinBox_target_field.valueChanged.connect(
            lambda: self.fridge.ips.set_target_field(self.doubleSpinBox_target_field.value())
        )
        self.doubleSpinBox_ramp_rate.valueChanged.connect(
            lambda: self.fridge.ips.set_ramp_rate(self.doubleSpinBox_ramp_rate.value())
        )
        self.pushButton_hold.clicked.connect(lambda: self.fridge.ips.set_action('HOLD'))
        self.pushButton_rtos.clicked.connect(lambda: self.fridge.ips.set_action('RTOS'))
        self.pushButton_rtoz.clicked.connect(lambda: self.fridge.ips.set_action('RTOZ'))
    
    def update_all(self):
        temp = self.fridge.temp_snapshot()
        field = self.fridge.field_snapshot()

        temp_text = [
            '{:.4f}'.format(temp['probe_temp']),
            '{:.4f}'.format(temp['pressure']),
            '{:.4f}'.format(temp['NV_flow']),
            '{:.4f}'.format(temp['VTI_temp']),
            '{:.4f}'.format(temp['magnet_temp']),
            '{:.4f}'.format(temp['PT2_temp']),
            '{:.4f}'.format(temp['PT1_temp']),
        ]

        field_text = [
            '{:.4f}'.format(field['Bz']),
            '{}'.format(field['iPS_action']),
            'ON' if field['iPS_heater_ON'] else 'OFF'
        ]

        for ind, text in enumerate(temp_text):
            self.treeWidget.topLevelItem(0).child(ind).setText(1, text)
        
        for ind, text in enumerate(field_text):
            self.treeWidget.topLevelItem(1).child(ind).setText(1, text)

        self.label_probe.setText(f'{temp_text[0]} K')
        self.label_magnet.setText(f'{temp_text[4]} K')
        self.label_field.setText(f'{field_text[0]} T')
        self.label_action.setText(field_text[1])
    
    