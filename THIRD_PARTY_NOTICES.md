# Third-Party Acknowledgments and License Notices

Myo Monitor is an independently maintained Python application for collecting and visualizing EMG and IMU data from the Myo Armband.

## Projects consulted during development

### dl-myo (Dongle-less Myo)

- Repository: https://github.com/iomz/dl-myo
- Author: Iori Mizutani and contributors
- License: GNU General Public License v3.0 (GPL-3.0)
- Relationship: Referenced for the approach to dongle-less BLE communication. `dl-myo` is not a runtime dependency of dongle-less-myo-app.

**Important:** This acknowledgment does not grant permission to relicense copied GPL-covered source code under MIT. If code from `dl-myo` was copied or adapted, review whether the resulting software must comply with GPL-3.0 before publishing under MIT.

### Myo Bluetooth Protocol

- Repository: https://github.com/thalmiclabs/myo-bluetooth/
- Maintainer: Thalmic Labs / North (archived)
- License: Apache License 2.0
- Relationship: Official Bluetooth protocol specification consulted for GATT services, characteristics, commands, and sensor packet formats.

If copyrightable Apache-licensed material is included in this repository, retain applicable copyright notices, the Apache-2.0 license text, and any required NOTICE information.

## Python libraries

The application uses third-party packages, including:

- Bleak (MIT): https://github.com/hbldh/bleak
- PySide6 / Qt for Python (LGPL-3.0, GPL, or commercial licensing options): https://doc.qt.io/qtforpython-6/
- PyQtGraph (MIT): https://github.com/pyqtgraph/pyqtgraph
- NumPy (BSD-3-Clause): https://numpy.org/

These dependencies are separately licensed; the MIT license applied to the original Myo Monitor source code does not replace their respective licenses. Verify exact dependency versions and redistribution obligations, especially when bundling binaries or installers.

## Project license

Subject to verification that the distributed project does not contain GPL-covered source code requiring different licensing, the independently authored Myo Monitor source code is distributed under the MIT License; see `LICENSE`.