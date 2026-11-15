"""Buduje tabelę checkpointów mapy 100 Levels z pliku regionu Minecrafta.

Uruchamiaj przy zmianie mapy:
    python tools/build_level_checkpoints.py 100-levels-5229-v1.7.4.zip app/level_checkpoints.json

Wynik (`app/level_checkpoints.json`) jest wbudowany w aplikację, więc GiftStream
nie musi parsować świata w czasie działania. Pozycje to stopy gracza (y = poziom
podłogi + 1), wyliczone z rzeczywistych bloków mapy:
* poziom ma płytę checkpointu (light/heavy/stone pressure plate) → stajemy na niej,
* brak płyty → wybieramy najwyższy solidny blok w obszarze poziomu z wolnym
  miejscem na głowę (bez liści, wody, barier i lawy).
"""
from __future__ import annotations

import io
import json
import re
import struct
import sys
import zipfile
import zlib

try:
    import nbtlib
except ImportError:  # pragma: no cover - narzędzie deweloperskie
    raise SystemExit("Zainstaluj nbtlib: pip install nbtlib")

PLATES = {"minecraft:light_weighted_pressure_plate", "minecraft:heavy_weighted_pressure_plate",
          "minecraft:stone_pressure_plate"}
UNSAFE = {"minecraft:water", "minecraft:lava", "minecraft:barrier", "minecraft:air",
          "minecraft:jungle_leaves", "minecraft:oak_leaves", "minecraft:birch_leaves",
          "minecraft:spruce_leaves", "minecraft:fire", "minecraft:cactus", "minecraft:cobweb",
          "minecraft:magma_block", "minecraft:soul_fire", "minecraft:powder_snow",
          "minecraft:weeping_vines", "minecraft:kelp", "minecraft:seagrass",
          "minecraft:vine", "minecraft:ladder", "minecraft:scaffolding"}
REGION = "100 Levels/dimensions/minecraft/overworld/region/{}.mca"


def iter_chunks(raw: bytes):
    for index in range(1024):
        offset = struct.unpack_from(">I", raw, index * 4)[0]
        if offset == 0:
            continue
        start = (offset >> 8) * 4096
        if start + 5 > len(raw):
            continue
        length = struct.unpack_from(">I", raw, start)[0]
        compression = raw[start + 4]
        payload = raw[start + 5:start + 4 + length]
        try:
            decoded = zlib.decompress(payload) if compression == 2 else payload
        except zlib.error:
            continue
        try:
            root = nbtlib.File.parse(io.BytesIO(decoded))
        except Exception:
            continue
        yield root["Level"] if "Level" in root else root


def iter_blocks(root):
    """(x, y, z, name) dla każdego bloku w chunku."""
    cx, cz = int(root["xPos"]), int(root["zPos"])
    for section in root.get("sections", []):
        states = section.get("block_states")
        if not states:
            continue
        palette = [str(entry["Name"]) for entry in states.get("palette", [])]
        sy = int(section.get("Y", 0))
        data = states.get("data")
        if data is None or len(palette) == 1:
            name = palette[0]
            for index in range(4096):
                yield (cx * 16 + index % 16, sy * 16 + index // 256,
                       cz * 16 + (index // 16) % 16, name)
            continue
        bits = max(4, (len(palette) - 1).bit_length())
        per_word = 64 // bits
        mask = (1 << bits) - 1
        for word_index, word in enumerate(data):
            value64 = int(word) & ((1 << 64) - 1)
            for slot in range(per_word):
                index = word_index * per_word + slot
                if index >= 4096:
                    break
                value = (value64 >> (slot * bits)) & mask
                name = palette[value] if value < len(palette) else palette[0]
                yield (cx * 16 + index % 16, sy * 16 + index // 256,
                       cz * 16 + (index // 16) % 16, name)


def main(archive: str, output: str) -> None:
    with zipfile.ZipFile(archive) as bundle:
        setlevel = bundle.read("100 Levels/datapacks/main/data/game/function/level/setlevel.mcfunction").decode()
        areas = {}
        for match in re.finditer(
                r"x=(-?\d+),y=(\d+),z=(-?\d+),dx=(\d+),dy=(\d+),dz=(\d+)\] level (\d+)", setlevel):
            x, _y, z, dx, _dy, dz, level = map(int, match.groups())
            areas[level] = (x, z, dx, dz)

        plate_candidates: dict[int, list[tuple[int, int, int]]] = {}
        surface_candidates: dict[int, list[tuple[int, int, int]]] = {}
        region_files = sorted(name for name in bundle.namelist()
                              if re.fullmatch(r"100 Levels/dimensions/minecraft/overworld/region/r\.-?1\.0\.mca", name))
        for region_name in region_files:
            for chunk in iter_chunks(bundle.read(region_name)):
                # Kolumny przetwarzamy od razu — nie trzymamy całego świata w pamięci.
                columns: dict[tuple[int, int], dict[int, str]] = {}
                for x, y, z, name in iter_blocks(chunk):
                    if name == "minecraft:air":
                        continue
                    columns.setdefault((x, z), {})[y] = name
                for (x, z), column in columns.items():
                    level = next((lv for lv, (ax, az, dx, dz) in areas.items()
                                  if ax <= x <= ax + dx and az <= z <= az + dz), None)
                    if level is None:
                        continue
                    for y, name in column.items():
                        if name not in PLATES:
                            continue
                        if _standable(column, y):
                            plate_candidates.setdefault(level, []).append((x, y, z))
                    for y in sorted(column, reverse=True):
                        if 0 <= y <= 200 and column[y] not in UNSAFE and _standable(column, y):
                            surface_candidates.setdefault(level, []).append((x, y, z))
                            break

    checkpoints: dict[int, dict] = {}
    for level, (ax, az, dx, dz) in sorted(areas.items()):
        options = plate_candidates.get(level) or surface_candidates.get(level) or []
        source = "plate" if plate_candidates.get(level) else "surface"
        if not options:
            raise SystemExit(f"Nie znaleziono bezpiecznego checkpointu dla poziomu {level}.")
        # Preferujemy środek obszaru, żeby punkt był powtarzalny i blisko trasy.
        options = sorted(options, key=lambda spot: (abs(spot[0] - (ax + dx / 2)) + abs(spot[2] - (az + dz / 2)), -spot[1]))
        x, y, z = options[0]
        checkpoints[level] = {"x": x + 0.5, "y": y + 1.0, "z": z + 0.5,
                              "source": source, "area": [ax, az, dx, dz]}

    payload = {"map": "100-levels-5229-v1.7.4", "version": 1, "levels": checkpoints}
    with open(output, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1, sort_keys=True)
    missing = [level for level in sorted(areas) if checkpoints[level]["source"] == "surface"]
    print(f"Zapisano {len(checkpoints)} checkpointów do {output}.")
    print(f"Poziomy bez płyty (fallback z powierzchni): {missing}")


def _standable(column: dict[int, str], y: int) -> bool:
    """y = poziom płyty/podłogi; stopy na y+1, głowa na y+2 (ta sama kolumna)."""
    if column.get(y) in UNSAFE or y not in column:
        return False
    return y + 1 not in column and y + 2 not in column


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
