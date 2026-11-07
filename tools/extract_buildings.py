#!/usr/bin/env python3
"""Extract the 44 active and 7 scenario infrastructure buildings to buildings.ron."""

import argparse
from pathlib import Path
import re
import sys

from project_paths import get_project_paths

BUILDING_OVERRIDES = {
    "wharf": {"name": "Wharf"},
}

OPENING_HOURS_NAMES = frozenset({"ALLHOURS", "MORNING", "DAY", "EVENING", "NIGHT"})

ACTIVE_BUILDINGS = [
    "hotel", "powergen", "watercln", "accomblk", "firstaid", "loo", "rep", "cleanershack",
    "security_post", "handyman", "genstore", "souvshop", "baywatch", "beachhut", "poolbar",
    "bar1", "bar2", "beachbar", "barbecue", "cafe1", "cafe2", "restrnt1", "restrnt2",
    "icestall", "softdrnk", "fastfood", "mainpool", "jacuzzi", "funpool", "eqpthire",
    "partyboat", "beachdisco", "stage", "bchshwr", "njjetskihire", "windsurfinghire",
    "arcade", "casino", "njspdboathire", "njpedloehire", "njfishingtrips", "club1",
    "club2", "cocktail", "builderyard", "busstop", "complainthut", "jetty_front",
    "jetty_mid", "jetty_end", "wharf"
]


def _require_opening_hours(building_key, opening_hours):
    if opening_hours is None:
        raise ValueError(f"Building {building_key} is missing OPENINGHOURS")
    if opening_hours not in OPENING_HOURS_NAMES:
        raise ValueError(
            f"Building {building_key} has unknown OPENINGHOURS {opening_hours!r}"
        )
    return opening_hours


