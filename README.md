# VisOPU

**TL.0009 Pan-Tilt Device Control & Surveillance Platform**

VisOPU is a professional-grade desktop application for controlling the **TL.0009** pan-tilt platform, integrating IP camera streams (including thermal), YOLO-based object detection, laser rangefinding, and offline tactical mapping — all in a single unified interface.

---

## Features

| Module | Description |
|---|---|
| **Pan-Tilt Control** | Precise speed/position control of TL.0009 via TCP. Auto-polling of position, speed, and temperature. |
| **Dual Camera** | RTSP/ONVIF IP camera streams with overlay buttons (zoom, focus, laser, detect, track, filters). |
| **Thermal Camera** | Pseudocolor palettes (WhiteHot, BlackHot, Iron, Rainbow, Arctic, Lava, Hot) with EMA-smoothed temperature display and FLIR-style HUD. |
| **YOLO Detection** | Real-time object detection with ByteTrack multi-target tracking, CLAHE preprocessing, and multi-frame confirmation. |
| **Laser Rangefinder** | 3 km LRF module with continuous/single ranging, distance overlay on camera view. |
| **Offline Map** | Leaflet-based tactical map with MBTiles support, distance measurement, bearing lines, and beam visualization. |
| **Keyboard Control** | Arrow keys for pan/tilt, Q/E for zoom, spacebar for stop — full hands-free operation. |
| **Pelco-D / ONVIF** | Full PTZ protocol support for zoom, focus, and iris via Pelco-D binary frames or ONVIF SOAP. |

---

## Architecture

```
VisOPU/
├── main.py                  # Entry point — logging, exception handling, Qt setup
├── app/
│   ├── mainwindow.py        # MainWindow — device wiring, UI layout, signal routing
│   ├── widgets.py           # CameraWidget, CollapsiblePanel, SlidingPanel
│   ├── communicators.py     # DeviceCommunicator, LaserCommunicator, PelcoD, ONVIF
│   ├── detector.py          # YoloDetector — multi-frame confirmation + ByteTrack
│   ├── offline_map.py       # MBTilesServer — local Leaflet tile server
│   └── styles.py            # Apple-style dark theme stylesheet
├── data/                    # Offline map tiles (*.mbtiles)
├── VisOPU.spec              # PyInstaller build specification
├── build.bat                # One-click build script
├── run.bat                  # Quick launch for development
└── requirements.txt         # Python dependencies
```

---

## Installation

### Prerequisites

- **Python 3.10+** (tested with 3.14)
- **Windows 10/11** (QtWebEngine requirement)

### Setup

```bash
# Clone the repository
git clone https://github.com/atabaevkirill-dev/VisOPU.git
cd VisOPU

# Install dependencies
pip install -r requirements.txt

# Download YOLO models (place in project root)
# yolov8n.pt (~6 MB) and/or yolov8m.pt (~50 MB) from ultralytics

# Run the application
python main.py
```

### Build Executable

```bash
# Install PyInstaller
pip install pyinstaller

# Build (creates dist/VisOPU/VisOPU.exe)
pyinstaller VisOPU.spec --clean --noconfirm
# or use build.bat on Windows
```

---

## Usage

### 1. Connect TL.0009 Device

1. Enter the device IP and port in the connection panel
2. Click **Connect** — the status indicator turns green
3. Use sliders to set pan/tilt speed, or enter exact position values
4. Keyboard: **Arrow keys** for pan/tilt, **Q/E** for zoom

### 2. Connect Cameras

- **CAM1** — Standard IP camera (RTSP URL)
- **CAM2** — Thermal camera (RTSP URL, enables thermal palette/temperature overlay)

### 3. Object Detection

1. Click **DETECT** overlay button on camera view to enable YOLO
2. Click **TRACK** to enable multi-object ByteTrack tracking
3. Use the class filter to focus on specific target types

### 4. Laser Rangefinder

1. Enter LRF module IP and connect
2. Single or continuous ranging modes available
3. Distance is overlaid on the camera view with target labels

### 5. Tactical Map

- **Left-click** — place measurement points
- **Right-click** — set device position
- Map supports offline MBTiles for disconnected operation
- Beam visualization shows pan direction on the map

---

## Configuration

The application auto-detects:
- GPU availability (CUDA for YOLO acceleration)
- YOLO model files in the project directory
- MBTiles files in `data/` for offline maps
- ONVIF camera capabilities (zoom, focus, PTZ)

### Camera Overlay Buttons

| Button | Function |
|---|---|
| **LSR** | Toggle laser distance overlay |
| **DET** | Toggle YOLO detection |
| **TRK** | Toggle ByteTrack tracking |
| **FLT** | Cycle video filters (Normal → NVG → Edge → B&W) |
| **PAL** | Cycle thermal palette (thermal camera only) |
| **TMP** | Toggle temperature HUD (thermal camera only) |

---

## Thermal Camera

The thermal module follows FLIR/InfiRay/Seek Thermal best practices:

- **EMA smoothing** (α=0.15) for stable temperature display
- **7×7 pixel averaging** for noise-resistant spot readings
- **Percentile-based auto-range** (1st/99th) for optimal contrast
- **MAX hold** (2-second peak retention) per FLIR convention
- **4 Hz update rate** for smooth, non-flickering display

---

## Supported Protocols

| Protocol | Device | Features |
|---|---|---|
| **TL.0009 TCP** | Pan-tilt platform | Speed, position, temperature polling |
| **RTSP** | IP cameras | Video stream via FFmpeg |
| **Pelco-D** | PTZ cameras | Pan, tilt, zoom, focus, iris |
| **ONVIF** | IP cameras | PTZ control, zoom, focus |
| **Binary TCP** | 3km LRF module | Single/continuous ranging |

---

## Requirements

| Component | Minimum | Recommended |
|---|---|---|
| OS | Windows 10 | Windows 11 |
| Python | 3.10 | 3.12+ |
| RAM | 4 GB | 8 GB |
| GPU | Integrated | NVIDIA (CUDA) |
| Network | 100 Mbps | 1 Gbps |

---

## Project Structure

```
main.py                 Entry point with exception handling and Qt setup
app/mainwindow.py       Main window — device panels, signal wiring, UI
app/widgets.py          Camera widget with thermal/detection/overlay support
app/communicators.py    TCP protocol handlers (TL.0009, LRF, Pelco-D, ONVIF)
app/detector.py         YOLO detector with ByteTrack and CLAHE
app/offline_map.py      Local MBTiles/OSM tile server with Leaflet
app/styles.py           Dark mode Apple-style theme
```

---

## License

This project is proprietary. All rights reserved.

---

## Author

**Kirill Atabaev** — [atabaevkirill-dev](https://github.com/atabaevkirill-dev)
