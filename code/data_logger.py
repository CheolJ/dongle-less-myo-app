"""Write native-rate EMG and IMU packets to separate CSV files."""
import csv
from datetime import datetime
from pathlib import Path

EMG_HEADERS = ['host_iso_utc','host_unix_ns','host_monotonic_ns','packet_sequence',
    'modality_packet_sequence','characteristic_uuid','sample_in_packet','emg_sample_sequence',
    'emg_1','emg_2','emg_3','emg_4','emg_5','emg_6','emg_7','emg_8','payload_hex',
    'label','protocol_step']
IMU_HEADERS = ['host_iso_utc','host_unix_ns','host_monotonic_ns','packet_sequence',
    'modality_packet_sequence','characteristic_uuid','imu_sample_sequence',
    'quat_w','quat_x','quat_y','quat_z','accel_x_g','accel_y_g','accel_z_g',
    'gyro_x_dps','gyro_y_dps','gyro_z_dps','payload_hex','label','protocol_step']

class DataLogger:
    """Own recording files and write rows in received packet order."""
    def __init__(self):
        self.files = []
        self.writers = {}
        self.active = False
        self.start_ns = None
        self.stop_ns = None
        self.session_id = None

    def start(self, directory, start_ns):
        if self.active:
            raise RuntimeError('Recording is already active.')
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        paths = [directory / f'myo_{stamp}_emg.csv', directory / f'myo_{stamp}_imu.csv']
        opened = []
        try:
            for path in paths:
                opened.append(path.open('x', newline='', encoding='utf-8'))
            writers = {'EMG': csv.DictWriter(opened[0], fieldnames=EMG_HEADERS),
                       'IMU': csv.DictWriter(opened[1], fieldnames=IMU_HEADERS)}
            for writer in writers.values():
                writer.writeheader()
        except Exception:
            for handle in opened:
                handle.close()
            raise
        self.files, self.writers = opened, writers
        self.start_ns, self.stop_ns = start_ns, None
        self.session_id = stamp
        self.active = True

    def accepts(self, timestamp_ns):
        return (self.start_ns is not None and timestamp_ns >= self.start_ns
                and (self.stop_ns is None or timestamp_ns < self.stop_ns))

    def write(self, packet, label, step, emg_sequence, imu_sequence):
        if not self.active or not self.accepts(packet['host_monotonic_ns']):
            return
        fields = {key: packet[key] for key in (
            'host_iso_utc','host_unix_ns','host_monotonic_ns','packet_sequence',
            'modality_packet_sequence','characteristic_uuid','payload_hex')}
        if packet['modality'] == 'EMG':
            for index, sample in enumerate(packet['samples']):
                row = dict(fields, sample_in_packet=index,
                           emg_sample_sequence=emg_sequence - len(packet['samples']) + index + 1,
                           label=label, protocol_step=step)
                row.update({f'emg_{j+1}': value for j, value in enumerate(sample)})
                self.writers['EMG'].writerow(row)
        else:
            row = dict(fields, imu_sample_sequence=imu_sequence, label=label, protocol_step=step)
            row.update(dict(zip(['quat_w','quat_x','quat_y','quat_z'],packet['quat'])))
            row.update(dict(zip(['accel_x_g','accel_y_g','accel_z_g'],packet['accel'])))
            row.update(dict(zip(['gyro_x_dps','gyro_y_dps','gyro_z_dps'],packet['gyro'])))
            self.writers['IMU'].writerow(row)

    def stop(self, stop_ns=None):
        self.stop_ns = stop_ns
        self.active = False
        error = None
        for handle in self.files:
            try:
                handle.flush()
                handle.close()
            except OSError as exc:
                error = exc
        self.files = []
        self.writers = {}
        self.start_ns = None
        if error:
            raise error
