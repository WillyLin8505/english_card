"""Build launcher icons and launch logos from the existing card glyph.

Source shape: app/assets/figma/mobile/tab_cards_active.svg (stacked cards).
Colour: MColors.primary #4A90D9 in app/lib/theme/mobile_theme.dart.
Launch backdrop: MColors.canvas #F7F9FC.

Run from the repo root: python app/tools/make_app_icon.py
"""
from __future__ import annotations

import hashlib
import shutil
import struct
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "app"
BACKUP = ROOT / "lexicon" / "logs" / "agents" / "card257_icon_backup"

PRIMARY = (0x4A, 0x90, 0xD9, 255)
CANVAS = (0xF7, 0xF9, 0xFC, 255)
WHITE = (255, 255, 255, 255)
BACK = (255, 255, 255, 210)

# Paths that this card replaces. Backed up once, relative to app/.
REPLACE = [
    "ios/Runner/Assets.xcassets/AppIcon.appiconset",
    "ios/Runner/Assets.xcassets/LaunchImage.imageset",
    "macos/Runner/Assets.xcassets/AppIcon.appiconset",
    "android/app/src/main/res/mipmap-mdpi/ic_launcher.png",
    "android/app/src/main/res/mipmap-hdpi/ic_launcher.png",
    "android/app/src/main/res/mipmap-xhdpi/ic_launcher.png",
    "android/app/src/main/res/mipmap-xxhdpi/ic_launcher.png",
    "android/app/src/main/res/mipmap-xxxhdpi/ic_launcher.png",
    "android/app/src/main/res/drawable/launch_background.xml",
    "android/app/src/main/res/drawable-v21/launch_background.xml",
    "web/favicon.png",
    "web/icons/Icon-192.png",
    "web/icons/Icon-512.png",
    "web/icons/Icon-maskable-192.png",
    "web/icons/Icon-maskable-512.png",
    "web/manifest.json",
    "web/index.html",
    "windows/runner/resources/app_icon.ico",
    "ios/Runner/Base.lproj/LaunchScreen.storyboard",
]


def backup_once() -> None:
    if BACKUP.exists():
        return
    for rel in REPLACE:
        src = APP / rel
        if not src.exists():
            continue
        dest = BACKUP / rel
        if src.is_dir():
            shutil.copytree(src, dest)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)


def _supersample(size: int) -> int:
    if size < 64:
        return 8
    if size < 256:
        return 4
    return 2


def render(size: int, *, tile: bool) -> Image.Image:
    """Full-bleed icon (tile=False) or rounded launch mark on transparent."""
    ss = _supersample(size)
    side = size * ss
    image = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if tile:
        radius = int(round(side * 0.2237))
        draw.rounded_rectangle((0, 0, side - 1, side - 1), radius=radius, fill=PRIMARY)
    else:
        draw.rectangle((0, 0, side, side), fill=PRIMARY)

    box = side * 0.54
    origin = (side - box) / 2
    scale = box / 22.0

    def pt(x: float, y: float) -> tuple[float, float]:
        return (origin + x * scale, origin + y * scale)

    def rounded(x: float, y: float, w: float, h: float, rx: float, **kwargs) -> None:
        x0, y0 = pt(x, y)
        x1, y1 = pt(x + w, y + h)
        draw.rounded_rectangle((x0, y0, x1, y1), radius=rx * scale, **kwargs)

    def hbar(x0: float, x1: float, y: float, stroke: float, fill) -> None:
        half = stroke * scale / 2
        ax, ay = pt(x0, y)
        bx, _ = pt(x1, y)
        draw.rounded_rectangle(
            (ax, ay - half, bx, ay + half), radius=half, fill=fill
        )

    # Back card, then a solid front card covering the overlap (tab_cards glyph).
    rounded(6.42, 2.75, 12.83, 12.83, 1.83, fill=BACK)
    rounded(2.75, 6.42, 12.83, 12.83, 2.0, fill=WHITE)
    hbar(6.42, 11.92, 11.0, 1.7, PRIMARY)
    hbar(6.42, 9.17, 14.67, 1.7, PRIMARY)

    out = image.resize((size, size), Image.Resampling.LANCZOS)
    if tile:
        return out
    return out.convert("RGB")


