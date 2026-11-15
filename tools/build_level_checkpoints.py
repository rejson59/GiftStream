"""Build the checkpoint table of the 100 Levels map from the real world file.

Run it whenever the bundled map changes::

    python tools/build_level_checkpoints.py 100-levels-5229-v1.7.4.zip app/level_checkpoints_data.py

How the map itself works (this is what the table follows):

* ``datapacks/main/data/game/function/level/setlevel.mcfunction`` contains one
  selector per level. The datapack runs every line each tick in file order, so
  when two boxes overlap the **last** matching line decides the level score.
  That file is the single source of truth for "which level am I on".
* A level's checkpoint is the pressure plate standing at its start: when the
  player steps on it, ``common:ingame/checkpoint/checkpoint/set`` runs
  ``spawnpoint @s ~ ~ ~``. There is no coordinate list in the datapack, so the
  plates have to be read from the region files.
* Levels without a plate (5, 9, 14, 32, 56, 65, 73, 78, 97) fall back to the
  highest safe block inside the level box.

Which plate is picked: for every level the candidate closest to the previous
level's box wins (that is the entrance of the stage), with plates preferred
over the surface fallback. This matters for levels with several plates, e.g.
level 100 has five (four of them in the final arena, one on the course) — only
the course one is the level's entrance.

The output is a **Python module**, not JSON: a separate data file was not
bundled into the PyInstaller executable, which made every level change fail with
"no stored checkpoint" in the released .app/.exe.
"""
from __future__ import annotations

import io
import math
import re
import struct
import sys
import zipfile
import zlib

try:
    import nbtlib
except ImportError:  # pragma: no cover - developer tool only
    raise SystemExit("Install nbtlib first: pip install nbtlib")

PLATES = {"minecraft:light_weighted_pressure_plate",
          "minecraft:heavy_weighted_pressure_plate",
          "minecraft:stone_pressure_plate"}
UNSAFE = {"minecraft:water", "minecraft:lava", "minecraft:barrier", "minecraft:air",
          "minecraft:jungle_leaves", "minecraft:oak_leaves", "minecraft:birch_leaves",
          "minecraft:spruce_leaves", "minecraft:acacia_leaves", "minecraft:dark_oak_leaves",
          "minecraft:mangrove_leaves", "minecraft:cherry_leaves", "minecraft:azalea_leaves",
          "minecraft:flowering_azalea_leaves", "minecraft:fire", "minecraft:cactus",
          "minecraft:cobweb", "minecraft:magma_block", "minecraft:soul_fire",
          "minecraft:powder_snow", "minecraft:weeping_vines", "minecraft:kelp",
          "minecraft:seagrass", "minecraft:vine", "minecraft:ladder",
          "minecraft:scaffolding", "minecraft:torch", "minecraft:wall_torch",
          "minecraft:soul_torch", "minecraft:redstone_torch", "minecraft:tripwire",
          "minecraft:tripwire_hook", "minecraft:string", "minecraft:light",
          "minecraft:iron_bars"}
SETLEVEL = "100 Levels/datapacks/main/data/game/function/level/setlevel.mcfunction"
SELECTOR = re.compile(r"x=(-?\d+),y=0,z=(-?\d+),dx=(\d+),dy=(\d+),dz=(\d+)\].*? level (\d+)$")
REGION = re.compile(r"100 Levels/dimensions/minecraft/overworld/region/r\.(-?\d+)\.(-?\d+)\.mca")


def read_areas(bundle: zipfile.ZipFile) -> list[tuple[int, int, int, int, int, int]]:
    """(level, x, z, dx, dz, dy) in the exact order the datapack applies them."""
    text = bundle.read(SETLEVEL).decode("utf-8")
    result = []
    for line in text.splitlines():
        match = SELECTOR.search(line.rstrip("\r"))
        if match:
            x, z, dx, dy, dz, level = map(int, match.groups())
            result.append((level, x, z, dx, dz, dy))
    return result


def iter_chunks(bundle: zipfile.ZipFile, name: str):
    raw = bundle.read(name)
    if len(raw) < 8192:
        return
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


