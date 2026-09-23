#!/usr/bin/env python3
"""Clench-reactive flow-field burst — visual demo for the EMG rig.

TouchDesigner-style: thin luminous streaks on black, swirling in a flow
field. Rest = slow drifting filaments. Clench = the field energises,
streaks lengthen and heat up, a shockwave ring fires on sharp onsets.

Usage:
    venv/bin/python burst.py            # auto-detects the serial port
Keys:
    f = fullscreen   ·   c = recalibrate baseline   ·   q = quit

Baseline auto-calibrates for ~2s at launch — keep the arm relaxed.
"""

import glob
import sys

import numpy as np
import serial
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.collections import LineCollection
from matplotlib.patches import Circle

BAUD = 115200
MAX_PARTICLES = 3200
FRAME_MS = 33
LIFE = 110  # frames


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
        self.center = 1365.0
        self.level = 0.0
        self.floor = 30.0
        self.calibrating = 60

    def feed(self, samples: np.ndarray) -> float:
        if len(samples):
            self.center += 0.02 * (samples.mean() - self.center)
            burst = np.abs(samples - self.center).mean()
            self.level += 0.3 * (burst - self.level)
        if self.calibrating > 0:
            self.calibrating -= 1
            self.floor += 0.1 * (self.level * 1.5 + 8 - self.floor)
        elif self.level < self.floor * 1.2:
            self.floor += 0.005 * (self.level * 1.5 + 8 - self.floor)
        # more sensitive than v1: smaller divisor, lower minimum
        effort = (self.level - self.floor) / max(self.floor * 3.5, 25.0)
        return float(np.clip(effort, 0.0, 1.5))


