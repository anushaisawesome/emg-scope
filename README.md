# emg-scope

This is the EMG half of a wearable I'm building for dancers. The wearable uses sparse IMUs for full-body pose reconstruction
and EMG for fine finger gesture recognition, and worn by a dancer it turns their movement into live visuals in TouchDesigner.
This repo is the muscle side: electrodes on my forearm feed a hand-built amplifier (about 11,000× gain), an ESP32 samples it
and streams it to my laptop, and the Python here turns that into a live oscilloscope, a clench-reactive visual, or OSC messages
for TouchDesigner.

<!-- TODO: add a short clip to docs/ and link it here: a clench on the forearm and the burst visual reacting, or plot.py's
waveform jumping when the muscle fires. A photo of the breadboard rig works as a second choice. -->

## How it works

1. **Amplifier.** A channel built from the BioAmp EXG Pill schematic (Upside Down Labs) on a breadboard: an instrumentation
   amplifier (about 11×), a bandpass filter for the EMG band and a 1000× gain stage, all leaning on a 1.1 V reference.
2. **ESP32.** `emg_scope_internal.ino` reads the amplifier on GPIO34 at 4,000 samples a second and sends each sample as two
   bytes over USB serial at 115200 baud. The first byte carries a `0xF` marker in its top four bits, so the laptop can find
   its place again if it starts reading mid-stream.
3. **Laptop.** `plot.py` shows the last half second of signal and its spectrum, with a line at 50 Hz for mains hum.
   `bridge.py` turns the raw signal into one smooth "how hard is the muscle working" value (`/emg/effort`, 0 to 1.5) with a
   noise floor it learns while your arm is relaxed, and sends it over OSC about 50 times a second.
4. **Visuals.** `burst.py` is a clench-reactive particle visual in matplotlib. `td_build.py` builds a matching TouchDesigner
   network that listens to the bridge.

## What's here

| File | What it does |
| --- | --- |
| `emg_scope_internal/emg_scope_internal.ino` | ESP32 sketch using the built-in ADC. This is the one the working rig runs. |
| `emg_scope/emg_scope.ino` | ESP32 with an MCP3208 (8-channel SPI ADC), for the multi-channel version. Wiring is in the header comment. |
| `plot.py` | Live scope: waveform, spectrum, and mean, peak-to-peak and loudest frequency in the title. Start here. |
| `burst.py` | Clench-reactive visual. Keys: `f` fullscreen, `c` recalibrate, `q` quit. |
| `bridge.py` | Serial to OSC: `/emg/effort` and `/emg/raw` to port 9001. |
| `td_build.py` | Paste into TouchDesigner's Textport to build a network driven by `/emg/effort`. |

## Run it

```sh
python3 -m venv venv
venv/bin/pip install pyserial matplotlib numpy python-osc
```

Flash `emg_scope_internal.ino` to the ESP32 (Arduino IDE, board "ESP32 Dev Module"), close the Serial Monitor, then:

```sh
venv/bin/python plot.py      # check the hardware first
venv/bin/python burst.py     # or the visual
venv/bin/python bridge.py    # or OSC for TouchDesigner (port 9001)
```

The serial port is found automatically. Relax your arm for the first couple of seconds so the noise floor calibrates, and
press `c` (or restart the bridge) whenever the electrodes are re-stuck.

## Things I learned the hard way

- **Keep serial at 115200.** The CH340 USB-serial chips on cheap ESP32 boards corrupt data at 921600 on macOS, and the
  garbage looks exactly like a broken circuit. That cost me an evening and a board I wrongly blamed.
- **A floating ADC pin is an antenna.** Expect a large 50 Hz wave until something is connected. Touching the pin gives you a
  free test signal.
- **Check the op-amp's supply range.** The chip the schematic specifies runs on 3.3 V; the common one I bought first didn't,
  and its output sat at the rail.

## Status

One channel works end to end: clench, and the scope and visuals respond. The MCP3208 sketch is written but not yet verified on
the rig. Next is a wearable perfboard version, then more channels around the arm.

## Reusing the envelope

If you want a muscle to drive something else (a robot gripper, say), the piece to reuse is the `Envelope` class in
`bridge.py`. Below about 0.15 the muscle is resting; from 0.15 to 1.0 you can map effort straight to a servo angle. On an
ESP32 alone, the same maths (rectify around the resting mean, smooth, threshold) fits in about 15 lines; compute it over
windows of about 100 samples.

## Credits

The amplifier follows the [BioAmp EXG Pill](https://github.com/upsidedownlabs/BioAmp-EXG-Pill) schematic by Upside Down Labs.
