# emg-scope

A software oscilloscope for a DIY EMG (muscle signal) rig: an ESP32 streams ADC samples over USB serial, and a live matplotlib plot on the laptop shows the waveform and its spectrum. Built as the debugging eyes for a wearable EMG → real-time visuals instrument (and because buying an oscilloscope was not in the budget).

## What's here

- **`emg_scope_internal/emg_scope_internal.ino`** — ESP32 sketch using the chip's built-in ADC (GPIO34). One wire from your signal to the board. The path of least resistance.
- **`emg_scope/emg_scope.ino`** — ESP32 + MCP3208 (8-channel SPI ADC) version, for multi-channel rigs. Wiring in the header comment.
- **`plot.py`** — live scope display: waveform (last 0.5 s) + spectrum with a 50 Hz mains marker. Auto-detects the serial port. Title bar shows mean / peak-to-peak / loudest frequency.

## Setup

```sh
python3 -m venv venv
venv/bin/pip install pyserial matplotlib numpy
```

Flash a sketch to the ESP32 (Arduino IDE, board "ESP32 Dev Module"), then:

```sh
venv/bin/python plot.py
```

## Hard-won notes

- **Serial stays at 115200.** Cheap CH340 USB-serial chips silently corrupt data at 921600 on macOS — the plot shows structured garbage that looks exactly like a broken circuit. This cost an evening. `SAMPLE_RATE` (4000) is sized to fit 115200 baud at 2 bytes/sample.
- Wire format: 2 bytes per sample — `0xF0 | (sample >> 8)`, then `sample & 0xFF`. The `0xF` high nibble is a sync marker so the plot can resync mid-stream.
- A floating ADC pin is an antenna: expect a rail-to-rail 50 Hz wave until you connect something. Touching the pin with a finger is a free test signal (your body is the antenna).
- Close the Arduino Serial Monitor before running `plot.py` — they can't share the port.
