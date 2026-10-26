"""Protocol controls and timer-driven presentation for the main window."""
import csv
import time
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QProgressBar, QFileDialog, QMessageBox)
from protocol_manager import load_csv, parse_manual

class ProtocolPanelMixin:
    """Build protocol controls; defer timing and labels to ProtocolManager."""
    def build_protocol_panel(self, container):
        panel = QGroupBox('Labeling Protocol')
        panel.setMinimumWidth(270)
        panel.setMaximumWidth(350)
        column = QVBoxLayout(panel)
        hint = QLabel('Protocol columns: name, second, label\nOne step per line, or load a CSV file.')
        hint.setWordWrap(True)
        column.addWidget(hint)
        import_row = QHBoxLayout()
        self.import_btn = QPushButton('Load Protocol CSV')
        self.import_btn.clicked.connect(self.load_protocol_csv)
        self.clear_import_btn = QPushButton('Clear CSV')
        self.clear_import_btn.clicked.connect(self.clear_protocol_csv)
        self.clear_import_btn.setEnabled(False)
        import_row.addWidget(self.import_btn)
        import_row.addWidget(self.clear_import_btn)
        column.addLayout(import_row)
        self.import_label = QLabel('Manual protocol')
        self.import_label.setWordWrap(True)
        column.addWidget(self.import_label)
        self.protocol_editor = QPlainTextEdit()
        self.protocol_editor.setPlainText('Rest, 3, 0\nGesture 1, 5, 1\nRest, 3, 0\nGesture 2, 5, 2')
        self.protocol_editor.setMaximumHeight(150)
        column.addWidget(self.protocol_editor)
        self.protocol_start_btn = QPushButton('▶ Start Protocol')
        self.protocol_start_btn.clicked.connect(self.toggle_protocol)
        column.addWidget(self.protocol_start_btn)
        self.state_label = QLabel('Idle')
        self.state_label.setAlignment(Qt.AlignCenter)
        self.state_label.setWordWrap(True)
        self.state_label.setMinimumHeight(85)
        self.state_label.setStyleSheet('background:#F5F5F5; border:2px solid #CCCCCC; border-radius:9px; font-size:23px; font-weight:bold; padding:10px; color:#202020;')
        column.addWidget(self.state_label)
        self.timer_label = QLabel('--')
        self.timer_label.setAlignment(Qt.AlignCenter)
        self.timer_label.setMinimumHeight(90)
        self.timer_label.setStyleSheet('background:#E8F0FE; border:2px solid #A0B9F5; border-radius:9px; font-size:36px; font-weight:bold; color:#0044AA;')
        column.addWidget(self.timer_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat('0%')
        self.progress_bar.setStyleSheet('QProgressBar {border:1px solid #CCC; text-align:center; color:#222;} QProgressBar::chunk {background:#0078D7;}')
        column.addWidget(self.progress_bar)
        self.protocol_info = QLabel('Labels are written into both CSV files.\nStart Recording before Start Protocol.')
        self.protocol_info.setWordWrap(True)
        column.addWidget(self.protocol_info)
        column.addStretch(1)
        container.addWidget(panel, stretch=1)

    def parse_steps(self):
        if self.imported_protocol_path is not None:
            return list(self.imported_steps)
        return parse_manual(self.protocol_editor.toPlainText())

    def load_protocol_csv(self):
        if self.protocol_active:
            return
        filename, _ = QFileDialog.getOpenFileName(self, 'Load protocol CSV',
                           str(self.sample_dir), 'CSV Files (*.csv);;All Files (*)')
        if not filename:
            return
        try:
            steps = load_csv(filename)
        except (OSError, UnicodeError, ValueError, csv.Error) as exc:
            QMessageBox.warning(self, 'Cannot load protocol', str(exc))
            return
        self.imported_steps = steps
        self.imported_protocol_path = Path(filename)
        self.protocol_editor.setPlainText('\n'.join(
            f'{name}, {duration:g}, {label}' for name, duration, label in steps))
        self.import_label.setText(f'Loaded: {self.imported_protocol_path.name} ({len(steps)} steps)')
        self.protocol_editor.setEnabled(False)
        self.clear_import_btn.setEnabled(True)

    def clear_protocol_csv(self):
        if self.protocol_active:
            return
        self.imported_protocol_path = None
        self.imported_steps = []
        self.import_label.setText('Manual protocol')
        self.protocol_editor.setEnabled(True)
        self.clear_import_btn.setEnabled(False)

    def toggle_protocol(self):
        if self.protocol_active:
            self.stop_protocol('Stopped')
            return
        if not self.logging:
            QMessageBox.information(self, 'Recording required', 'Connect Myo and start recording before starting a labeling protocol.')
            return
        try:
            self.protocol_steps = self.parse_steps()
        except ValueError as exc:
            QMessageBox.warning(self, 'Invalid protocol', str(exc))
            return
        self.protocol_active = True
        self.protocol_editor.setEnabled(False)
        self.import_btn.setEnabled(False)
        self.clear_import_btn.setEnabled(False)
        self.protocol_start_btn.setText('■ Stop Protocol')
        self.protocol_index = -1
        self.protocol_started_ns = time.perf_counter_ns()
        self.protocol_manager.begin(self.protocol_steps, self.protocol_started_ns)
        self.total_duration_ns = int(sum(duration for _, duration, _ in self.protocol_steps) * 1e9)
        self.next_protocol_step()
        self.protocol_timer.start()

    def next_protocol_step(self):
        self.protocol_index += 1
        if self.protocol_index >= len(self.protocol_steps):
            self.stop_protocol('Done!')
            self.progress_bar.setValue(100)
            self.progress_bar.setFormat('100%')
            return
        name, duration, label = self.protocol_steps[self.protocol_index]
        self.step_deadline_ns = self.protocol_manager.deadlines[self.protocol_index]
        self.state_label.setText(name)
        self.timer_label.setText(str(int(np.ceil(duration))))

    def update_protocol(self):
        if not self.protocol_active:
            return
        now = time.perf_counter_ns()
        while self.protocol_active and now >= self.step_deadline_ns:
            self.next_protocol_step()
        if self.protocol_active:
            remaining = max(0, self.step_deadline_ns - now)
            self.timer_label.setText(str(int(np.ceil(remaining / 1e9))))
            percentage = min(100, int(100 * (now - self.protocol_started_ns) / self.total_duration_ns))
            self.progress_bar.setValue(percentage)
            self.progress_bar.setFormat(f'{percentage}%')

    def stop_protocol(self, status='Stopped'):
        self.protocol_timer.stop()
        self.protocol_active = False
        self.protocol_editor.setEnabled(self.imported_protocol_path is None)
        self.import_btn.setEnabled(True)
        self.clear_import_btn.setEnabled(self.imported_protocol_path is not None)
        self.protocol_start_btn.setText('▶ Start Protocol')
        self.protocol_manager.stop(min(time.perf_counter_ns(), self.protocol_manager.end_ns))
        self.state_label.setText('Idle')
        self.timer_label.setText(status)
        if status != 'Done!':
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat('0%')
