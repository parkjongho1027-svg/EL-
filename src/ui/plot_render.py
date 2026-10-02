"""단일 운행 및 전기에너지 비교 그래프를 PNG와 Tk에 동일하게 그린다."""

from pathlib import Path
import math
from PIL import Image, ImageDraw, ImageFont, ImageTk

from src.ui.phase_annotations import PHASE_ENGLISH, phase_segments


def _font(size):
    candidates = (
        Path("C:/Windows/Fonts/malgun.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    )
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def render_plot(profile, palette, reference=None, size=(820, 270), scale=2):
    """표시 높이에 맞춘 눈금과 시간별 곡선을 화면 및 PNG에 그린다."""
    width, height = size
    if width < 360 or height < 200:
        raise ValueError("그래프 크기는 360×200 이상이어야 합니다.")
    W, H = width * scale, height * scale
    background = palette.get("surface", "#ffffff")
    text = palette.get("text", "#222222")
    grid = "#555b68" if palette.get("background") == "#000000" else "#dce2e9"
    axis = "#aaaaaa" if palette.get("background") == "#000000" else "#aab4bf"
    image = Image.new("RGB", (W, H), background)
    d = ImageDraw.Draw(image)
    f = _font(10 * scale)
    title_font = _font(11 * scale)
    has_korean_font = bytes(f.getmask("가")) != bytes(f.getmask("나"))
    left, right = 75 * scale, (width - 20) * scale
    profiles = (
        (("Reference", reference, "#4d9aff"), ("Candidate", profile, "#f3a450"))
        if reference
        else (("Curve", profile, palette.get("accent", "#2879cc")),)
    )
    duration = max(p["duration_s"] for _, p, _ in profiles)
    if duration <= 0:
        raise ValueError("운행시간이 0보다 커야 합니다.")

    def nice_step(raw):
        if raw <= 0:
            return 1.0
        power = 10 ** math.floor(math.log10(raw))
        for number in (1, 2, 2.5, 5, 10):
            if number * power >= raw:
                return number * power
        return 10 * power

    time_step = nice_step(duration / 4)
    time_max = math.ceil(duration / time_step) * time_step
    electrical = reference is not None or "grid_kw_samples" in profile
    phases = phase_segments(profile) if not electrical else ()

    def series(p, key):
        if key == "speed":
            return [sample[2] for sample in p["samples"]]
        return p["grid_kw_samples"] if electrical else p["signed_mechanical_kw_samples"]

    speed_bottom = round(height * 0.46)
    power_top = max(speed_bottom + 35, round(height * 0.62))
    bands = (
        (50 * scale, speed_bottom * scale, "Speed (m/s)", "speed"),
        (
            power_top * scale,
            (height - 32) * scale,
            "Grid power (kW)" if electrical else "Mechanical power (kW)",
            "power",
        ),
    )
    for top, bottom, label, key in bands:
        arrays = [series(p, key) for _, p, _ in profiles]
        observed_low = min(0.0, *(min(a) for a in arrays))
        observed_high = max(0.0, *(max(a) for a in arrays))
        if observed_high - observed_low < 1e-9:
            observed_high = observed_low + 1
        step = nice_step((observed_high - observed_low) / 2)
        low = (
            0.0
            if key == "speed"
            else math.floor((observed_low - step * 0.05) / step) * step
        )
        high = math.ceil((observed_high + step * 0.05) / step) * step
        tick_count = 3 if (bottom - top) / scale < 100 else 5
        d.text((left, top - 22 * scale), label, fill=text, font=title_font)
        for j in range(tick_count):
            value = low + (high - low) * j / (tick_count - 1)
            y = bottom - (bottom - top) * j / (tick_count - 1)
            d.line((left, y, right, y), fill=grid, width=scale)
            increment = (high - low) / (tick_count - 1)
            decimals = 2 if increment < 0.1 else 1 if increment < 1 else 0
            txt = f"{value:.{decimals}f}"
            box = d.textbbox((0, 0), txt, font=f)
            d.text(
                (
                    left - 7 * scale - (box[2] - box[0]),
                    y - (box[3] - box[1]) / 2 - 2 * scale,
                ),
                txt,
                fill=text,
                font=f,
            )
        for j in range(round(time_max / time_step) + 1):
            tick = time_step * j
            x = left + (right - left) * tick / time_max
            d.line((x, top, x, bottom), fill=grid, width=max(1, scale // 2))
            if key == "power":
                txt = f"{tick:g}"
                box = d.textbbox((0, 0), txt, font=f)
                d.text(
                    (x - (box[2] - box[0]) / 2, bottom + 3 * scale),
                    txt,
                    fill=text,
                    font=f,
                )
        if phases:
            separator = "#8797a8" if palette.get("background") == "#000000" else "#a4adb7"
            for _number, _name, start, _end in phases[1:]:
                x = left + (right - left) * start / time_max
                for y in range(int(top), int(bottom), 7 * scale):
                    d.line((x, y, x, min(bottom, y + 3 * scale)),
                           fill=separator, width=max(1, scale // 2))
        for name, p, color in profiles:
            values = series(p, key)
            stride = max(1, math.ceil((len(values) - 1) / 1499))
            indices = list(range(0, len(values), stride))
            if indices[-1] != len(values) - 1:
                indices.append(len(values) - 1)
            coords = [
                (
                    left + (right - left) * p["samples"][i][0] / time_max,
                    bottom - (bottom - top) * (values[i] - low) / (high - low),
                )
                for i in indices
            ]
            if len(coords) > 1:
                d.line(coords, fill=color, width=2 * scale, joint="curve")
    if phases:
        # 단계 명칭은 UI의 별도 '구간 안내'에 표시한다. 그래프에는 번호만 남긴다.
        for number, _name, _start, _end in phases:
            midpoint = (_start + _end) / 2
            if (right - left) * (_end - _start) / time_max >= 13 * scale:
                tick_x = left + (right - left) * midpoint / time_max
                d.text((tick_x - 3 * scale, 52 * scale), str(number),
                       fill=text, font=f)
    d.text((right - 56 * scale, H - 14 * scale), "Time (s)", fill=text, font=f)
    if reference:
        for index, (name, _, color) in enumerate(profiles):
            x = left + (index * 125) * scale
            d.line(
                (x, 8 * scale, x + 18 * scale, 8 * scale), fill=color, width=3 * scale
            )
            d.text((x + 23 * scale, 2 * scale), name, fill=text, font=f)
    return image


def draw_on_canvas(canvas, profile, palette, reference=None):
    canvas.delete("all")
    if not profile or (reference is None and not profile):
        return
    width = max(360, min(1800, canvas.winfo_width() - 4))
    height = max(200, min(750, canvas.winfo_height() - 4))
    image = render_plot(profile, palette, reference, (width, height), scale=2)
    photo = ImageTk.PhotoImage(
        image.resize((width, height), Image.Resampling.LANCZOS), master=canvas
    )
    canvas._plot_photo = photo
    canvas.create_image(
        canvas.winfo_width() / 2, canvas.winfo_height() / 2, image=photo
    )
