"""Compose acquisition, visualization, protocol controls, and recording."""
import sys
import time
from collections import deque
from pathlib import Path
import numpy as np
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QPushButton, QVBoxLayout, QWidget)
from myo_ble import MyoWorker
from data_logger import DataLogger
from protocol_manager import ProtocolManager
from protocol_panel import ProtocolPanelMixin
from plot_panel import PlotPanelMixin

class MainWindow(ProtocolPanelMixin, PlotPanelMixin, QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Myo Monitor v3 — 8ch EMG + 6-axis IMU')
        self.resize(1260, 980)
        self.worker = None
        self.devices = []
        self.running = False
        self.logging = False
        self.stream_ready = False
        self.logger = DataLogger()
        self.protocol_manager = ProtocolManager()
        self.emg_samples = 0
        self.imu_samples = 0
        self.packet_count = 0
        self.emg_buffer = deque(maxlen=1000)  # Five seconds at the nominal 200 Hz rate.
        self.accel_buffer = deque(maxlen=250)
        self.gyro_buffer = deque(maxlen=250)
        self.sample_dir = Path.cwd()
        self.protocol_steps = []
        self.imported_protocol_path = None
        self.protocol_active = False
        self.protocol_index = -1
        self.protocol_started_ns = 0
        self.step_deadline_ns = 0
        self.total_duration_ns = 1


        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        top = QHBoxLayout()
        self.scan_btn = QPushButton('Scan Myo')
        self.scan_btn.clicked.connect(self.scan)
        self.devices_combo = QComboBox()
        self.devices_combo.setMinimumWidth(250)
        self.connect_btn = QPushButton('Connect')
        self.connect_btn.clicked.connect(self.toggle_connect)
        self.save_btn = QPushButton('Start Recording')
        self.save_btn.clicked.connect(self.toggle_recording)
        self.save_btn.setEnabled(False)
        self.dir_btn = QPushButton('Output Folder')
        self.dir_btn.clicked.connect(self.choose_folder)
        self.folder_label = QLabel(str(self.sample_dir))
        self.folder_label.setMaximumWidth(250)
        top.addWidget(self.scan_btn)
        top.addWidget(self.devices_combo)
        top.addWidget(self.connect_btn)
        top.addWidget(self.save_btn)
        top.addWidget(self.dir_btn)
        top.addWidget(self.folder_label, 1)
        layout.addLayout(top)

        self.status_label = QLabel('Ready — scan to find a Myo armband.')
        self.count_label = QLabel('EMG 0 samples | IMU 0 samples | 0 packets')
        layout.addWidget(self.status_label)
        layout.addWidget(self.count_label)

        chart_and_panel = QHBoxLayout()
        plot_column = QVBoxLayout()
        chart_and_panel.addLayout(plot_column, stretch=4)
        layout.addLayout(chart_and_panel, stretch=1)

        self.build_plots(plot_column)
        self.build_protocol_panel(chart_and_panel)
        self.timer = QTimer(self)
        self.timer.setInterval(50)  # Display refresh does not resample acquired data.
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.protocol_timer = QTimer(self)
        self.protocol_timer.setInterval(50)
        self.protocol_timer.timeout.connect(self.update_protocol)

    def toggle_recording(self):
        if self.logging:
            self.close_recording()
            return
        if not self.stream_ready:
            QMessageBox.information(self, 'Not connected', 'Connect to a streaming Myo before recording.')
            return
        selected = QFileDialog.getExistingDirectory(self, 'Choose recording folder', str(self.sample_dir))
        if not selected:
            return
        try:
            start_ns = time.perf_counter_ns()
            self.logger.start(selected, start_ns)
        except (OSError, RuntimeError) as exc:
            self.on_error(f'Cannot open recording files: {exc}')
            return
        self.sample_dir = Path(selected)
        self.folder_label.setText(str(self.sample_dir))
        self.protocol_manager.reset()
        self.progress_bar.setValue(0)
        self.timer_label.setText('--')
        self.logging = True
        self.save_btn.setText('Stop Recording')
        self.status_label.setText('Recording two CSV files in ' + str(self.sample_dir))

    def close_recording(self):
        if self.protocol_active:
            self.stop_protocol('Stopped')
        if not self.logging:
            return
        self.logging = False
        try:
            self.logger.stop(time.perf_counter_ns())
        except OSError as exc:
            self.on_error(f'Error closing recording files: {exc}')
        self.save_btn.setText('Start Recording')
        if self.stream_ready:
            self.status_label.setText('Recording stopped; CSV files closed.')

    def on_packet(self, data):
        self.packet_count += 1
        if data['modality'] == 'EMG':
            for sample in data['samples']:
                self.emg_samples += 1
                self.emg_buffer.append(sample)
        else:
            self.imu_samples += 1
            self.accel_buffer.append(data['accel'])
            self.gyro_buffer.append(data['gyro'])
        if self.logging:
            label, step = self.protocol_manager.label_at(data['host_monotonic_ns'])
            try:
                self.logger.write(data, label, step, self.emg_samples, self.imu_samples)
            except (OSError, ValueError) as exc:
                self.close_recording()
                self.on_error(f'Recording write failed: {exc}')

    def refresh(self):
        self.count_label.setText(f'EMG {self.emg_samples:,} samples | IMU {self.imu_samples:,} samples | {self.packet_count:,} packets')
        self.refresh_plots()

    def on_stream_ready(self):
        self.stream_ready = True
        self.save_btn.setEnabled(True)

    def choose_folder(self):
        selected = QFileDialog.getExistingDirectory(self, 'Recording output folder', str(self.sample_dir))
        if selected:
            self.sample_dir = Path(selected)
            self.folder_label.setText(selected)

    def new_worker(self):
        self.worker = MyoWorker()
        self.worker.status.connect(self.status_label.setText)
        self.worker.error.connect(self.on_error)
        self.worker.discovered.connect(self.on_found)
        self.worker.packet.connect(self.on_packet)
        self.worker.ready.connect(self.on_stream_ready)
        self.worker.finished.connect(self.on_finished)

    def scan(self):
        if self.worker and self.worker.isRunning():
            return
        self.new_worker()
        self.scan_btn.setEnabled(False)
        self.connect_btn.setEnabled(False)
        self.worker.scan()

    def on_found(self, found):
        self.devices = [d for d, _ in found]
        self.devices_combo.clear()
        for d, name in found:
            self.devices_combo.addItem(f'{name} ({d.address})')

    def toggle_connect(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.connect_btn.setEnabled(False)
            self.status_label.setText('Disconnecting...')
            return
        index = self.devices_combo.currentIndex()
        if index < 0 or index >= len(self.devices):
            QMessageBox.information(self, 'No device', 'Scan and select a Myo device first.')
            return
        if self.protocol_active:
            self.stop_protocol('Stopped')
        self.emg_buffer.clear()
        self.accel_buffer.clear()
        self.gyro_buffer.clear()
        self.emg_samples = self.imu_samples = self.packet_count = 0
        self.new_worker()
        self.scan_btn.setEnabled(False)
        self.stream_ready = False
        self.connect_btn.setText('Disconnect')
        self.worker.connect_device(self.devices[index])
        self.save_btn.setEnabled(False)

    def on_error(self, message):
        self.status_label.setText('Error: ' + message)

    def on_finished(self):
        self.stream_ready = False
        self.close_recording()
        self.scan_btn.setEnabled(True)
        self.connect_btn.setEnabled(True)
        self.connect_btn.setText('Connect')
        self.save_btn.setEnabled(False)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            if not self.worker.wait(4000):
                event.ignore()
                self.status_label.setText('Waiting for BLE cleanup; try closing again.')
                return
        self.close_recording()
        super().closeEvent(event)
