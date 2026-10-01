"""PNG visuals drawn with Pillow (no numpy/matplotlib needed).

Two figures, both generated from real simulation output:
  * draw_mesh           - the mesh graph: green = online, red = offline,
                          orange dashed = highlighted route (e.g. SOS after reroute)
  * draw_delivery_chart - message outcomes + average latency by priority
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional

from PIL import Image, ImageDraw, ImageFont

from .mesh import MeshNetwork
from .report import DeliveryReport

GREEN = (34, 197, 94)
RED = (239, 68, 68)
ORANGE = (245, 158, 11)
BLUE = (59, 130, 246)
GRAY = (154, 164, 178)
LIGHT = (229, 231, 235)
DARK = (31, 41, 55)
WHITE = (255, 255, 255)
BG = (248, 250, 252)


def _font(size: int):
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _layout(nodes: List[str]) -> Dict[str, tuple[float, float]]:
    n = len(nodes)
    return {
        nid: (math.cos(2 * math.pi * i / max(n, 1) - math.pi / 2),
              math.sin(2 * math.pi * i / max(n, 1) - math.pi / 2))
        for i, nid in enumerate(nodes)
    }


def _dashed_line(draw: ImageDraw.ImageDraw, x1, y1, x2, y2,
                 fill, width: int = 3, dash: int = 12, gap: int = 8):
    length = math.hypot(x2 - x1, y2 - y1)
    if length == 0:
        return
    dx, dy = (x2 - x1) / length, (y2 - y1) / length
    d = 0.0
    while d < length:
        e = min(d + dash, length)
        draw.line([x1 + dx * d, y1 + dy * d, x1 + dx * e, y1 + dy * e],
                  fill=fill, width=width)
        d = e + gap


def draw_mesh(mesh: MeshNetwork,
              highlight_path: Optional[List[str]] = None,
              out_path: str | Path = "mesh_graph.png",
              title: str = "DisasterRelay mesh network",
              offline: Optional[set] = None) -> str:
    """Render the mesh. `offline` forces nodes to draw red (e.g. an outage
    snapshot) regardless of their current liveness."""
    size = 720
    img = Image.new("RGB", (size, size), BG)
    draw = ImageDraw.Draw(img)
    nodes = mesh.nodes
    offline = offline or set()
    unit = _layout(nodes)
    pos = {nid: (size / 2 + x * size * 0.33, size / 2 + y * size * 0.33)
           for nid, (x, y) in unit.items()}
    highlight_path = highlight_path or []
    hot = set(zip(highlight_path, highlight_path[1:]))

    draw.text((size / 2, 28), title, fill=DARK, font=_font(22), anchor="ma")

    drawn = set()
    for a in nodes:
        for b in mesh.neighbors(a, alive_only=False):
            if (b, a) in drawn:
                continue
            drawn.add((a, b))
            x1, y1 = pos[a]
            x2, y2 = pos[b]
            if (a, b) in hot or (b, a) in hot:
                _dashed_line(draw, x1, y1, x2, y2, ORANGE, width=4)
            elif a in offline or b in offline:
                draw.line([x1, y1, x2, y2], fill=LIGHT, width=2)
            elif not mesh.is_alive(a) or not mesh.is_alive(b):
                draw.line([x1, y1, x2, y2], fill=LIGHT, width=2)
            else:
                draw.line([x1, y1, x2, y2], fill=GRAY, width=3)

    r = 44
    for nid in nodes:
        x, y = pos[nid]
        alive = mesh.is_alive(nid) and nid not in offline
        color = GREEN if alive else RED
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color, outline=WHITE,
                     width=4)
        draw.text((x, y - 6), nid, fill=WHITE, font=_font(26), anchor="mm")
        status = "online" if alive else "OFFLINE"
        draw.text((x, y + r + 16), status, fill=DARK, font=_font(15), anchor="ma")

    # legend
    lx, ly = 24, size - 96
    for i, (label, color) in enumerate(
            [("online node", GREEN), ("offline node", RED),
             ("SOS route (rerouted)", ORANGE)]):
        y = ly + i * 26
        draw.rectangle([lx, y - 8, lx + 26, y + 8], fill=color)
        draw.text((lx + 34, y), label, fill=DARK, font=_font(14), anchor="lm")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return str(out_path)


def _bars(draw: ImageDraw.ImageDraw, origin_x: int, origin_y: int,
          width: int, height: int, labels: List[str], values: List[float],
          colors: List[tuple], title: str, ylabel: str):
    draw.text((origin_x + width / 2, origin_y - height - 28), title, fill=DARK,
              font=_font(17), anchor="mm")
    draw.line([origin_x, origin_y, origin_x + width, origin_y], fill=DARK, width=2)
    draw.line([origin_x, origin_y - height, origin_x, origin_y], fill=DARK, width=2)
    vmax = max(values) if values and max(values) > 0 else 1
    n = len(labels)
    slot = width / n
    bw = min(90, slot * 0.55)
    for i, (label, val, color) in enumerate(zip(labels, values, colors)):
        cx = origin_x + slot * (i + 0.5)
        bh = (val / vmax) * (height - 30)
        draw.rectangle([cx - bw / 2, origin_y - bh, cx + bw / 2, origin_y],
                       fill=color, outline=WHITE, width=2)
        txt = f"{val:.1f}" if isinstance(val, float) else str(val)
        draw.text((cx, origin_y - bh - 14), txt, fill=DARK, font=_font(16),
                  anchor="mm")
        draw.text((cx, origin_y + 18), label, fill=DARK, font=_font(15),
                  anchor="ma")
    draw.text((origin_x - 14, origin_y - height / 2), ylabel, fill=DARK,
              font=_font(14), anchor="mm")


def draw_delivery_chart(report: DeliveryReport,
                        out_path: str | Path = "delivery_chart.png") -> str:
    s = report.summary()
    W, H = 1120, 480
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw.text((W / 2, 30), "DisasterRelay delivery report", fill=DARK,
              font=_font(24), anchor="ma")

    _bars(draw, 90, 380, 420, 260,
          ["Delivered", "Pending", "Dropped"],
          [s["delivered"], s["pending"], s["dropped"]],
          [GREEN, ORANGE, RED],
          "Message outcomes", "messages")

    lat_by_prio: Dict[str, List[int]] = {}
    for r in report.sim.delivered:
        lat_by_prio.setdefault(r.priority, []).append(r.latency_ticks)
    order = [p for p in ("SOS", "MEDICAL", "INFO") if p in lat_by_prio]
    avgs = [sum(lat_by_prio[p]) / len(lat_by_prio[p]) for p in order]
    pcolors = {"SOS": RED, "MEDICAL": ORANGE, "INFO": BLUE}
    _bars(draw, 620, 380, 420, 260, order, avgs,
          [pcolors[p] for p in order],
          "Avg latency by priority", "ticks")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return str(out_path)