def main() -> None:
    port = find_port()
    ser = serial.Serial(port, BAUD, timeout=0)
    print(f"Reading {port}. Relax ~2s to calibrate. f=fullscreen c=recal q=quit")

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

    pos = np.zeros((0, 2))
    vel = np.zeros((0, 2))
    age = np.zeros(0)
    spin = np.zeros(0)

    plt.rcParams["toolbar"] = "none"
    fig, ax = plt.subplots(figsize=(10, 7), facecolor="black")
    ax.set_facecolor("black")
    ax.set_xlim(-1, 1); ax.set_ylim(-1, 1)
    ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    fig.subplots_adjust(0, 0, 1, 1)
    fig.canvas.manager.set_window_title("clench")

    streaks = LineCollection([], capstyle="round", zorder=3)
    glow = LineCollection([], capstyle="round", zorder=2)
    ax.add_collection(streaks)
    ax.add_collection(glow)

    core_ring = Circle((0, 0), 0.03, fill=False, lw=1.0, zorder=4,
                       edgecolor=(0.8, 0.7, 1.0, 0.35))
    ax.add_patch(core_ring)

    rings = []
    ring_artists = []

    meter = ax.text(0.02, 0.02, "", transform=ax.transAxes,
                    color="#2e2e3a", fontsize=9, family="monospace", zorder=5)

    cmap = matplotlib.colormaps["inferno"]
    rng = np.random.default_rng(7)
    effort_s = 0.0
    prev_effort = 0.0
    t = 0

    def on_key(event):
        if event.key == "f":
            fig.canvas.manager.full_screen_toggle()
        elif event.key == "c":
            env.calibrating = 60
        elif event.key == "q":
            plt.close(fig)

    fig.canvas.mpl_connect("key_press_event", on_key)

    def flow(p, tt, e):
        """Swirling flow field: rotation + travelling waves, energised by effort."""
        x, y = p[:, 0], p[:, 1]
        r = np.sqrt(x * x + y * y) + 1e-6
        # base rotation (tangential)
        fx, fy = -y / r, x / r
        # travelling wave curl for organic filaments
        k = 3.2
        fx = fx + 0.8 * np.sin(k * y + tt * 0.03) * np.cos(k * x - tt * 0.017)
        fy = fy + 0.8 * np.cos(k * x + tt * 0.023) * np.sin(k * y + tt * 0.013)
        # gentle outward push that grows with effort
        fx += (0.15 + 1.6 * e) * x / r * np.exp(-r * 1.8)
        fy += (0.15 + 1.6 * e) * y / r * np.exp(-r * 1.8)
        return np.column_stack([fx, fy])

    def update(_):
        nonlocal pos, vel, age, spin, effort_s, prev_effort, t, rings
        t += 1
        effort = env.feed(read_samples())
        effort_s += 0.22 * (effort - effort_s)

        if effort - prev_effort > 0.18 and not env.calibrating:
            rings.append([0.04, 0.5, 1.6])
        prev_effort = effort

        n = int(4 + effort_s * 300)
        theta = rng.uniform(0, 2 * np.pi, n)
        rad = rng.uniform(0.01, 0.05, n) ** 0.8
        dirs = np.column_stack([np.cos(theta), np.sin(theta)])
        pos = np.vstack([pos, dirs * rad[:, None]])
        vel = np.vstack([vel, dirs * (0.002 + 0.02 * effort_s)])
        age = np.concatenate([age, np.zeros(n)])
        spin = np.concatenate([spin, rng.choice([-1, 1], n)])

        if len(pos):
            f = flow(pos, t, effort_s)
            f[:, 0] *= np.where(spin > 0, 1.0, 0.85)   # two families of motion
            vel += f * (0.0012 + 0.0075 * effort_s)
            pos += vel
            vel *= 0.965
            age += 1
        alive = (age < LIFE) & (np.abs(pos) < 1.3).all(axis=1)
        pos, vel, age, spin = pos[alive], vel[alive], age[alive], spin[alive]
        if len(pos) > MAX_PARTICLES:
            pos, vel, age, spin = (a[-MAX_PARTICLES:] for a in (pos, vel, age, spin))

        life = 1 - age / LIFE
        if len(pos):
            # streak = short trail along velocity; longer & hotter with effort
            trail = 5 + 26 * effort_s
            segs = np.stack([pos - vel * trail, pos], axis=1)
            heat = np.clip(0.10 + 0.80 * life * (0.30 + 0.70 * min(effort_s, 1.0)), 0, 0.96)

            col = cmap(heat)
            col[:, 3] = np.clip(life, 0, 1) ** 0.7 * (0.55 + 0.4 * effort_s)
            streaks.set_segments(segs)
            streaks.set_color(np.clip(col, 0, 1))
            streaks.set_linewidth(0.5 + 0.9 * life * (0.4 + effort_s))

            gcol = cmap(np.clip(heat, 0, 0.9))
            gcol[:, 3] = 0.08 * np.clip(life, 0, 1) * (1 + 1.5 * effort_s)
            glow.set_segments(segs)
            glow.set_color(np.clip(gcol, 0, 1))
            glow.set_linewidth(2.5 + 5.0 * life * (0.4 + effort_s))
        else:
            streaks.set_segments([])
            glow.set_segments([])

        # core: thin pulsing ring, flares with effort
        breathe = 0.025 + 0.008 * np.sin(t * 0.06) + 0.12 * effort_s
        flare = cmap(0.45 + 0.5 * min(effort_s, 1.0))
        core_ring.set_radius(breathe)
        core_ring.set_linewidth(0.8 + 2.5 * effort_s)
        core_ring.set_edgecolor((flare[0], flare[1], flare[2], 0.25 + 0.5 * effort_s))

        while len(ring_artists) < len(rings):
            a = Circle((0, 0), 0.05, fill=False, lw=1.2, zorder=2)
            ax.add_patch(a)
            ring_artists.append(a)
        for r_state, art in zip(rings, ring_artists):
            r_state[0] += 0.04
            r_state[1] *= 0.90
            rc = cmap(0.8)
            art.set_radius(r_state[0])
            art.set_linewidth(r_state[2])
            art.set_edgecolor((rc[0], rc[1], rc[2], max(r_state[1], 0)))
        keep = [i for i, rs in enumerate(rings) if rs[1] > 0.02]
        for i, art in enumerate(ring_artists):
            if i >= len(rings) or i not in keep:
                art.set_edgecolor((0, 0, 0, 0))
        rings = [rings[i] for i in keep]

        meter.set_text(f"effort {min(effort, 1.5):4.2f}"
                       + ("  [calibrating]" if env.calibrating else ""))
        return streaks, glow, meter

    ani = FuncAnimation(fig, update, interval=FRAME_MS, blit=False,
                        cache_frame_data=False)
    plt.show()
    ser.close()


if __name__ == "__main__":
    main()