def parse_building_list(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Split content by BUILD_ to isolate building blocks
    # Use re.split with a capture group to keep the building keys
    blocks = re.split(r'^\s*"BUILD_([A-Z0-9_]+)"', content, flags=re.MULTILINE)
    
    buildings_data = {}
    
    if len(blocks) > 1:
        for i in range(1, len(blocks), 2):
            b_key = blocks[i].lower()
            if b_key not in ACTIVE_BUILDINGS:
                continue
            
            block_content = blocks[i+1]
            prefix = b_key.upper()
            lines = block_content.splitlines()
            
            # Initialize fields
            name = None
            sprite = None
            cost = None
            refund = None
            width = None
            height = None
            capacity = None
            opening_hours = None
            power = 0
            category = None
            terrain = []
            menu = "None"
            construct_sprite = None
            build_time = 0
            baseplate_type = 0
            num_baseplates = 0

            token_pattern = re.compile(r'"([^"]*)"|(\S+)')
            
            for line in lines:
                # Strip comments
                if '//' in line:
                    line = line.split('//', 1)[0]
                line = line.strip()
                if not line:
                    continue
                
                # Check for property
                m = re.match(r'^\s*"([A-Z0-9_]+)"\s*(.*)$', line)
                if not m:
                    continue
                
                prop_key = m.group(1)
                prop_val_part = m.group(2)
                
                if not prop_key.startswith(prefix + "_"):
                    continue
                
                suffix = prop_key[len(prefix)+1:]
                
                # Parse tokens
                matches = token_pattern.findall(prop_val_part)
                tokens = [g[0] if g[0] != '' else g[1] for g in matches]
                if not tokens:
                    continue
                
                # Assign fields
                if suffix == "NAME":
                    name = tokens[0]
                elif suffix == "SPRITE":
                    sprite = tokens[0]
                elif suffix == "COST2BUILD":
                    cost = int(tokens[0])
                elif suffix == "REFUNDVALUE":
                    refund = int(tokens[0])
                elif suffix == "GRIDWIDTH":
                    width = int(tokens[0])
                elif suffix == "GRIDHEIGHT":
                    height = int(tokens[0])
                elif suffix == "GUESTCAPACITY":
                    capacity = int(tokens[0])
                elif suffix == "OPENINGHOURS":
                    opening_hours = tokens[0]
                elif suffix == "POWER":
                    power = int(tokens[0])
                elif suffix == "CATEGORY":
                    category = tokens[0]
                elif suffix == "BUILDON":
                    terrain.append(tokens[0])
                elif suffix == "MENU":
                    menu = tokens[0]
                elif suffix == "CONSTRUCT":
                    construct_sprite = tokens[0]
                elif suffix == "BUILDTIME":
                    build_time = int(tokens[0])
                elif suffix == "BASEPLATETYPE":
                    baseplate_type = int(tokens[0])
                elif suffix == "NUM_BASEPLATES":
                    num_baseplates = int(tokens[0])
            
            opening_hours = _require_opening_hours(b_key, opening_hours)

            # Check for missing fields
            missing = []
            if name is None:
                missing.append("name")
            if sprite is None:
                missing.append("sprite")
            if cost is None:
                missing.append("cost")
            if refund is None:
                missing.append("refund")
            if width is None:
                missing.append("width")
            if height is None:
                missing.append("height")
            if capacity is None:
                missing.append("capacity")
            if category is None:
                missing.append("category")
            if not terrain:
                missing.append("terrain")
            
            if missing:
                print(f"[WARN] Building {b_key} is missing fields: {missing}", file=sys.stderr)
            
            building_data = {
                "key": b_key,
                "name": name,
                "sprite": sprite,
                "cost": cost,
                "refund": refund,
                "width": width,
                "height": height,
                "capacity": capacity,
                "opening_hours": opening_hours,
                "power": power,
                "category": category,
                "terrain": terrain,
                "menu": menu,
                "construct_sprite": construct_sprite,
                "build_time": build_time,
                "baseplate_type": baseplate_type,
                "num_baseplates": num_baseplates,
            }
            building_data.update(BUILDING_OVERRIDES.get(b_key, {}))
            buildings_data[b_key] = building_data

    return buildings_data

def write_ron(buildings_dict, output_path):
    output_path = Path(output_path)
    lines = ["[\n"]
    for key in ACTIVE_BUILDINGS:
        if key not in buildings_dict:
            print(f"[ERROR] Active building {key} not found in parsed data!", file=sys.stderr)
            sys.exit(1)
        b = buildings_dict[key]
        lines.append("    (\n")
        lines.append(f'        key: "{b["key"]}",\n')
        lines.append(f'        name: "{b["name"]}",\n')
        lines.append(f'        sprite: "{b["sprite"]}",\n')
        lines.append(f'        cost: {b["cost"]},\n')
        lines.append(f'        refund: {b["refund"]},\n')
        lines.append(f'        width: {b["width"]},\n')
        lines.append(f'        height: {b["height"]},\n')
        lines.append(f'        capacity: {b["capacity"]},\n')
        opening_hours = _require_opening_hours(key, b.get("opening_hours"))
        lines.append(f'        opening_hours: {opening_hours},\n')
        lines.append(f'        power: {b["power"]},\n')
        lines.append(f'        category: "{b["category"]}",\n')
        
        # Format terrain list
        terrain_str = ", ".join(f'"{t}"' for t in b["terrain"])
        lines.append(f'        terrain: [{terrain_str}],\n')
        lines.append(f'        menu: "{b["menu"]}",\n')
        construct_sprite = b["construct_sprite"]
        if construct_sprite is None:
            lines.append("        construct_sprite: None,\n")
        else:
            lines.append(f'        construct_sprite: Some("{construct_sprite}"),\n')
        lines.append(f'        build_time: {b["build_time"]},\n')
        lines.append(f'        baseplate_type: {b["baseplate_type"]},\n')
        lines.append(f'        num_baseplates: {b["num_baseplates"]},\n')
        lines.append("    ),\n")
    lines.append("]\n")
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('w', encoding='utf-8') as f:
        f.write("".join(lines))
    print(f"Successfully wrote {len(ACTIVE_BUILDINGS)} buildings to {output_path}")


def _repo_relative_path(path, repo_root):
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate
    return repo_root / candidate


def create_argument_parser(default_input, default_output):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-i",
        "--input",
        "--input-path",
        dest="input_path",
        type=Path,
        default=None,
        help=f"BuildingList.txt input (default: {default_input})",
    )
    parser.add_argument(
        "-o",
        "--output",
        "--output-path",
        dest="output_path",
        type=Path,
        default=None,
        help=f"buildings.ron output (default: {default_output})",
    )
    return parser


def main(argv=None):
    paths = get_project_paths()
    default_input = paths.decrypted_ble_dir / "Script" / "BuildingList.txt"
    default_output = paths.buildings_path
    args = create_argument_parser(default_input, default_output).parse_args(argv)
    input_path = (
        _repo_relative_path(args.input_path, paths.repo_root)
        if args.input_path is not None
        else default_input
    )
    output_path = (
        _repo_relative_path(args.output_path, paths.repo_root)
        if args.output_path is not None
        else default_output
    )

    if not input_path.exists():
        print(f"[ERROR] Input file not found: {input_path}", file=sys.stderr)
        return 1

    print(f"Parsing buildings from {input_path}...")
    buildings_dict = parse_building_list(input_path)
    print(f"Parsed {len(buildings_dict)} active buildings.")

    write_ron(buildings_dict, output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
