#!/usr/bin/env python3
"""Serial → OSC bridge: muscle effort into TouchDesigner.

Reads the EMG stream from the ESP32 (same 2-byte format as plot.py),
computes the effort envelope, and sends it as OSC to TouchDesigner:

    /emg/effort   float 0..1.5   (smoothed, instant attack / soft decay)
    /emg/raw      float 0..1     (latest raw sample, normalised)

Usage:
    venv/bin/python bridge.py                    # OSC to 127.0.0.1:9001
    venv/bin/python bridge.py --port 9002        # different OSC port
    venv/bin/python bridge.py /dev/cu.usbserial-10 --port 9001

TouchDesigner side: add an OSC In CHOP, set Network Port to 9001 —
channels appear as soon as data flows. Reference `emg/effort` in any
parameter expression, e.g.  op('oscin1')['emg/effort']
"""

import argparse
import glob
import sys
import time

import numpy as np
import serial
from pythonosc.udp_client import SimpleUDPClient


def find_port() -> str:
    candidates = (glob.glob("/dev/cu.usbserial*")
                  + glob.glob("/dev/cu.SLAB*")
                  + glob.glob("/dev/cu.wchusbserial*")
                  + glob.glob("/dev/cu.usbmodem*"))
    if not candidates:
        sys.exit("No ESP32 serial port found.")
    return candidates[0]


class Envelope:
    def __init__(self):
        self.center = 1365.0
        self.level = 0.0
        self.floor = 30.0
        self.calibrating = 100

    def feed(self, samples: np.ndarray) -> float:
        if len(samples):
            self.center += 0.02 * (samples.mean() - self.center)
            burst = np.abs(samples - self.center).mean()
            self.level += 0.55 * (burst - self.level)
        if self.calibrating > 0:
            self.calibrating -= 1
            self.floor += 0.1 * (self.level * 1.5 + 8 - self.floor)
        elif self.level < self.floor * 1.2:
            self.floor += 0.005 * (self.level * 1.5 + 8 - self.floor)
        effort = (self.level - self.floor) / max(self.floor * 3.5, 25.0)
        return float(np.clip(effort, 0.0, 1.5))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("serial_port", nargs="?", default=None)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9001)
    args = ap.parse_args()

    sport = args.serial_port or find_port()
    ser = serial.Serial(sport, 115200, timeout=0)
    osc = SimpleUDPClient(args.host, args.port)
    print(f"{sport} → OSC {args.host}:{args.port}  (/emg/effort, /emg/raw)")
    print("Relax ~2s to calibrate. Ctrl-C to quit.")

    env = Envelope()
    pending = bytearray()
    effort_s = 0.0
    last_raw = 0.0

    try:
        while True:
            chunk = ser.read(65536)
            out = []
            if chunk:
                pending.extend(chunk)
                i = 0
                while i + 1 < len(pending):
                    if pending[i] & 0xF0 == 0xF0:
                        out.append(((pending[i] & 0x0F) << 8) | pending[i + 1])
                        i += 2
                    else:
                        i += 1
                del pending[:i]
            samples = np.asarray(out, dtype=float)
            effort = env.feed(samples)
            # instant attack, soft decay
            effort_s = effort if effort > effort_s else effort_s + 0.12 * (effort - effort_s)
            if len(samples):
                last_raw = float(samples[-1] / 4095.0)

            osc.send_message("/emg/effort", effort_s)
            osc.send_message("/emg/raw", last_raw)

            bar = "#" * int(min(effort_s, 1.5) * 30)
            print(f"\reffort {effort_s:4.2f} |{bar:<45s}|"
                  + ("[cal]" if env.calibrating else "     "), end="")
            time.sleep(0.02)  # ~50 sends/sec
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        ser.close()


if __name__ == "__main__":
    main()
