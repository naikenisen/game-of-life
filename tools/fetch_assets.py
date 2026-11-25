#!/usr/bin/env python3
"""Télécharge les assets 3D gratuits (CC0) utilisés par la vue Godot.

Tous les modèles sont de Quaternius (quaternius.com) et toutes les textures de
Poly Haven (polyhaven.com), sous licence CC0 (domaine public). Ils ne sont pas
versionnés dans git : ce script les récupère dans godot/assets/.

    python3 tools/fetch_assets.py
"""
import json
import os
import sys
import urllib.parse
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "godot", "assets")

TILAK = "https://raw.githubusercontent.com/tilakpatell/tilakverse-assets/main/quaternius/"
BEEP = "https://raw.githubusercontent.com/beep2bleep/FreeAssetsByKenneyNLandQuaternius/HEAD/FreeModels by Quaternius[Patreon]/"
DUCZ = "https://raw.githubusercontent.com/LuanDucate/Ducz.CharacterCreator/HEAD/public/models/"
POLYHAVEN = "https://dl.polyhaven.org/file/ph-assets/Textures/jpg/1k/{id}/{id}_{map}_1k.jpg"

# Personnages : Quaternius « Ultimate Modular Characters » + « Ultimate Modular Women »
CHARACTERS_M = ["Adventurer", "Beach", "Casual_2", "Casual_Hoodie", "Farmer", "King", "Punk", "Suit", "Worker"]
CHARACTERS_F = ["Adventurer", "Casual", "Formal", "Medieval", "Punk", "Suit", "Witch", "Worker"]

FILES = {
    # animations : Quaternius Universal Animation Library (120 animations humaines)
    "animations/UAL1.glb": TILAK + "universal-animation-library/Unreal-Godot/UAL1.glb",
    # animaux
    "animals/Cow.fbx": TILAK + "farm-animals/FBX/Cow.fbx",
    "animals/Pig.fbx": TILAK + "farm-animals/FBX/Pig.fbx",
    "animals/Sheep.fbx": TILAK + "farm-animals/FBX/Sheep.fbx",
    "animals/Horse.fbx": TILAK + "farm-animals/FBX/Horse.fbx",
    "animals/Wolf.fbx": BEEP + "Characters and Animals/Animal Pack Vol.2 - Jul 2017/FBX/Wolf.fbx",
    "animals/Chick.fbx": BEEP + "Characters and Animals/Animals Pack - Oct 2016/FBX/Chick.fbx",
    # mobilier (Furniture Pack mars 2019 + oct 2017)
    "furniture/BedDouble.fbx": BEEP + "Home and Buildings/Furniture Pack - March 2019/FBX/BedDouble.fbx",
    "furniture/Bookcase_Books.fbx": BEEP + "Home and Buildings/Furniture Pack - March 2019/FBX/Bookcase_Books.fbx",
    "furniture/Chair.fbx": BEEP + "Home and Buildings/Furniture Pack - March 2019/FBX/Chair.fbx",
    "furniture/Closet.fbx": BEEP + "Home and Buildings/Furniture Pack - March 2019/FBX/Closet.fbx",
    "furniture/NightStand.fbx": BEEP + "Home and Buildings/Furniture Pack - March 2019/FBX/NightStand.fbx",
    "furniture/Sofa.fbx": BEEP + "Home and Buildings/Furniture Pack - March 2019/FBX/Sofa.fbx",
    "furniture/Stool.fbx": BEEP + "Home and Buildings/Furniture Pack - March 2019/FBX/Stool.fbx",
    "furniture/Table.fbx": BEEP + "Home and Buildings/Furniture Pack - March 2019/FBX/Table.fbx",
    "furniture/Desk.fbx": BEEP + "Home and Buildings/Furniture Pack - March 2019/FBX/Desk.fbx",
    "furniture/Door1.fbx": BEEP + "Home and Buildings/Furniture Pack - March 2019/FBX/Door1.fbx",
    "furniture/Lamp.fbx": TILAK + "furniture-pack/FBX/Lamp.fbx",
    "furniture/Plant.fbx": TILAK + "furniture-pack/FBX/Plant.fbx",
    # accessoires et outils
    "props/Chest.fbx": BEEP + "Medieval/RPG Asset Pack - May 2017/FBX/AnimatedChest.fbx",
    "props/Barrel.fbx": BEEP + "Medieval/RPG Asset Pack - May 2017/FBX/Barrel.fbx",
    "props/Well.fbx": BEEP + "Home and Buildings/Farm Buildings - Sept 2018/FBX/Well.fbx",
    "props/Fence.fbx": BEEP + "Home and Buildings/Farm Buildings - Sept 2018/FBX/Fence.fbx",
    "props/Axe.fbx": BEEP + "Medieval/Medieval Weapons Pack - Sept 2018/FBX/Axe.fbx",
    "props/Hammer_Small.fbx": BEEP + "Medieval/Medieval Weapons Pack - Sept 2018/FBX/Hammer_Small.fbx",
    "props/Hammer_Double.fbx": BEEP + "Medieval/Medieval Weapons Pack - Sept 2018/FBX/Hammer_Double.fbx",
    "props/Sword.fbx": BEEP + "Medieval/Medieval Weapons Pack - Sept 2018/FBX/Sword.fbx",
    "props/Spear.fbx": BEEP + "Medieval/Medieval Weapons Pack - Sept 2018/FBX/Spear.fbx",
    "props/Bow_Wooden.fbx": BEEP + "Medieval/Medieval Weapons Pack - Sept 2018/FBX/Bow_Wooden.fbx",
    "props/Scythe.fbx": BEEP + "Medieval/Medieval Weapons Pack - Sept 2018/FBX/Scythe.fbx",
    "props/Shield_Round.fbx": BEEP + "Medieval/Medieval Weapons Pack - Sept 2018/FBX/Shield_Round.fbx",
    "props/WoodenStaff.fbx": BEEP + "Medieval/RPG Asset Pack - May 2017/FBX/WoodenStaff.fbx",
}
for n in CHARACTERS_M:
    FILES[f"characters/male/{n}.glb"] = DUCZ + f"Male/{n}.glb"
