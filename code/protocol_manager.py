"""Parse protocols and resolve labels using host monotonic timestamps."""
import csv
import math
from bisect import bisect_right


def validate_step(name, second, label, row_number):
    name = str(name).strip()
    label = str(label).strip()
    if not name or not label:
        raise ValueError(f'Row {row_number}: name and label must not be empty')
    try:
        duration = float(str(second).strip())
    except ValueError as exc:
        raise ValueError(f'Row {row_number}: second must be a number') from exc
    if not math.isfinite(duration) or not 0 < duration <= 3600:
        raise ValueError(f'Row {row_number}: second must be > 0 and <= 3600')
    return name, duration, label


def parse_manual(text):
    steps = []
    for row_number, original in enumerate(text.splitlines(), 1):
        line = original.strip()
        if not line or line.startswith('#'):
            continue
        fields = next(csv.reader([line], skipinitialspace=True))
        if [part.strip().lower() for part in fields] == ['name','second','label']:
            continue
        if len(fields) != 3:
            raise ValueError(f'Line {row_number}: expected name, second, label')
        steps.append(validate_step(*fields, row_number))
    if not steps:
        raise ValueError('Add at least one protocol step.')
    return steps


def load_csv(filename):
    with open(filename, newline='', encoding='utf-8-sig') as file:
        reader = csv.reader(file, skipinitialspace=True)
        header = next(reader, None)
        if header is None or [v.strip().lower() for v in header] != ['name','second','label']:
            raise ValueError('CSV header must be exactly: name,second,label')
        steps = []
        for row_number, row in enumerate(reader, 2):
            if not row or all(not field.strip() for field in row):
                continue
            if len(row) != 3:
                raise ValueError(f'Row {row_number}: expected exactly three columns')
            steps.append(validate_step(*row, row_number))
    if not steps:
        raise ValueError('CSV must contain at least one protocol step')
    return steps


class ProtocolManager:
    """Use planned step deadlines rather than delayed GUI timer callback times."""
    def __init__(self):
        self.times = [0]
        self.values = [('Idle', 0)]
        self.deadlines = []
        self.steps = []
        self.started_ns = 0
        self.end_ns = 0
        self.active = False

    def reset(self):
        self.times = [0]
        self.values = [('Idle', 0)]
        self.deadlines = []
        self.steps = []
        self.active = False

    def begin(self, steps, start_ns):
        self.steps = list(steps)
        self.started_ns = start_ns
        self.deadlines = []
        elapsed = 0.0
        for _, seconds, _ in steps:
            elapsed += seconds
            self.deadlines.append(start_ns + round(elapsed * 1e9))
        self.end_ns = self.deadlines[-1]
        # Retain previous protocol history for packets still queued in Qt.
        cutoff = bisect_right(self.times, start_ns)
        self.times = self.times[:cutoff] + [start_ns]
        self.values = self.values[:cutoff] + [(steps[0][2], 1)]
        for index in range(1, len(steps)):
            self.times.append(self.deadlines[index - 1])
            self.values.append((steps[index][2], index + 1))
        self.times.append(self.end_ns)
        self.values.append(('Idle', 0))
        self.active = True

    def stop(self, stop_ns):
        if not self.active:
            return
        # Remove planned future transitions; keep historical transitions.
        index = bisect_right(self.times, stop_ns)
        self.times = self.times[:index]
        self.values = self.values[:index]
        if self.times[-1] == stop_ns:
            self.values[-1] = ('Idle', 0)
        else:
            self.times.append(stop_ns)
            self.values.append(('Idle', 0))
        self.active = False

    def label_at(self, timestamp_ns):
        return self.values[max(0, bisect_right(self.times, timestamp_ns) - 1)]

    def current_index(self, now_ns):
        return bisect_right(self.deadlines, now_ns)
