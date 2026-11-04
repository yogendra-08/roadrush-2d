"""PhotoImage cache: loads PNGs from ``assets/`` (rebuilding missing ones with procart)."""
from __future__ import annotations

from PIL import Image, ImageTk

from . import procart
from .paths import asset

ANGLE_STEP = 5   # rotated sprites are cached every 5 degrees


class Sprites:
    def __init__(self):
        self._pil: dict[str, Image.Image] = {}
        self._photo: dict = {}

    # ------------------------------------------------------------------ loading
    def pil(self, rel: str, fallback) -> Image.Image:
        """Load assets/<rel>; if missing/corrupt build it procedurally (and try to save it)."""
        if rel not in self._pil:
            path = asset(*rel.split("/"))
            try:
                with Image.open(path) as im:
                    img = im.convert("RGBA")
            except (OSError, ValueError):
                img = fallback()
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    img.save(path)
                except OSError:
                    pass
            self._pil[rel] = img
        return self._pil[rel]

    def _photo_of(self, key, img: Image.Image):
        if key not in self._photo:
            self._photo[key] = ImageTk.PhotoImage(img)
        return self._photo[key]

    # --------------------------------------------------------------------- cars
    def car_pil(self, car_id: str) -> Image.Image:
        return self.pil(f"cars/{car_id}.png", lambda: procart.make_car_sprite(car_id))

    def car_preview(self, car_id: str, scale: float = 1.0):
        key = ("preview", car_id, scale)
        if key not in self._photo:
            img = self.pil(f"cars/{car_id}_preview.png", lambda: procart.make_car_preview(car_id))
            if scale != 1.0:
                img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
            self._photo[key] = ImageTk.PhotoImage(img)
        return self._photo[key]

    def _rotated(self, key_prefix: str, base: Image.Image, heading: float):
        idx = int(round(heading / ANGLE_STEP)) % (360 // ANGLE_STEP)
        key = (key_prefix, idx)
        if key not in self._photo:
            rot = base.rotate(-idx * ANGLE_STEP, expand=True, resample=Image.BICUBIC)
            self._photo[key] = ImageTk.PhotoImage(rot)
        return self._photo[key]

    def car_frame(self, car_id: str, heading: float):
        return self._rotated(f"car:{car_id}", self.car_pil(car_id), heading)

    def traffic_frame(self, kind: str, heading: float):
        base = self.pil(f"cars/traffic_{kind}.png", lambda: procart.make_traffic(kind))
        return self._rotated(f"traffic:{kind}", base, heading)

    # ---------------------------------------------------------------- obstacles
    def obstacle(self, kind: str, rot: float):
        base = self.pil(f"obstacles/{kind}.png", lambda: procart.make_obstacle(kind))
        return self._rotated(f"obs:{kind}", base, rot)

    def coin_frames(self) -> list:
        frames = []
        for i in range(procart.COIN_FRAMES):
            base = self.pil(f"obstacles/coin_{i}.png", lambda i=i: procart.make_coin_frames()[i])
            frames.append(self._photo_of(("coin", i), base))
        return frames

    def fuel(self):
        return self._photo_of("fuel", self.pil("obstacles/fuel.png", procart.make_fuel_can))

    def icon(self, name: str):
        return self._photo_of(("icon", name), self.pil(f"ui/{name}.png", lambda: procart.make_icon(name, 28)))

    def app_icon(self):
        return self._photo_of("app", self.pil("ui/icon.png", lambda: procart.make_icon("app", 64)))

    def preload(self) -> None:
        """Touch every image so missing files are rebuilt before the game starts."""
        from .car import CAR_ORDER
        for c in CAR_ORDER:
            self.car_pil(c)
            self.car_preview(c)
        for k in procart.TRAFFIC_TYPES:
            self.traffic_frame(k, 0)
        for k in procart.OBSTACLE_TYPES:
            self.obstacle(k, 0)
        self.coin_frames()
        self.fuel()
        for n in ("heart", "heart_empty", "coin", "fuel", "nitro"):
            self.icon(n)