for n in CHARACTERS_F:
    FILES[f"characters/female/{n}.glb"] = DUCZ + f"Female/{n}.glb"

# Nature : Quaternius « Stylized Nature MegaKit » (glTF + textures)
NATURE = ["CommonTree_1", "CommonTree_2", "CommonTree_3", "CommonTree_4", "CommonTree_5",
          "Pine_1", "Pine_2", "Pine_3", "Birch_1", "Birch_2", "Birch_3",
          "Bush_Common", "Bush_Common_Flowers", "Bush_Large", "Fern_1", "Plant_1", "Plant_7",
          "Flower_3_Group", "Flower_4_Group", "Clover_1",
          "Grass_Common_Short", "Grass_Common_Tall", "Grass_Wispy_Tall", "Grass_Wheat",
          "Mushroom_Common", "Mushroom_RedCap", "Rock_Medium_1", "Rock_Medium_2", "Rock_Medium_3",
          "Rock_Big_1", "Rock_Big_2", "Pebble_Round_1", "Pebble_Round_2", "Pebble_Square_3"]

# Textures : Poly Haven, 1k
TEXTURES = {
    "grass": "leafy_grass", "forest": "forest_ground_04", "sand": "coast_sand_01", "soil": "farm_soil",
    "rock": "rocky_terrain_02", "gravel": "gravel_ground_01", "planks": "wood_plank_wall",
    "logs": "wood_trunk_wall", "stone_wall": "castle_wall_varriation", "brick": "medieval_red_brick",
    "plaster": "white_plaster_rough_01", "floor": "old_wood_floor", "roof_tiles": "clay_roof_tiles_02",
    "thatch": "thatch_roof_angled", "carpet": "dirty_carpet", "cobble": "cobblestone_floor_01",
}
TEX_MAPS = {"diff": "albedo", "nor_gl": "normal", "arm": "arm"}

LICENSES = {
    "LICENSE-Quaternius-CC0.txt": TILAK + "farm-animals/License.txt",
}


def url(u):
    parts = urllib.parse.urlsplit(u)
    return urllib.parse.urlunsplit(parts._replace(path=urllib.parse.quote(parts.path)))


def get(u, dest, quiet=False):
    path = os.path.join(ROOT, dest)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path, False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    req = urllib.request.Request(url(u), headers={"User-Agent": "lifesim-asset-fetcher"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    with open(path + ".part", "wb") as f:
        f.write(data)
    os.replace(path + ".part", path)
    if not quiet:
        print(f"  {dest} ({len(data) // 1024} Ko)")
    return path, True


def main():
    print(f"Téléchargement des assets dans {os.path.abspath(ROOT)}")
    errors = []
    jobs = list(FILES.items()) + list(LICENSES.items())
    for dest, u in jobs:
        try:
            get(u, dest)
        except Exception as e:
            errors.append(f"{dest}: {e}")
    # nature : chaque .gltf référence un .bin et des textures
    for name in NATURE:
        base = TILAK + "stylized-nature-megakit/glTF/"
        try:
            path, _ = get(base + name + ".gltf", f"nature/{name}.gltf")
            with open(path, encoding="utf-8") as f:
                gl = json.load(f)
            for res in gl.get("buffers", []) + gl.get("images", []):
                uri = res.get("uri", "")
                if uri and not uri.startswith("data:"):
                    get(base + urllib.parse.unquote(uri), "nature/" + urllib.parse.unquote(uri))
        except Exception as e:
            errors.append(f"nature/{name}: {e}")
    for key, pid in TEXTURES.items():
        for m, suffix in TEX_MAPS.items():
            try:
                get(POLYHAVEN.format(id=pid, map=m), f"textures/{key}_{suffix}.jpg")
            except Exception as e:
                errors.append(f"textures/{key}_{suffix}: {e}")
    if errors:
        print("\nErreurs :")
        for e in errors:
            print("  " + e)
        sys.exit(1)
    print("Tous les assets sont présents.")


if __name__ == "__main__":
    main()
