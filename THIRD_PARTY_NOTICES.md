# Third-party notices

Snap is licensed under the GNU General Public License v3.0 (see `LICENSE`).
The Windows release bundles the following third-party components, each under its own license.

| Component | License | Project |
|---|---|---|
| Qt for Python (PySide6, shiboken6) and the Qt libraries | LGPL-3.0 | https://www.qt.io/qt-for-python |
| PySide6-Fluent-Widgets (QFluentWidgets) | GPL-3.0 | https://github.com/zhiyiYo/PyQt-Fluent-Widgets |
| PySideSix-Frameless-Window | LGPL-3.0 | https://github.com/zhiyiYo/PyQt-Frameless-Window |
| darkdetect | BSD-3-Clause | https://github.com/albertosottile/darkdetect |
| MediaPipe | Apache-2.0 | https://github.com/google-ai-edge/mediapipe |
| MediaPipe Selfie Segmenter model (`assets/models/selfie_segmenter.tflite`) | Apache-2.0 | https://ai.google.dev/edge/mediapipe/solutions/vision/image_segmenter |
| absl-py | Apache-2.0 | https://github.com/abseil/abseil-py |
| FlatBuffers | Apache-2.0 | https://github.com/google/flatbuffers |
| certifi | MPL-2.0 | https://github.com/certifi/python-certifi |
| OpenCV (opencv-contrib-python) | Apache-2.0 | https://opencv.org |
| NumPy | BSD-3-Clause (and bundled permissive licenses) | https://numpy.org |
| python-sounddevice | MIT | https://github.com/spatialaudio/python-sounddevice |
| PortAudio (bundled with sounddevice) | MIT | http://www.portaudio.com |
| CFFI / pycparser | MIT-0 / BSD-3-Clause | https://cffi.readthedocs.io |
| keyboard | MIT | https://github.com/boppreh/keyboard |
| pygrabber | MIT | https://github.com/andreaschiavinato/python_grabber |
| comtypes | MIT | https://github.com/enthought/comtypes |
| pywin32 | PSF | https://github.com/mhammond/pywin32 |
| Python runtime | PSF-2.0 | https://www.python.org |

## Interoperability

Snap writes video frames to two existing virtual camera drivers through their public
shared-memory interfaces. It contains no code from either project, and it does not
bundle either driver; the user installs them separately.

- **OBS Studio virtual camera** (GPL-2.0-or-later), https://obsproject.com
- **Unity Capture** (MIT), https://github.com/schellingb/UnityCapture
