"""Dependency-free regression checks for protocol timing and recording CSV schema."""
import csv
import tempfile
import unittest
from pathlib import Path
from code.data_logger import DataLogger, EMG_HEADERS, IMU_HEADERS
from code.protocol_manager import ProtocolManager, parse_manual, load_csv


class CoreTests(unittest.TestCase):
    def test_protocol_parse_and_planned_boundaries(self):
        steps = parse_manual('name,second,label\nRest, 1, 0\nGesture, 2, 1')
        model = ProtocolManager()
        model.begin(steps, 1_000_000_000)
        self.assertEqual(model.label_at(1_500_000_000), ('0', 1))
        self.assertEqual(model.label_at(2_000_000_000), ('1', 2))
        self.assertEqual(model.label_at(4_000_000_000), ('Idle', 0))
        model.stop(2_500_000_000)
        self.assertEqual(model.label_at(2_600_000_000), ('Idle', 0))
        self.assertEqual(model.label_at(1_500_000_000), ('0', 1))
        model.begin(steps, 5_000_000_000)
        self.assertEqual(model.label_at(2_000_000_000), ('1', 2))
        self.assertEqual(model.label_at(5_100_000_000), ('0', 1))

    def test_csv_schema_and_sample_order(self):
        with tempfile.TemporaryDirectory() as folder:
            log = DataLogger()
            log.start(folder, 100)
            shared = dict(host_iso_utc='2026-10-26T00:00:00+00:00', host_unix_ns=1000,
                          host_monotonic_ns=101, packet_sequence=1,
                          modality_packet_sequence=1, characteristic_uuid='test',payload_hex='00')
            log.write(dict(shared, modality='EMG', samples=[tuple(range(8)), tuple(range(8,16))]), '1', 2, 2, 0)
            log.write(dict(shared, modality='IMU', quat=[1,0,0,0], accel=[0,0,1],gyro=[0,0,0]),'1',2,2,1)
            log.stop(200)
            paths=list(Path(folder).glob('*.csv'))
            self.assertEqual(len(paths),2)
            for modality, headers in [('emg',EMG_HEADERS),('imu',IMU_HEADERS)]:
                file=next(f for f in paths if f.name.endswith(modality+'.csv'))
                with file.open(newline='', encoding='utf-8') as h:
                    reader=csv.DictReader(h)
                    self.assertEqual(reader.fieldnames, headers)
                    rows=list(reader)
                    self.assertEqual(len(rows), 2 if modality=='emg' else 1)
                    self.assertTrue(all(row['label']=='1' for row in rows))
                    if modality=='emg':
                        self.assertEqual([r['sample_in_packet'] for r in rows], ['0','1'])
                        self.assertEqual([r['emg_sample_sequence'] for r in rows], ['1','2'])

    def test_import(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'protocol.csv'
            path.write_text('name,second,label\nRest,3,0\nGesture,5,1\n',encoding='utf-8')
            self.assertEqual(len(load_csv(path)),2)
            path.write_text('name,label,second\nRest,0,3\n',encoding='utf-8')
            with self.assertRaises(ValueError): load_csv(path)

if __name__ == '__main__':
    unittest.main()
