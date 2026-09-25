"""Export the rope tension and capacity charts as PNG without Pillow."""

import math
import struct
import zlib

from src.ui.native_plot import FONT
from src.ui.graph_axes import axes_for_graphs


def export_chart_png(kind, values, *, width=1100, height=580, axes=None):
    if kind not in ("traction", "traffic"):
        raise ValueError("지원하지 않는 그래프입니다.")
    if not 400 <= width <= 3000 or not 250 <= height <= 2000 or not values:
        raise ValueError("그래프 크기 또는 데이터가 올바르지 않습니다.")
    white = (255, 255, 255)
    grid = (226, 232, 237)
    blue = (40, 121, 204)
    orange = (211, 122, 40)
    black = (35, 40, 48)
    pixels = bytearray(bytes(white) * (width * height))

    def dot(x, y, color, size=1):
        x, y = round(x), round(y)
        for dy in range(size):
            for dx in range(size):
                if 0 <= x + dx < width and 0 <= y + dy < height:
                    index = ((y + dy) * width + x + dx) * 3
                    pixels[index : index + 3] = bytes(color)

    def line(x0, y0, x1, y1, color, size=1):
        steps = max(1, math.ceil(max(abs(x1 - x0), abs(y1 - y0))))
        for j in range(steps + 1):
            ratio = j / steps
            dot(x0 + (x1 - x0) * ratio, y0 + (y1 - y0) * ratio, color, size)

    def text(string, x, y, color=black, scale=2):
        for character in string.upper():
            glyph = FONT.get(character, FONT[" "])
            for row, bits in enumerate(glyph):
                for col, bit in enumerate(bits):
                    if bit == "1":
                        dot(x + col * scale, y + row * scale, color, scale)
            x += 6 * scale

    left, right, top, bottom = 90, width - 40, 70, height - 65
    axes = axes or axes_for_graphs(
        kind, [values if kind == "traction" else {"per_floor": values}]
    )
    maximum, distance = axes["y_max"], axes["x_max"]
    if kind == "traction":
        text("ROPE TENSION (N / ROPE)", left, 22)
        text("CAR", left + 450, 22, blue)
        text("COUNTERWEIGHT", left + 520, 22, orange)
    else:
        text("FIVE MINUTE CAPACITY (PASSENGERS / FLOOR)", left, 22)

    for tick in range(round(maximum / axes["y_step"]) + 1):
        value = tick * axes["y_step"]
        y = bottom - (bottom - top) * value / maximum
        line(left, y, right, y, grid)
        text(f"{value:g}", 10, y - 7)
    for tick in range(round(distance / axes["x_step"]) + 1):
        value = tick * axes["x_step"]
        x = left + (right - left) * value / distance
        line(x, top, x, bottom, grid)
        text(f"{value + (2 if kind == 'traffic' else 0):g}", x - 10, bottom + 10)
    if kind == "traction":
        for col, color in ((1, blue), (2, orange)):
            for previous, current in zip(values, values[1:]):
                line(
                    left + (right - left) * previous[0] / distance,
                    bottom - (bottom - top) * previous[col] / maximum,
                    left + (right - left) * current[0] / distance,
                    bottom - (bottom - top) * current[col] / maximum,
                    color,
                    2,
                )
        text("POSITION (M)", right - 160, height - 23)
    else:
        width_per_bar = (right - left) / distance
        for index, count in enumerate(values):
            x0 = left + index * width_per_bar + 2
            x1 = min(right - 1, left + (index + 1) * width_per_bar - 2)
            y0 = bottom - (bottom - top) * count / maximum
            for x in range(round(x0), max(round(x0) + 1, round(x1))):
                line(x, y0, x, bottom, blue)
        text("DESTINATION FLOOR", right - 220, height - 23)
    raw = b"".join(
        b"\x00" + pixels[y * width * 3 : (y + 1) * width * 3] for y in range(height)
    )

    def chunk(tag, body):
        return (
            struct.pack("!I", len(body))
            + tag
            + body
            + struct.pack("!I", zlib.crc32(tag + body) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack("!2I5B", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )
