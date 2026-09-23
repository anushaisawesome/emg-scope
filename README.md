# emg-scope

Tools for a DIY EMG (muscle signal) rig: an ESP32 streams ADC samples over USB serial; Python on the laptop turns them into a live oscilloscope, a muscle-reactive visual, or OSC for TouchDesigner. Built as the working stack for a wearable EMG → real-time visuals instrument.

## What's here

- **`emg_scope_internal/emg_scope_internal.ino`** — ESP32 sketch using the chip's built-in ADC (GPIO34). One wire from your signal to the board. **This is the sketch the working rig runs.**
- **`emg_scope/emg_scope.ino`** — ESP32 + MCP3208 (8-channel SPI ADC) version, for multi-channel rigs. Wiring in the header comment.
- **`plot.py`** — live scope display: waveform (last 0.5 s) + spectrum with a 50 Hz mains marker. Auto-detects the serial port. Title bar shows mean / peak-to-peak / loudest frequency. **Start here to verify the hardware works.**
- **`burst.py`** — clench-reactive particle/flow visual (matplotlib). Keys: `f` fullscreen, `c` recalibrate, `q` quit.
- **`bridge.py`** — serial → OSC bridge: sends `/emg/effort` (0..1.5) to port 9001 at ~50 Hz for TouchDesigner or anything else that speaks OSC.
- **`td_build.py`** — paste-in-Textport script that builds a muscle-reactive TouchDesigner network listening to the bridge.

## Handover notes (robot arm integration)

The signal chain that works: forearm electrodes → hand-built amplifier board (BioAmp EXG Pill schematic, ~×11,000 gain, 1.1 V reference) → ESP32 GPIO34 → 2-byte samples over serial → laptop.

To drive a robot arm, the piece to reuse is the **`Envelope` class in `bridge.py`**: it converts the raw noisy signal into a smooth 0..1.5 "how hard is the muscle working" value with a self-calibrating noise floor (instant attack, soft decay). Grip control is then:

```
effort < 0.15        → hand open
effort 0.15 – 1.0    → proportional close (map to servo angle)
```

Two integration routes:
1. **Laptop in the loop** — run `bridge.py`, receive OSC on whatever controls the arm (or adapt the script to write to a serial servo controller directly).
2. **ESP32-only** — port the envelope maths into the sketch (it's ~15 lines: rectify around the resting mean, exponential smoothing, threshold) and drive servos from the ESP32's PWM. No laptop needed. Note the sketch currently streams at 4000 samples/s; compute the envelope over ~100-sample windows.

Calibration matters: the noise floor learns during ~2 s of relaxed arm at startup. Re-run calibration whenever electrodes are re-stuck or the wearer changes.

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
