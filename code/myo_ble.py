"""Myo BLE GATT transport and sensor packet decoder.

Official Myo Bluetooth protocol: https://github.com/thalmiclabs/myo-bluetooth/
"""
import asyncio
import struct
import time
from datetime import datetime, timezone

from bleak import BleakClient, BleakScanner
from PySide6.QtCore import QThread, Signal

BASE = '-a904-deb9-4748-2c7f4a124842'
def uuid(short):
    return f'd506{short:04x}{BASE}'

CONTROL_SERVICE = uuid(0x0001)
COMMAND = uuid(0x0401)
IMU = uuid(0x0402)
EMGS = [uuid(x) for x in (0x0105, 0x0205, 0x0305, 0x0405)]

class MyoWorker(QThread):
    discovered = Signal(object)
    status = Signal(str)
    packet = Signal(object)
    error = Signal(str)
    ready = Signal()

    def __init__(self):
        super().__init__()
        self.loop = None
        self.mode = 'idle'
        self.device = None

    def scan(self):
        self.mode = 'scan'
        self.start()

    def connect_device(self, device):
        self.mode = 'connect'
        self.device = device
        self.start()

    def stop(self):
        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(self._stop_event.set)

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self._stop_event = asyncio.Event()
        try:
            if self.mode == 'scan':
                self.loop.run_until_complete(self._scan())
            else:
                self.loop.run_until_complete(self._stream())
        except Exception as e:
            self.error.emit(f'{type(e).__name__}: {e}')
        finally:
            self.loop.close()
            self.loop = None

    async def _scan(self):
        self.status.emit('Scanning for Myo devices (8 s)...')
        results = await BleakScanner.discover(timeout=8, return_adv=True)
        found = []
        for device, adv in results.values():
            services = [s.lower() for s in adv.service_uuids]
            if 'myo' in ((adv.local_name or device.name or '').lower()) or CONTROL_SERVICE in services:
                found.append((device, adv.local_name or device.name or 'Myo'))
        self.discovered.emit(found)
        self.status.emit(f'Scan complete: {len(found)} device(s)')

    async def _stream(self):
        self.status.emit('Connecting...')
        async with BleakClient(self.device, timeout=20.0) as client:
            self.status.emit('Connected; configuring notifications...')
            available = {c.uuid.lower() for svc in client.services for c in svc.characteristics}
            needed = [COMMAND, IMU] + EMGS
            missing = [c for c in needed if c not in available]
            if missing:
                raise RuntimeError('Missing Myo characteristics: ' + ', '.join(missing))
            packet_sequence = 0
            modality_sequence = {'EMG': 0, 'IMU': 0}

            def on_notification(sender, data):
                nonlocal packet_sequence
                # Timestamp acquired when Bleak invokes callback; not device sample time.
                host_monotonic_ns = time.perf_counter_ns()
                host_unix_ns = time.time_ns()
                payload = bytes(data)
                characteristic = sender.uuid.lower()
                modality = 'IMU' if characteristic == IMU else 'EMG'
                packet_sequence += 1
                modality_sequence[modality] += 1
                base = {
                    'modality': modality,
                    'packet_sequence': packet_sequence,
                    'modality_packet_sequence': modality_sequence[modality],
                    'characteristic_uuid': characteristic,
                    'host_monotonic_ns': host_monotonic_ns,
                    'host_unix_ns': host_unix_ns,
                    'host_iso_utc': datetime.fromtimestamp(host_unix_ns / 1e9, tz=timezone.utc).isoformat(),
                    'payload_hex': payload.hex(),
                }
                if modality == 'EMG':
                    if len(payload) != 16:
                        self.error.emit(f'Unexpected EMG payload size: {len(payload)}')
                        return
                    # Two consecutive 8-channel signed int8 samples per notification.
                    samples = struct.unpack('<16b', payload)
                    base['samples'] = [samples[:8], samples[8:]]
                else:
                    if len(payload) != 20:
                        self.error.emit(f'Unexpected IMU payload size: {len(payload)}')
                        return
                    # Myo protocol uses little-endian signed 16-bit fields on the wire.
                    vals = struct.unpack('<10h', payload)
                    base['quat'] = [v / 16384.0 for v in vals[:4]]
                    base['accel'] = [v / 2048.0 for v in vals[4:7]]  # g
                    base['gyro'] = [v / 16.0 for v in vals[7:10]]  # deg/s
                    base['raw_int16'] = vals
                self.packet.emit(base)

            for characteristic in EMGS + [IMU]:
                await client.start_notify(characteristic, on_notification)
            # Unlock hold, never sleep, raw/unfiltered EMG + IMU data, classifier off.
            await client.write_gatt_char(COMMAND, bytes([0x0A, 0x01, 0x02]), response=True)
            await client.write_gatt_char(COMMAND, bytes([0x09, 0x01, 0x01]), response=True)
            await client.write_gatt_char(COMMAND, bytes([0x01, 0x03, 0x03, 0x01, 0x00]), response=True)
            self.status.emit('Streaming EMG (200 Hz) + IMU (50 Hz)')
            self.ready.emit()
            try:
                while client.is_connected and not self._stop_event.is_set():
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=0.25)
                    except asyncio.TimeoutError:
                        pass
            finally:
                try:
                    await client.write_gatt_char(COMMAND, bytes([0x01, 0x03, 0x00, 0x00, 0x00]), response=True)
                except Exception:
                    pass
                for characteristic in EMGS + [IMU]:
                    try:
                        await client.stop_notify(characteristic)
                    except Exception:
                        pass
                self.status.emit('Disconnected')