def chunk_columns(chunk) -> dict[tuple[int, int], dict[int, str]]:
    """(x, z) -> {y: block} for every non-air block of one chunk."""
    cx, cz = int(chunk["xPos"]), int(chunk["zPos"])
    columns: dict[tuple[int, int], dict[int, str]] = {}
    for section in chunk.get("sections", []):
        states = section.get("block_states")
        if not states:
            continue
        palette = [str(entry["Name"]) for entry in states.get("palette", [])]
        sy = int(section.get("Y", 0))
        data = states.get("data")
        if data is None or len(palette) == 1:
            if palette[0] == "minecraft:air":
                continue
            for index in range(4096):
                columns.setdefault((cx * 16 + index % 16, cz * 16 + (index // 16) % 16), {})[
                    sy * 16 + index // 256] = palette[0]
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
                if name == "minecraft:air":
                    continue
                columns.setdefault((cx * 16 + index % 16, cz * 16 + (index // 16) % 16), {})[
                    sy * 16 + index // 256] = name
    return columns


def level_score_at(areas, x: int, y: int, z: int) -> int | None:
    score = None
    for level, ax, az, dx, dz, dy in areas:
        if ax <= x <= ax + dx and az <= z <= az + dz and 0 <= y <= dy:
            score = level
    if score is not None:
        return score
    for level, ax, az, dx, dz, _dy in areas:
        if ax <= x <= ax + dx and az <= z <= az + dz:
            score = level
    return score


def box_gap(point: tuple[int, int, int], area: tuple[int, int, int, int, int]) -> int:
    ax, az, dx, dz, _dy = area
    return (max(ax - point[0], 0, point[0] - (ax + dx))
            + max(az - point[2], 0, point[2] - (az + dz)))


def build(bundle: zipfile.ZipFile):
    areas = read_areas(bundle)
    boxes: dict[int, tuple[int, int, int, int, int]] = {}
    for level, x, z, dx, dz, dy in areas:
        boxes.setdefault(level, (x, z, dx, dz, dy))

    plates: dict[int, list[tuple[int, int, int]]] = {}
    surface: dict[int, list[tuple[int, int, int]]] = {}
    for name in sorted(n for n in bundle.namelist() if REGION.fullmatch(n)):
        for chunk in iter_chunks(bundle, name):
            for (x, z), column in chunk_columns(chunk).items():
                for y, block in column.items():
                    if block not in PLATES:
                        continue
                    level = level_score_at(areas, x, y + 1, z)
                    if level and (y + 1) not in column and (y + 2) not in column:
                        plates.setdefault(level, []).append((x, y, z))
                for y in sorted(column, reverse=True):
                    if y > 200 or column[y] in UNSAFE:
                        continue
                    if (y + 1) in column or (y + 2) in column:
                        continue
                    level = level_score_at(areas, x, y + 1, z)
                    if level:
                        surface.setdefault(level, []).append((x, y, z))
                        break

    checkpoints: dict[int, dict] = {}
    for level in range(1, 101):
        if level not in boxes:
            raise SystemExit(f"No area for level {level}.")
        box = boxes[level]
        candidates = ([(p, 0) for p in plates.get(level, [])]
                      + [(p, 1) for p in surface.get(level, [])])
        if not candidates:
            raise SystemExit(f"No safe checkpoint found for level {level}.")
        if level == 1:
            # The first level starts on its own checkpoint plate.
            centre_x, centre_z = box[0] + box[2] / 2, box[1] + box[3] / 2
            best = min(candidates, key=lambda c: (c[1],
                                                  abs(c[0][0] + 0.5 - centre_x)
                                                  + abs(c[0][2] + 0.5 - centre_z),
                                                  -c[0][1]))
        else:
            previous = checkpoints[level - 1]
            previous_box = boxes[level - 1]
            best = min(candidates, key=lambda c: (
                c[1],                                     # real plates before fallbacks
                box_gap(c[0], previous_box),              # the entrance of the stage
                math.dist((c[0][0] + 0.5, c[0][1] + 1, c[0][2] + 0.5),
                          (previous["x"], previous["y"], previous["z"])),
                -c[0][1]))
        point, source = best
        checkpoints[level] = {"x": point[0] + 0.5, "y": float(point[1] + 1),
                              "z": point[2] + 0.5,
                              "source": "plate" if source == 0 else "surface",
                              "area": [box[0], box[1], box[2], box[3]]}
    return checkpoints


def write_module(checkpoints: dict[int, dict], map_name: str, output: str) -> None:
    lines = [
        '"""Checkpoint table of the bundled 100 Levels map (generated file).',
        "",
        "Generated by ``tools/build_level_checkpoints.py`` from the real map blocks:",
        "the start plate of every level (the map sets the player's spawnpoint there),",
        "falling back to the highest safe block when a level has no plate.",
        "",
        "Kept as a Python module on purpose: a separate JSON file was not shipped",
        "inside the PyInstaller executable, which made every level change fail with",
        "'no stored checkpoint'.",
        '"""',
        "from __future__ import annotations",
        "",
        f'SOURCE_MAP = "{map_name}"',
        "VERSION = 2",
        "",
        "# level -> (feet x, feet y, feet z, source, (area x, area z, area dx, area dz))",
        "CHECKPOINTS: dict[int, tuple[float, float, float, str, tuple[int, int, int, int]]] = {",
    ]
    for level in sorted(checkpoints):
        spot = checkpoints[level]
        area = tuple(spot["area"])
        lines.append(f'    {level}: ({spot["x"]!r}, {spot["y"]!r}, {spot["z"]!r}, '
                     f'"{spot["source"]}", {area!r}),')
    lines.append("}")
    with open(output, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def main(archive: str, output: str) -> None:
    with zipfile.ZipFile(archive) as bundle:
        checkpoints = build(bundle)
    write_module(checkpoints, archive.rsplit("/", 1)[-1].removesuffix(".zip"), output)
    fallback = [level for level in sorted(checkpoints) if checkpoints[level]["source"] == "surface"]
    print(f"Wrote {len(checkpoints)} checkpoints to {output}.")
    print(f"Levels without a checkpoint plate (surface fallback): {fallback}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
