"""Pillow 없이 PNG를 만드는 작은 그래프 렌더러 (표준 라이브러리 전용)."""

import math
import struct
import zlib

# 파일 저장에 필요한 영문·숫자 5×7 비트맵 글꼴. 화면 글꼴은 Tk가 담당한다.
FONT = {
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01111", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "11110"),
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00010", "00010", "00010", "10010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    ".": ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    "/": ("00001", "00001", "00010", "00100", "01000", "10000", "10000"),
    "(": ("00010", "00100", "01000", "01000", "01000", "00100", "00010"),
    ")": ("01000", "00100", "00010", "00010", "00010", "00100", "01000"),
    ":": ("00000", "01100", "01100", "00000", "01100", "01100", "00000"),
    " ": ("00000",) * 7,
}


def _rgb(value):
    if not isinstance(value, str) or len(value) != 7 or value[0] != "#":
        return (40, 40, 40)
    try:
        return tuple(int(value[i : i + 2], 16) for i in (1, 3, 5))
    except ValueError:
        return (40, 40, 40)


def render_png(profile, palette, reference=None, size=(1100, 440), axes=None,
               comparisons=None):
    """축·보조선·곡선을 PNG 바이트로 반환한다. Pillow/Ghostscript 불필요."""
    w, h = size
    if w < 360 or h < 200:
        raise ValueError("그래프 크기는 360×200 이상이어야 합니다.")
    bg = _rgb(palette.get("surface", "#ffffff"))
    ink = _rgb(palette.get("text", "#222222"))
    grid = _rgb("#596171" if palette.get("background") == "#000000" else "#dce2e9")
    pixels = bytearray(bytes(bg) * (w * h))

    def dot(x, y, color, thickness=1):
        x = int(round(x))
        y = int(round(y))
        for dy in range(-(thickness // 2), thickness - thickness // 2):
            yy = y + dy
            if yy < 0 or yy >= h:
                continue
            for dx in range(-(thickness // 2), thickness - thickness // 2):
                xx = x + dx
                if 0 <= xx < w:
                    i = (yy * w + xx) * 3
                    pixels[i : i + 3] = bytes(color)

    def line(a, b, color, thickness=1):
        x0, y0 = a
        x1, y1 = b
        steps = max(1, int(max(abs(x1 - x0), abs(y1 - y0))))
        for j in range(steps + 1):
            t = j / steps
            dot(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, color, thickness)

    def label(text, x, y, color=ink, mult=2):
        for char in text.upper():
            glyph = FONT.get(char, FONT[" "])
            for row, bits in enumerate(glyph):
                for col, pixel in enumerate(bits):
                    if pixel == "1":
                        for dx in range(mult):
                            for dy in range(mult):
                                dot(x + col * mult + dx, y + row * mult + dy, color)
            x += 6 * mult

    def step(raw):
        unit = 10 ** math.floor(math.log10(max(raw, 1e-12)))
        for n in (1, 2, 2.5, 5, 10):
            if n * unit >= raw:
                return n * unit
        return 10 * unit

    def plot_points(samples, values):
        """적분에 사용한 원본을 유지하면서 화면용 선분만 최대 1,500개로 줄인다."""
        stride = max(1, math.ceil((len(samples) - 1) / 1499))
        indices = list(range(0, len(samples), stride))
        if indices[-1] != len(samples) - 1:
            indices.append(len(samples) - 1)
        return ((samples[i], values[i]) for i in indices)

    profiles = (
        tuple((str(index + 1), sample, _rgb(color))
              for index, (sample, color) in enumerate(comparisons))
        if comparisons is not None else
        (
            ("REFERENCE", reference, _rgb("#4d9aff")),
            ("CANDIDATE", profile, _rgb("#f3a450")),
        )
        if reference
        else (("CURVE", profile, _rgb(palette.get("accent", "#2879cc"))),)
    )
    duration = max(p["duration_s"] for _, p, _ in profiles)
    ts = axes["x_step"] if axes else step(duration / 4)
    tmax = axes["x_max"] if axes else math.ceil(duration / ts) * ts
    left, right = 85, w - 22
    electrical = reference is not None or "grid_kw_samples" in profile
    speed_bottom = round(h * 0.46)
    power_top = max(speed_bottom + 35, round(h * 0.62))
    for key, top, bottom, title in (
        ("speed", 50, speed_bottom, "SPEED (M/S)"),
        (
            "power",
            power_top,
            h - 32,
            "GRID POWER (KW)" if electrical else "MECHANICAL POWER (KW)",
        ),
    ):
        values = []
        for _, p, _ in profiles:
            values.append(
                [row[2] for row in p["samples"]]
                if key == "speed"
                else p["grid_kw_samples"]
                if electrical
                else p["signed_mechanical_kw_samples"]
            )
        lo = min(0.0, *(min(v) for v in values))
        hi = max(0.0, *(max(v) for v in values))
        if hi - lo < 1e-9:
            hi = lo + 1
        dy = step((hi - lo) / 2)
        lo = 0 if key == "speed" else math.floor((lo - dy * 0.05) / dy) * dy
        hi = math.ceil((hi + dy * 0.05) / dy) * dy
        if axes:
            lo, hi, dy = (
                (0, axes["speed_max"], axes["speed_step"])
                if key == "speed"
                else (axes["power_min"], axes["power_max"], axes["power_step"])
            )
        label(title, left, top - 22)
        tick_count = (
            round((hi - lo) / dy) + 1 if axes else (3 if bottom - top < 100 else 5)
        )
        for i in range(tick_count):
            v = lo + i * dy if axes else lo + (hi - lo) * i / (tick_count - 1)
            y = bottom - (bottom - top) * (v - lo) / (hi - lo)
            line((left, y), (right, y), grid)
            increment = (hi - lo) / (tick_count - 1)
            num = (
                f"{v:.2f}"
                if increment < 0.1
                else f"{v:.1f}"
                if increment < 1
                else f"{v:g}"
            )
            label(num, left - len(num) * 12 - 9, y - 7, mult=2)
        for i in range(round(tmax / ts) + 1):
            t = i * ts
            x = left + (right - left) * t / tmax
            line((x, top), (x, bottom), grid)
            if key == "power":
                num = f"{t:g}"
                label(num, x - len(num) * 6, bottom + 3, mult=2)
        for (_, p, color), vlist in zip(profiles, values):
            previous = None
            for sample, value in plot_points(p["samples"], vlist):
                point = (
                    left + (right - left) * sample[0] / tmax,
                    bottom - (bottom - top) * (value - lo) / (hi - lo),
                )
                if previous is not None:
                    line(previous, point, color, 2)
                previous = point
    label("TIME (S)", right - 100, h - 14)
    if comparisons is not None:
        for index, (_, _, color) in enumerate(profiles):
            label(str(index + 1), left + index % 12 * 40, 5, color)
    elif reference:
        label("REFERENCE", left, 5, profiles[0][2])
        label("CANDIDATE", left + 160, 5, profiles[1][2])
    raw = b"".join(b"\x00" + pixels[y * w * 3 : (y + 1) * w * 3] for y in range(h))

    def chunk(kind, data):
        return (
            struct.pack("!I", len(data))
            + kind
            + data
            + struct.pack("!I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack("!2I5B", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


def stack_pngs(images):
    """Vertically join RGB PNGs from the internal renderer with no image dependency."""
    if not images:
        raise ValueError("저장할 그래프가 없습니다.")
    width = None
    rows = []
    for image in images:
        if not image.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("PNG 데이터가 올바르지 않습니다.")
        offset, compressed = 8, bytearray()
        while offset < len(image):
            length = struct.unpack_from("!I", image, offset)[0]
            kind = image[offset + 4:offset + 8]
            value = image[offset + 8:offset + 8 + length]
            if kind == b"IHDR":
                w, h, depth, color, compression, filtering, interlace = struct.unpack("!2I5B", value)
                if (depth, color, compression, filtering, interlace) != (8, 2, 0, 0, 0) or (width is not None and w != width):
                    raise ValueError("비교 PNG는 동일한 가로 크기의 RGB여야 합니다.")
                width = w
            elif kind == b"IDAT":
                compressed.extend(value)
            offset += length + 12
        raw = zlib.decompress(compressed)
        if len(raw) != h * (1 + 3 * width) or any(raw[i * (1 + 3 * width)] != 0 for i in range(h)):
            raise ValueError("비교 PNG의 이미지 데이터가 올바르지 않습니다.")
        rows.append(raw)
    output = b"".join(rows)
    height = sum(len(raw) // (1 + 3 * width) for raw in rows)

    def chunk(kind, data):
        return (struct.pack("!I", len(data)) + kind + data
                + struct.pack("!I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack("!2I5B", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(output, 6)) + chunk(b"IEND", b""))
