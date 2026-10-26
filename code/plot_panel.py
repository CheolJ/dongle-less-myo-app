"""Construct and refresh raw EMG/IMU charts with bounded buffers."""
import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QLabel, QHBoxLayout

class PlotPanelMixin:
    def build_plots(self, plot_column):
        pg.setConfigOptions(antialias=False, background='w', foreground='k')
        self.emg_plot = pg.GraphicsLayoutWidget()
        self.emg_plot.setMinimumHeight(440)
        self.emg_curves = []
        palette = ['#3274a1','#ad6538','#39966d','#9860a8','#b14e5d','#5f8d2d','#876f4c','#555b9d']
        for i in range(8):
            plot = self.emg_plot.addPlot(row=i, col=0)
            plot.setMenuEnabled(False)
            plot.setMouseEnabled(x=False, y=False)
            plot.setYRange(-130, 130, padding=0)
            plot.setLabel('left', f'CH{i+1}')
            plot.showGrid(x=True, y=True, alpha=0.13)
            if i < 7:
                plot.hideAxis('bottom')
            else:
                plot.setLabel('bottom', 'Recent samples (200 Hz nominal)')
            self.emg_curves.append(plot.plot(pen=pg.mkPen(palette[i], width=1)))
        plot_column.addWidget(QLabel('EMG — signed int8 (raw), eight channels'))
        plot_column.addWidget(self.emg_plot, stretch=2)

        imu_row = QHBoxLayout()
        self.imu_plots = []
        self.imu_curves = []
        for title, ylabel in [('Accelerometer (g)','g'),('Gyroscope (deg/s)','deg/s')]:
            plot = pg.PlotWidget(title=title)
            plot.showGrid(x=True, y=True, alpha=.2)
            plot.setLabel('left', ylabel)
            plot.setLabel('bottom', 'Recent samples (50 Hz nominal)')
            plot.addLegend(offset=(5, 5))
            curves = [plot.plot(pen=pg.mkPen(c, width=1.5), name=n)
                      for c,n in zip(['#c45850','#4b9673','#627fc3'], ['X','Y','Z'])]
            self.imu_curves.append(curves)
            self.imu_plots.append(plot)
            imu_row.addWidget(plot)
        plot_column.addLayout(imu_row, stretch=1)

    def refresh_plots(self):
        if self.emg_buffer:
            data = np.asarray(self.emg_buffer, dtype=np.int16)
            x = (np.arange(len(data)) - len(data) + 1) / 200
            for i, curve in enumerate(self.emg_curves):
                curve.setData(x, data[:, i])
        for buffer, curves in ((self.accel_buffer,self.imu_curves[0]),
                                (self.gyro_buffer,self.imu_curves[1])):
            if buffer:
                data = np.asarray(buffer, dtype=float)
                x = (np.arange(len(data)) - len(data) + 1) / 50
                for i, curve in enumerate(curves):
                    curve.setData(x, data[:, i])
