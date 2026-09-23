#!/usr/bin/env python3
"""Live plot for the ESP32 + MCP3208 software scope.

Usage:
    pip3 install pyserial matplotlib numpy
    python3 plot.py              # auto-detects the ESP32 serial port
    python3 plot.py /dev/cu.usbserial-0001   # or name it explicitly

Top pane: last 0.5 s of the waveform (volts).
Bottom pane: live spectrum — a spike at 50 Hz is mains hum (finger-touch
test), a spike at some other fixed frequency is your amp oscillating.
Press Q or close the window to quit.
"""

import glob
import sys
from collections import deque

import numpy as np
import serial
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

BAUD = 115200
SAMPLE_RATE = 4000           # must match SAMPLE_RATE in the flashed sketch
VREF = 3.3
WINDOW_S = 0.5               # seconds of waveform shown


def find_port() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]
    candidates = (glob.glob("/dev/cu.usbserial*")
                  + glob.glob("/dev/cu.SLAB*")
                  + glob.glob("/dev/cu.wchusbserial*")
                  + glob.glob("/dev/cu.usbmodem*"))
    if not candidates:
        sys.exit("No ESP32 serial port found. Is it plugged in? "
                 "(pass the port explicitly: python3 plot.py /dev/cu.…)")
    if len(candidates) > 1:
        print(f"Multiple ports, using {candidates[0]} — pass one explicitly to override: {candidates}")
    return candidates[0]


def main() -> None:
    port = find_port()
    ser = serial.Serial(port, BAUD, timeout=0.05)
    print(f"Reading {port} at {BAUD} baud, {SAMPLE_RATE} S/s")

    n_window = int(WINDOW_S * SAMPLE_RATE)
    samples = deque([2048] * n_window, maxlen=n_window)
    pending = bytearray()

    fig, (ax_t, ax_f) = plt.subplots(2, 1, figsize=(10, 6))
    fig.canvas.manager.set_window_title("EMG software scope")

    t = np.arange(n_window) / SAMPLE_RATE
    (line_t,) = ax_t.plot(t, np.zeros(n_window), lw=0.6)
    ax_t.set_ylim(0, VREF)
    ax_t.set_xlim(0, WINDOW_S)
    ax_t.set_ylabel("volts")
    ax_t.set_xlabel("seconds")
    ax_t.axhline(VREF / 2, color="grey", lw=0.5, ls="--")  # mid-supply ref

    freqs = np.fft.rfftfreq(n_window, 1 / SAMPLE_RATE)
    (line_f,) = ax_f.plot(freqs, np.zeros(len(freqs)), lw=0.8)
    ax_f.set_xlim(0, 1000)
    ax_f.set_ylim(0, 0.2)
    ax_f.set_ylabel("amplitude (V)")
    ax_f.set_xlabel("Hz")
    ax_f.axvline(50, color="red", lw=0.5, ls="--")  # mains

    stats = ax_t.set_title("waiting for data…", fontsize=10)

    def decode(chunk: bytes) -> list[int]:
        """Pull 12-bit samples out of the byte stream, resyncing on 0xFn."""
        out = []
        pending.extend(chunk)
        i = 0
        while i + 1 < len(pending):
            if pending[i] & 0xF0 == 0xF0:
                out.append(((pending[i] & 0x0F) << 8) | pending[i + 1])
                i += 2
            else:
                i += 1  # mid-stream junk; skip to next sync byte
        del pending[:i]
        return out

    def update(_frame):
        chunk = ser.read(8192)
        if chunk:
            samples.extend(decode(chunk))
        v = np.asarray(samples) * VREF / 4095
        line_t.set_ydata(v)
        spectrum = np.abs(np.fft.rfft(v - v.mean())) * 2 / n_window
        line_f.set_ydata(spectrum)
        peak_i = spectrum[1:].argmax() + 1
        stats.set_text(
            f"mean {v.mean():.3f} V   p-p {v.max() - v.min():.3f} V   "
            f"loudest freq {freqs[peak_i]:.0f} Hz"
        )
        return line_t, line_f, stats

    ani = FuncAnimation(fig, update, interval=50, blit=False,
                        cache_frame_data=False)
    plt.tight_layout()
    plt.show()
    ser.close()


if __name__ == "__main__":
    main()