def save_png(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True)


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise SystemExit(f"not a png: {path}")
    return struct.unpack(">II", data[16:24])


def main() -> None:
    backup_once()
    master = render(1024, tile=False)
    save_png(master, APP / "assets" / "brand" / "app_icon_1024.png")

    ios_dir = APP / "ios/Runner/Assets.xcassets/AppIcon.appiconset"
    ios_px = {
        "Icon-App-20x20@1x.png": 20,
        "Icon-App-20x20@2x.png": 40,
        "Icon-App-20x20@3x.png": 60,
        "Icon-App-29x29@1x.png": 29,
        "Icon-App-29x29@2x.png": 58,
        "Icon-App-29x29@3x.png": 87,
        "Icon-App-40x40@1x.png": 40,
        "Icon-App-40x40@2x.png": 80,
        "Icon-App-40x40@3x.png": 120,
        "Icon-App-60x60@2x.png": 120,
        "Icon-App-60x60@3x.png": 180,
        "Icon-App-76x76@1x.png": 76,
        "Icon-App-76x76@2x.png": 152,
        "Icon-App-83.5x83.5@2x.png": 167,
        "Icon-App-1024x1024@1x.png": 1024,
    }
    for name, px in ios_px.items():
        save_png(render(px, tile=False), ios_dir / name)

    launch_dir = APP / "ios/Runner/Assets.xcassets/LaunchImage.imageset"
    for name, px in (
        ("LaunchImage.png", 168),
        ("LaunchImage@2x.png", 336),
        ("LaunchImage@3x.png", 504),
    ):
        save_png(render(px, tile=True), launch_dir / name)

    android_px = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
    for density, px in android_px.items():
        save_png(
            render(px, tile=False),
            APP / f"android/app/src/main/res/mipmap-{density}/ic_launcher.png",
        )
    launch_dp = {"mdpi": 144, "hdpi": 216, "xhdpi": 288, "xxhdpi": 432, "xxxhdpi": 576}
    for density, px in launch_dp.items():
        save_png(
            render(px, tile=True),
            APP / f"android/app/src/main/res/drawable-{density}/launch_logo.png",
        )

    mac_dir = APP / "macos/Runner/Assets.xcassets/AppIcon.appiconset"
    for px in (16, 32, 64, 128, 256, 512, 1024):
        save_png(render(px, tile=False), mac_dir / f"app_icon_{px}.png")

    web_icons = APP / "web/icons"
    for px, names in (
        (192, ("Icon-192.png", "Icon-maskable-192.png")),
        (512, ("Icon-512.png", "Icon-maskable-512.png")),
    ):
        image = render(px, tile=False)
        for name in names:
            save_png(image, web_icons / name)
    save_png(render(32, tile=False), APP / "web/favicon.png")

    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    ico_path = APP / "windows/runner/resources/app_icon.ico"
    render(256, tile=False).save(
        ico_path,
        format="ICO",
        sizes=[(px, px) for px in ico_sizes],
    )

    marketing = ios_dir / "Icon-App-1024x1024@1x.png"
    digest = hashlib.md5(marketing.read_bytes()).hexdigest()
    flutter_template = "c785f8932297af4acd5f5ccb7630f01c"
    if digest == flutter_template:
        raise SystemExit("1024 icon still matches the Flutter template")
    width, height = png_size(launch_dir / "LaunchImage.png")
    if (width, height) == (1, 1):
        raise SystemExit("LaunchImage is still 1x1")
    if Image.open(marketing).mode != "RGB":
        raise SystemExit(f"marketing icon mode {Image.open(marketing).mode}, want RGB")
    print(f"master md5 {digest}")
    print(f"launch {width}x{height} @1x, @2x {png_size(launch_dir / 'LaunchImage@2x.png')}, @3x {png_size(launch_dir / 'LaunchImage@3x.png')}")
    print(f"backup {BACKUP}")


if __name__ == "__main__":
    main()
