#!/usr/bin/env python3
"""Clench-reactive particle burst — visual demo for the EMG rig.

Rest: deep-violet embers drifting and swirling around a faintly breathing
core. Clench: the core flares, a shockwave ring fires, and a storm of
hot particles spirals outward — density, speed and colour all scale with
effort.

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
from matplotlib.patches import Circle

BAUD = 115200
MAX_PARTICLES = 2600
FRAME_MS = 33
LIFE = 100  # frames


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
            self.level += 0.25 * (burst - self.level)
        if self.calibrating > 0:
            self.calibrating -= 1
            self.floor += 0.1 * (self.level * 1.5 + 10 - self.floor)
        elif self.level < self.floor * 1.2:
            self.floor += 0.005 * (self.level * 1.5 + 10 - self.floor)
        effort = (self.level - self.floor) / max(self.floor * 6, 40.0)
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
    spin = np.zeros(0)          # per-particle swirl direction/strength

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

    # vignette background: deep indigo center fading to black
    yy, xx = np.mgrid[-1:1:240j, -1:1:240j]
    r = np.sqrt(xx**2 + yy**2)
    bg = np.zeros((240, 240, 3))
    glowc = np.array([0.10, 0.06, 0.22])
    bg += glowc * np.clip(1 - r, 0, 1)[..., None] ** 2.2
    ax.imshow(bg, extent=[-1, 1, -1, 1], zorder=0, interpolation="bilinear")

    halo = ax.scatter([], [], s=[], lw=0, zorder=2)   # soft glow layer
    core = ax.scatter([], [], s=[], lw=0, zorder=3)   # bright centers

    # breathing core: three concentric translucent discs
    core_discs = [Circle((0, 0), 0.02, color=(0.7, 0.5, 1.0, a), lw=0, zorder=1)
                  for a in (0.10, 0.06, 0.03)]
    for c in core_discs:
        ax.add_patch(c)

    rings = []  # [radius, alpha, width] shockwaves
    ring_artists = []

    meter = ax.text(0.02, 0.02, "", transform=ax.transAxes,
                    color="#3a3a4a", fontsize=9, family="monospace", zorder=5)

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

    def update(_):
        nonlocal pos, vel, age, spin, effort_s, prev_effort, t, rings
        t += 1
        effort = env.feed(read_samples())
        effort_s += 0.18 * (effort - effort_s)

        # shockwave on sharp onset
        if effort - prev_effort > 0.28 and not env.calibrating:
            rings.append([0.05, 0.55, 2.5 + 2 * effort])
        prev_effort = effort

        # spawn
        n = int(2 + effort_s * 240)
        theta = rng.uniform(0, 2 * np.pi, n)
        speed = (0.003 + 0.052 * effort_s) * rng.uniform(0.25, 1.0, n) ** 0.7
        dirs = np.column_stack([np.cos(theta), np.sin(theta)])
        pos = np.vstack([pos, dirs * rng.uniform(0.01, 0.04, n)[:, None]])
        vel = np.vstack([vel, dirs * speed[:, None]])
        age = np.concatenate([age, np.zeros(n)])
        spin = np.concatenate([spin, rng.choice([-1, 1], n) * rng.uniform(0.2, 1.0, n)])

        # physics: drift, swirl, gentle slow-down
        if len(pos):
            perp = np.column_stack([-pos[:, 1], pos[:, 0]])
            norm = np.linalg.norm(pos, axis=1, keepdims=True) + 1e-6
            vel += perp / norm * spin[:, None] * 0.0009 * (1 + 2 * effort_s)
            pos += vel
            vel *= 0.986
            age += 1
        alive = (age < LIFE) & (np.abs(pos) < 1.25).all(axis=1)
        pos, vel, age, spin = pos[alive], vel[alive], age[alive], spin[alive]
        if len(pos) > MAX_PARTICLES:
            pos, vel, age, spin = (a[-MAX_PARTICLES:] for a in (pos, vel, age, spin))

        life = 1 - age / LIFE
        heat = np.clip(0.12 + 0.75 * life * (0.30 + 0.70 * min(effort_s, 1.0)), 0, 0.96)

        offs = pos if len(pos) else np.zeros((0, 2))
        # halo: big, soft, translucent
        hcol = cmap(heat)
        hcol[:, 3] = 0.10 * np.clip(life, 0, 1) ** 1.5 * (1 + effort_s)
        halo.set_offsets(offs)
        halo.set_sizes(60 + 240 * life * (0.25 + effort_s))
        halo.set_facecolor(np.clip(hcol, 0, 1))
        # core: small, bright
        ccol = cmap(np.clip(heat + 0.18, 0, 0.98))
        ccol[:, 3] = np.clip(life, 0, 1) ** 0.8
        core.set_offsets(offs)
        core.set_sizes(2.5 + 13 * life * (0.35 + 0.8 * effort_s))
        core.set_facecolor(np.clip(ccol, 0, 1))

        # breathing core: slow idle pulse + effort flare
        breathe = 0.016 + 0.006 * np.sin(t * 0.06) + 0.10 * effort_s
        flare = cmap(0.35 + 0.6 * min(effort_s, 1.0))
        for i, c in enumerate(core_discs):
            c.set_radius(breathe * (1 + 0.9 * i))
            c.set_color((flare[0], flare[1], flare[2], (0.14, 0.07, 0.035)[i] * (0.5 + effort_s)))

        # shockwave rings
        while len(ring_artists) < len(rings):
            a = Circle((0, 0), 0.05, fill=False, lw=2, zorder=2)
            ax.add_patch(a)
            ring_artists.append(a)
        for r_state, art in zip(rings, ring_artists):
            r_state[0] += 0.035
            r_state[1] *= 0.90
            rc = cmap(0.75)
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
        return halo, core, meter

    ani = FuncAnimation(fig, update, interval=FRAME_MS, blit=False,
                        cache_frame_data=False)
    plt.show()
    ser.close()


if __name__ == "__main__":
    main()
