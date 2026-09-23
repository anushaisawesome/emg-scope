#!/usr/bin/env python3
"""Clench-reactive particle burst — visual demo for the EMG rig.

Reads the same 2-byte serial stream as plot.py, computes a muscle-effort
envelope, and drives a particle system: rest = gentle drifting sparkle,
clench = radial burst whose size/speed/colour scale with effort.

Usage:
    venv/bin/python burst.py            # auto-detects the serial port
Keys:
    f = fullscreen toggle   ·   c = recalibrate baseline   ·   q = quit

The baseline auto-calibrates for the first 2 seconds — keep the arm
relaxed after launching.
"""

import glob
import sys

import numpy as np
import serial
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

BAUD = 115200
VREF = 3.3
MAX_PARTICLES = 4000
FRAME_MS = 33


def find_port() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]
    candidates = (glob.glob("/dev/cu.usbserial*")
                  + glob.glob("/dev/cu.SLAB*")
                  + glob.glob("/dev/cu.wchusbserial*")
                  + glob.glob("/dev/cu.usbmodem*"))
    if not candidates:
        sys.exit("No ESP32 serial port found.")
    return candidates[0]


class Envelope:
    """Rectified + smoothed muscle effort, self-calibrating baseline."""

    def __init__(self):
        self.center = 1365.0        # ~1.1V in counts, refined live
        self.level = 0.0            # smoothed envelope (counts)
        self.floor = 30.0           # noise floor (counts), learned at rest
        self.calibrating = 60       # frames of forced learning at startup

    def feed(self, samples: np.ndarray) -> float:
        if len(samples):
            self.center += 0.02 * (samples.mean() - self.center)
            burst = np.abs(samples - self.center).mean()
            self.level += 0.25 * (burst - self.level)
        if self.calibrating > 0:
            self.calibrating -= 1
            self.floor += 0.1 * (self.level * 1.5 + 10 - self.floor)
        elif self.level < self.floor * 1.2:
            self.floor += 0.005 * (self.level * 1.5 + 10 - self.floor)
        # 0 at/below noise floor, ~1 around a solid clench
        effort = (self.level - self.floor) / max(self.floor * 6, 40.0)
        return float(np.clip(effort, 0.0, 1.5))


def main() -> None:
    port = find_port()
    ser = serial.Serial(port, BAUD, timeout=0)
    print(f"Reading {port}. Keep arm relaxed ~2s for calibration. f=fullscreen c=recal q=quit")

    pending = bytearray()

    def read_samples() -> np.ndarray:
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
        return np.asarray(out, dtype=float)

    env = Envelope()

    # particle state
    pos = np.zeros((0, 2))
    vel = np.zeros((0, 2))
    age = np.zeros(0)

    plt.rcParams["toolbar"] = "none"
    fig, ax = plt.subplots(figsize=(10, 7), facecolor="black")
    ax.set_facecolor("black")
    ax.set_xlim(-1, 1); ax.set_ylim(-1, 1)
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    fig.subplots_adjust(0, 0, 1, 1)
    fig.canvas.manager.set_window_title("clench")

    scat = ax.scatter([], [], s=[], c=[], cmap="plasma", vmin=0, vmax=1, lw=0)
    meter = ax.text(0.02, 0.02, "", transform=ax.transAxes,
                    color="#555555", fontsize=10, family="monospace")

    cmap = matplotlib.colormaps["plasma"]

    def on_key(event):
        nonlocal pos, vel, age
        if event.key == "f":
            fig.canvas.manager.full_screen_toggle()
        elif event.key == "c":
            env.calibrating = 60
        elif event.key == "q":
            plt.close(fig)

    fig.canvas.mpl_connect("key_press_event", on_key)

    rng = np.random.default_rng(7)

    def update(_):
        nonlocal pos, vel, age
        effort = env.feed(read_samples())

        # spawn: a whisper at rest, a storm on clench
        n = int(2 + effort * 220)
        theta = rng.uniform(0, 2 * np.pi, n)
        speed = (0.004 + 0.055 * effort) * rng.uniform(0.3, 1.0, n)
        newp = np.column_stack([np.cos(theta), np.sin(theta)]) * 0.02
        newv = np.column_stack([np.cos(theta), np.sin(theta)]) * speed[:, None]
        pos = np.vstack([pos, newp]); vel = np.vstack([vel, newv])
        age = np.concatenate([age, np.zeros(n)])

        pos += vel
        vel *= 0.985
        age += 1
        alive = (age < 90) & (np.abs(pos) < 1.2).all(axis=1)
        pos, vel, age = pos[alive], vel[alive], age[alive]
        if len(pos) > MAX_PARTICLES:
            pos, vel, age = pos[-MAX_PARTICLES:], vel[-MAX_PARTICLES:], age[-MAX_PARTICLES:]

        life = 1 - age / 90
        scat.set_offsets(pos if len(pos) else np.zeros((0, 2)))
        scat.set_sizes(4 + 26 * life * (0.3 + effort))
        colors = cmap(np.clip(0.15 + 0.85 * (1 - age / 90) * (0.35 + 0.65 * min(effort, 1)), 0, 1))
        colors[:, 3] = np.clip(life, 0, 1)
        scat.set_facecolor(colors)
        meter.set_text(f"effort {min(effort, 1.5):4.2f}" + ("  [calibrating]" if env.calibrating else ""))
        return scat, meter

    ani = FuncAnimation(fig, update, interval=FRAME_MS, blit=False,
                        cache_frame_data=False)
    plt.show()
    ser.close()


if __name__ == "__main__":
    main()
