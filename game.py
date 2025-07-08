import pyglet
from pyglet.gl import *
import math
import json
import os
import requests
import base64
from dotenv import load_dotenv
import noise
import random
import zipfile
import shutil
import tempfile
from io import BytesIO
import os
# 他の必要なインポート (例: pyglet, pyglet.glなど)

# 環境変数を取得
WORLD_NAME = os.getenv('WORLD_NAME', 'Default World')
PLAYER_UUID = os.getenv('PLAYER_UUID', 'default-player-uuid')
WORLD_UUID = os.getenv('WORLD_UUID', 'default-world-uuid')
RESOURCE_PACKS_STR = os.getenv('RESOURCE_PACKS', '') # 新しく追加
BEHAVIOR_PACKS_STR = os.getenv('BEHAVIOR_PACKS', '') # 新しく追加

print(f"Game starting with:")
print(f"  World Name: {WORLD_NAME}")
print(f"  Player UUID: {PLAYER_UUID}")
print(f"  World UUID: {WORLD_UUID}")

# パック情報を処理（プレースホルダー）
if RESOURCE_PACKS_STR:
    resource_packs = RESOURCE_PACKS_STR.split(',')
    print(f"  Resource Packs (selected): {resource_packs}")
    print("  (Note: Resource packs would be loaded here in a full game engine.)")
else:
    print("  No Resource Packs selected.")

if BEHAVIOR_PACKS_STR:
    behavior_packs = BEHAVIOR_PACKS_STR.split(',')
    print(f"  Behavior Packs (selected): {behavior_packs}")
    print("  (Note: Behavior packs would be loaded here in a full game engine.)")
else:
    print("  No Behavior Packs selected.")



# .envファイルをロード
load_dotenv()

# --- GitHub API 設定 ---
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_OWNER = os.getenv('GITHUB_OWNER')
GITHUB_REPO = os.getenv('GITHUB_REPO')

if not GITHUB_TOKEN or not GITHUB_OWNER or not GITHUB_REPO:
    print("エラー: .env ファイルに GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO が設定されていません。")
    print("または GITHUB_OWNER, GITHUB_REPO が正しく設定されていません。")
    exit(1)

GITHUB_API_BASE_URL = f'https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents'
HEADERS = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.com.v3+json',
    'User-Agent': 'Pyglet-Minecraft-Game'
}

# --- GitHub API ヘルパー関数 ---
def get_github_file_content(path):
    """GitHubからファイルの内容を取得し、JSONとしてデコードする (コンテンツAPI用)"""
    url = f'{GITHUB_API_BASE_URL}/{path}'
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        content_b64 = response.json()['content']
        decoded_content = base64.b64decode(content_b64).decode('utf-8')
        return json.loads(decoded_content)
    return None

def put_github_file_content(path, content, message, sha=None):
    """GitHubにファイルの内容をJSONとしてエンコードし、保存する (コンテンツAPI用)"""
    url = f'{GITHUB_API_BASE_URL}/{path}'
    encoded_content = base64.b64encode(json.dumps(content, indent=4).encode('utf-8')).decode('utf-8')
    data = {
        'message': message,
        'content': encoded_content
    }
    if sha:
        data['sha'] = sha

    response = requests.put(url, headers=HEADERS, json=data)
    return response.status_code in [200, 201], response.json()

def get_github_file_info(path):
    """GitHubからファイルのSHAなどの情報を取得する (コンテンツAPI用)"""
    url = f'{GITHUB_API_BASE_URL}/{path}'
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        return response.json()
    return None

def download_github_raw_file(path):
    """GitHubからファイルの生データ (バイナリ) をダウンロードする"""
    url = f'https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/main/{path}'
    response = requests.get(url, headers={'Authorization': f'token {GITHUB_TOKEN}'})
    if response.status_code == 200:
        return response.content
    print(f"Failed to download raw file from GitHub: {url} (Status: {response.status_code})")
    return None

def list_github_directory(path):
    """GitHubディレクトリ内のファイルとディレクトリをリストアップする"""
    url = f'{GITHUB_API_BASE_URL}/{path}'
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        return response.json()
    print(f"Failed to list GitHub directory {path}: {response.status_code} - {response.text}")
    return []


# --- グローバル変数と初期設定 ---
window = pyglet.window.Window(width=1024, height=768, caption='Cave Game', resizable=True)

# OpenGLの設定
glEnable(GL_DEPTH_TEST)
glEnable(GL_CULL_FACE)
glEnable(GL_TEXTURE_2D)
glEnable(GL_BLEND)
glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

camera_x, camera_y, camera_z = 0.0, 0.0, -5.0
camera_rot_x, camera_rot_y = 0.0, 0.0
mouse_sensitivity = 0.1
keys = pyglet.window.key.KeyStateHandler()
window.push_handlers(keys)

# --- 物理定数 ---
GRAVITY = 20.0
JUMP_SPEED = 8.0
PLAYER_HEIGHT = 1.8
PLAYER_WIDTH = 0.6
EYE_HEIGHT_OFFSET = 1.62

velocity_x, velocity_y, velocity_z = 0.0, 0.0, 0.0
on_ground = False

# --- プレイヤーのHP ---
player_hp = 20.0
SUFFOCATION_DAMAGE_INTERVAL = 0.5
suffocation_timer = 0.0

# --- インベントリ設定 ---
INVENTORY_SLOT_COUNT = 9
ITEM_STACK_LIMIT = 64
player_inventory = []
selected_slot = 0

# --- ブロック定義とテクスチャ ---
BLOCK_DEFINITIONS = {
    "minecraft:air": {"id": 0, "texture_key": None, "is_solid": False, "is_falling_block": False},
    "minecraft:grass": {"id": 1, "texture_key": "grass", "is_solid": True, "is_falling_block": False},
    "minecraft:dirt": {"id": 2, "texture_key": "dirt", "is_solid": True, "is_falling_block": False},
    "minecraft:stone": {"id": 3, "texture_key": "stone", "is_solid": True, "is_falling_block": False},
    "minecraft:sand": {"id": 4, "texture_key": "sand", "is_solid": True, "is_falling_block": True},
    "minecraft:gravel": {"id": 5, "texture_key": "gravel", "is_solid": True, "is_falling_block": True},
    "minecraft:concrete_powder": {"id": 6, "texture_key": "concrete_powder", "is_solid": True, "is_falling_block": True},
}

BLOCK_IDENTIFIER_TO_ID = {identifier: props["id"] for identifier, props in BLOCK_DEFINITIONS.items()}
BLOCK_ID_TO_IDENTIFIER = {props["id"]: identifier for identifier, props in BLOCK_DEFINITIONS.items()}

FALLING_BLOCK_IDS = [
    props["id"] for identifier, props in BLOCK_DEFINITIONS.items() 
    if props.get("is_falling_block", False)
]

DEFAULT_TEXTURE_URLS = {
    "grass": 'https://placehold.co/64x64/00FF00/FFFFFF?text=Grass',
    "dirt": 'https://placehold.co/64x64/8B4513/FFFFFF?text=Dirt',
    "stone": 'https://placehold.co/64x64/808080/FFFFFF?text=Stone',
    "sand": 'https://placehold.co/64x64/FFFF00/000000?text=Sand',
    "gravel": 'https://placehold.co/64x64/A9A9A9/FFFFFF?text=Gravel',
    "concrete_powder": 'https://placehold.co/64x64/B0C4DE/000000?text=ConcretePowder',
}

textures = {}

def load_image_to_texture_cache(texture_key, image_source, is_bytes=False):
    """
    画像ソース（URLまたはバイトデータ）からテクスチャをロードし、
    textures辞書にtexture_keyでキャッシュする。
    """
    try:
        if is_bytes:
            from io import BytesIO
            image_data = BytesIO(image_source)
            image = pyglet.image.load('', file=image_data)
        else:
            response = requests.get(image_source, stream=True)
            response.raise_for_status()
            from io import BytesIO
            image_data = BytesIO(response.content)
            image = pyglet.image.load('', file=image_data)
        
        texture = image.get_texture()
        textures[texture_key] = texture
        print(f"Loaded texture '{texture_key}' from {'bytes' if is_bytes else image_source}")
        return texture
    except Exception as e:
        print(f"Failed to load texture '{texture_key}' from {'bytes' if is_bytes else image_source}: {e}")
        fallback_image = pyglet.image.create(64, 64, pyglet.image.SolidColorImagePattern((255, 0, 0, 255)))
        fallback_texture = fallback_image.get_texture()
        textures[texture_key] = fallback_texture
        return fallback_texture

def load_default_textures():
    for texture_key, url in DEFAULT_TEXTURE_URLS.items():
        load_image_to_texture_cache(texture_key, url, is_bytes=False)

# ワールドデータ (辞書: キーは "(x,y,z)" 形式の文字列、値はブロックID)
world_data = {}

# --- ワールド名とUUID、プレイヤーUUIDを環境変数から取得 ---
# 環境変数が設定されていない場合は、テスト用のデフォルト値を使用
current_world_name = os.getenv('WORLD_NAME', "MyFirstCave")
current_player_uuid = os.getenv('PLAYER_UUID', "test-player-uuid-1234")
current_world_uuid = os.getenv('WORLD_UUID', "test-world-uuid-abcd")

print(f"Game starting with: World='{current_world_name}', Player='{current_player_uuid}', World_UUID='{current_world_uuid}'")

# ワールドデータのファイルパス
WORLD_BLOCK_FILE_PATH = f'worlds/{current_player_uuid}/{current_world_name}-{current_player_uuid}-block-{current_world_uuid}.json'
PLAYER_POS_FILE_PATH = f'worlds/{current_player_uuid}/{current_world_name}-{current_player_uuid}-playerxyz-{current_world_uuid}.json'
PLAYER_ITEM_FILE_PATH = f'worlds/{current_player_uuid}/{current_world_name}-{current_player_uuid}-player-item-{current_world_uuid}.json'

# --- ワールドデータのロード/セーブ関数 ---
def load_world_blocks():
    """GitHubからワールドブロックデータとプレイヤー位置データをロードする"""
    global world_data, camera_x, camera_y, camera_z

    loaded_blocks = get_github_file_content(WORLD_BLOCK_FILE_PATH)
    if loaded_blocks:
        world_data = loaded_blocks
        print(f"Loaded world blocks from {WORLD_BLOCK_FILE_PATH}")
    else:
        print(f"No existing world blocks found for {WORLD_BLOCK_FILE_PATH}. Generating new world.")
        seed = random.randint(0, 100000)
        generate_noise_terrain(seed)
        save_world_blocks()

    loaded_pos = get_github_file_content(PLAYER_POS_FILE_PATH)
    if loaded_pos:
        camera_x, camera_y, camera_z = loaded_pos['x'], loaded_pos['y'], loaded_pos['z']
        print(f"Loaded player position: ({camera_x}, {camera_y}, {camera_z})")
    else:
        initial_x = WORLD_SIZE_X // 2
        initial_z = WORLD_SIZE_Z // 2
        initial_y = get_terrain_height(initial_x, initial_z) + EYE_HEIGHT_OFFSET + 1
        camera_x, camera_y, camera_z = float(initial_x), float(initial_y), float(initial_z)
        print(f"No player position found. Setting default: ({camera_x}, {camera_y}, {camera_z})")
        save_player_position()

def save_world_blocks():
    """ワールドブロックデータをGitHubに保存する"""
    file_info = get_github_file_info(WORLD_BLOCK_FILE_PATH)
    sha = file_info['sha'] if file_info else None
    
    success, response = put_github_file_content(
        WORLD_BLOCK_FILE_PATH, 
        world_data, 
        f'Update world blocks for {current_world_name}', 
        sha
    )
    if not success:
        print(f"Failed to save world blocks: {response}")

def save_player_position():
    """プレイヤー位置をGitHubに保存する"""
    player_pos_data = {'x': camera_x, 'y': camera_y, 'z': camera_z}
    file_info = get_github_file_info(PLAYER_POS_FILE_PATH)
    sha = file_info['sha'] if file_info else None

    success, response = put_github_file_content(
        PLAYER_POS_FILE_PATH,
        player_pos_data,
        f'Update player position for {current_world_name}',
        sha
    )
    if not success:
        print(f"Failed to save player position: {response}")

def load_player_inventory():
    """プレイヤーのインベントリをGitHubからロードする"""
    global player_inventory
    loaded_inventory = get_github_file_content(PLAYER_ITEM_FILE_PATH)
    if loaded_inventory:
        player_inventory = loaded_inventory
        print(f"Loaded player inventory from {PLAYER_ITEM_FILE_PATH}")
    else:
        player_inventory = [
            {"id": BLOCK_IDENTIFIER_TO_ID["minecraft:grass"], "count": 64},
            {"id": BLOCK_IDENTIFIER_TO_ID["minecraft:dirt"], "count": 64},
            {"id": BLOCK_IDENTIFIER_TO_ID["minecraft:stone"], "count": 64},
            {"id": BLOCK_IDENTIFIER_TO_ID["minecraft:sand"], "count": 64},
            {"id": BLOCK_IDENTIFIER_TO_ID["minecraft:gravel"], "count": 64},
            {"id": BLOCK_IDENTIFIER_TO_ID["minecraft:concrete_powder"], "count": 64},
        ]
        player_inventory = player_inventory[:INVENTORY_SLOT_COUNT] + [{"id": BLOCK_IDENTIFIER_TO_ID["minecraft:air"], "count": 0}] * (INVENTORY_SLOT_COUNT - len(player_inventory))
        print("No existing player inventory found. Initializing default inventory.")
        save_player_inventory()

def save_player_inventory():
    """プレイヤーのインベントリをGitHubに保存する"""
    file_info = get_github_file_info(PLAYER_ITEM_FILE_PATH)
    sha = file_info['sha'] if file_info else None

    success, response = put_github_file_content(
        PLAYER_ITEM_FILE_PATH,
        player_inventory,
        f'Update player inventory for {current_world_name}',
        sha
    )
    if not success:
        print(f"Failed to save player inventory: {response}")

# --- 地形生成関数 (ノイズベース) ---
WORLD_SIZE_X = 64
WORLD_SIZE_Y = 64
WORLD_SIZE_Z = 64
NOISE_SCALE = 20.0
TERRAIN_HEIGHT_OFFSET = 10

def get_terrain_height(x, z, seed=0):
    """指定された(x,z)座標の地形の高さをノイズで計算する"""
    height = noise.pnoise2(x / NOISE_SCALE, z / NOISE_SCALE, octaves=4, persistence=0.5, lacunarity=2.0, repeatx=1024, repeaty=1024, base=seed)
    height = (height + 1.0) / 2.0
    return int(height * (WORLD_SIZE_Y / 2)) + TERRAIN_HEIGHT_OFFSET

def generate_noise_terrain(seed):
    """ノイズベースの地形を生成し、world_dataに格納する"""
    global world_data
    world_data = {}

    print(f"Generating terrain with seed: {seed}")

    for x in range(WORLD_SIZE_X):
        for z in range(WORLD_SIZE_Z):
            height = get_terrain_height(x, z, seed)
            
            world_data[f"{x},{height},{z}"] = BLOCK_IDENTIFIER_TO_ID["minecraft:grass"]
            
            for y_dirt in range(height - 1, height - 3, -1):
                if y_dirt >= 0:
                    world_data[f"{x},{y_dirt},{z}"] = BLOCK_IDENTIFIER_TO_ID["minecraft:dirt"]
            
            for y_stone in range(height - 3, -WORLD_SIZE_Y, -1):
                if y_stone >= -WORLD_SIZE_Y:
                    world_data[f"{x},{y_stone},{z}"] = BLOCK_IDENTIFIER_TO_ID["minecraft:stone"]
    print("Terrain generation complete.")

# --- ブロックの描画関数 (テクスチャ対応) ---
def draw_block(x, y, z, block_id):
    """指定された位置に、指定されたブロックIDのブロックを描画する（テクスチャ付き）"""
    if block_id == BLOCK_IDENTIFIER_TO_ID["minecraft:air"]:
        return

    identifier = BLOCK_ID_TO_IDENTIFIER.get(block_id)
    if not identifier:
        print(f"Warning: Unknown block ID {block_id}. Skipping draw.")
        return

    block_props = BLOCK_DEFINITIONS.get(identifier)
    if not block_props or not block_props.get("texture_key"):
        return

    texture = textures.get(block_props["texture_key"])
    if not texture:
        return

    glBindTexture(texture.target, texture.id)
    
    glPushMatrix()
    glTranslatef(x + 0.5, y + 0.5, z + 0.5)
    
    glBegin(GL_QUADS)
    # 前面 (Z+)
    glTexCoord2f(0.0, 0.0); glVertex3f(-0.5, -0.5, 0.5)
    glTexCoord2f(1.0, 0.0); glVertex3f( 0.5, -0.5, 0.5)
    glTexCoord2f(1.0, 1.0); glVertex3f( 0.5,  0.5, 0.5)
    glTexCoord2f(0.0, 1.0); glVertex3f(-0.5,  0.5, 0.5)
    # 後面 (Z-)
    glTexCoord2f(1.0, 0.0); glVertex3f(-0.5, -0.5, -0.5)
    glTexCoord2f(1.0, 1.0); glVertex3f(-0.5,  0.5, -0.5)
    glTexCoord2f(0.0, 1.0); glVertex3f( 0.5,  0.5, -0.5)
    glTexCoord2f(0.0, 0.0); glVertex3f( 0.5, -0.5, -0.5)
    # 上面 (Y+)
    glTexCoord2f(0.0, 1.0); glVertex3f(-0.5,  0.5, -0.5)
    glTexCoord2f(0.0, 0.0); glVertex3f(-0.5,  0.5,  0.5)
    glTexCoord2f(1.0, 0.0); glVertex3f( 0.5,  0.5,  0.5)
    glTexCoord2f(1.0, 1.0); glVertex3f( 0.5,  0.5, -0.5)
    # 下面 (Y-)
    glTexCoord2f(1.0, 1.0); glVertex3f(-0.5, -0.5, -0.5)
    glTexCoord2f(0.0, 1.0); glVertex3f( 0.5, -0.5, -0.5)
    glTexCoord2f(0.0, 0.0); glVertex3f( 0.5, -0.5,  0.5)
    glTexCoord2f(1.0, 0.0); glVertex3f(-0.5, -0.5,  0.5)
    # 右面 (X+)
    glTexCoord2f(1.0, 0.0); glVertex3f( 0.5, -0.5, -0.5)
    glTexCoord2f(1.0, 1.0); glVertex3f( 0.5,  0.5, -0.5)
    glTexCoord2f(0.0, 1.0); glVertex3f( 0.5,  0.5,  0.5)
    glTexCoord2f(0.0, 0.0); glVertex3f( 0.5, -0.5,  0.5)
    # 左面 (X-)
    glTexCoord2f(0.0, 0.0); glVertex3f(-0.5, -0.5, -0.5)
    glTexCoord2f(1.0, 0.0); glVertex3f(-0.5, -0.5,  0.5)
    glTexCoord2f(1.0, 1.0); glVertex3f(-0.5,  0.5,  0.5)
    glTexCoord2f(0.0, 1.0); glVertex3f(-0.5,  0.5, -0.5)
    glEnd()

    glPopMatrix()
    glBindTexture(texture.target, 0)


@window.event
def on_draw():
    window.clear()
    
    # 3D描画モード
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(75, window.width / window.height, 0.1, 100.0)

    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()

    glRotatef(-camera_rot_x, 1, 0, 0)
    glRotatef(-camera_rot_y, 0, 1, 0)
    glTranslatef(-camera_x, -camera_y, -camera_z)

    player_cx, player_cy, player_cz = int(camera_x), int(camera_y - EYE_HEIGHT_OFFSET), int(camera_z)
    render_distance_blocks = 16 * 8

    for pos_str, block_id in world_data.items():
        x, y, z = map(int, pos_str.split(','))
        
        dist_sq = (x - player_cx)**2 + (y - player_cy)**2 + (z - player_cz)**2
        if dist_sq < render_distance_blocks**2:
            draw_block(x, y, z, block_id)

    # 2D描画モード (UI用)
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluOrtho2D(0, window.width, 0, window.height)

    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()

    draw_hotbar()

@window.event
def on_mouse_motion(x, y, dx, dy):
    global camera_rot_y, camera_rot_x
    camera_rot_y += dx * mouse_sensitivity
    camera_rot_x += dy * mouse_sensitivity
    if camera_rot_x > 90: camera_rot_x = 90
    if camera_rot_x < -90: camera_rot_x = -90

@window.event
def on_key_press(symbol, modifiers):
    global selected_slot
    # 数字キー1-9でスロット選択
    if pyglet.window.key._1 <= symbol <= pyglet.window.key._9:
        slot_index = symbol - pyglet.window.key._1
        if slot_index < INVENTORY_SLOT_COUNT:
            selected_slot = slot_index
            print(f"Selected slot: {selected_slot + 1}")

# --- ブロックの設置・破壊 (Raycasting) ---
def get_looked_at_block_and_face():
    """プレイヤーの視線が当たっているブロックとその面を特定する"""
    yaw_rad = math.radians(camera_rot_y)
    pitch_rad = math.radians(camera_rot_x)

    front_x = math.sin(yaw_rad) * math.cos(pitch_rad)
    front_y = -math.sin(pitch_rad)
    front_z = -math.cos(yaw_rad) * math.cos(pitch_rad)
    
    ray_start = (camera_x, camera_y, camera_z)
    
    step_size = 0.1
    max_distance = 8.0

    current_x, current_y, current_z = ray_start
    
    last_block_pos = None
    
    for _ in range(int(max_distance / step_size)):
        block_x = int(math.floor(current_x))
        block_y = int(math.floor(current_y))
        block_z = int(math.floor(current_z))
        
        current_block_pos = (block_x, block_y, block_z)
        pos_key = f"{block_x},{block_y},{block_z}"
        
        if get_block_at_coords(block_x, block_y, block_z) != BLOCK_IDENTIFIER_TO_ID["minecraft:air"]:
            if last_block_pos:
                face_normal = (
                    block_x - last_block_pos[0],
                    block_y - last_block_pos[1],
                    block_z - last_block_pos[2]
                )
            else:
                face_normal = (-int(round(front_x)), -int(round(front_y)), -int(round(front_z)))
                
            mag = math.sqrt(face_normal[0]**2 + face_normal[1]**2 + face_normal[2]**2)
            if mag != 0:
                face_normal = (face_normal[0]/mag, face_normal[1]/mag, face_normal[2]/mag)
            else:
                face_normal = (0,0,0)
            
            return current_block_pos, face_normal
        
        current_x += front_x * step_size
        current_y += front_y * step_size
        current_z += front_z * step_size
        
        if last_block_pos is None or current_block_pos != last_block_pos:
            last_block_pos = current_block_pos

    return None, None


@window.event
def on_mouse_press(x, y, button, modifiers):
    block_pos, face_normal = get_looked_at_block_and_face()
    if block_pos:
        if button == pyglet.window.mouse.LEFT: # 左クリックで破壊
            pos_key = f"{block_pos[0]},{block_pos[1]},{block_pos[2]}"
            broken_block_id = world_data.get(pos_key, BLOCK_IDENTIFIER_TO_ID["minecraft:air"])
            if broken_block_id != BLOCK_IDENTIFIER_TO_ID["minecraft:air"]:
                world_data[pos_key] = BLOCK_IDENTIFIER_TO_ID["minecraft:air"]
                print(f"Broke block at {block_pos}")
                add_item_to_inventory(broken_block_id)
                save_world_blocks()
                save_player_inventory()
        elif button == pyglet.window.mouse.RIGHT and face_normal: # 右クリックで設置
            place_x = block_pos[0] + int(round(face_normal[0]))
            place_y = block_pos[1] + int(round(face_normal[1]))
            place_z = block_pos[2] + int(round(face_normal[2]))
            
            # プレイヤーのバウンディングボックス
            player_min_x = camera_x - PLAYER_WIDTH / 2
            player_max_x = camera_x + PLAYER_WIDTH / 2
            player_min_y = camera_y - EYE_HEIGHT_OFFSET
            player_max_y = camera_y + (PLAYER_HEIGHT - EYE_HEIGHT_OFFSET)
            player_min_z = camera_z - PLAYER_WIDTH / 2
            player_max_z = camera_z + PLAYER_WIDTH / 2

            # 設置しようとしているブロックのAABB
            block_min_x, block_max_x = place_x, place_x + 1
            block_min_y, block_max_y = place_y, place_y + 1
            block_min_z, block_max_z = place_z, place_z + 1

            # AABB衝突判定
            is_overlapping_player = (
                player_min_x < block_max_x and player_max_x > block_min_x and
                player_min_y < block_max_y and player_max_y > block_min_y and
                player_min_z < block_max_z and player_max_z > block_min_z
            )
            
            if not is_overlapping_player:
                if selected_slot < len(player_inventory) and player_inventory[selected_slot]["count"] > 0:
                    block_to_place_id = player_inventory[selected_slot]["id"]
                    
                    if block_to_place_id != BLOCK_IDENTIFIER_TO_ID["minecraft:air"]:
                        pos_key = f"{place_x},{place_y},{place_z}"
                        world_data[pos_key] = block_to_place_id
                        player_inventory[selected_slot]["count"] -= 1
                        print(f"Placed block {BLOCK_ID_TO_IDENTIFIER.get(block_to_place_id)} at {place_x},{place_y},{place_z}")
                        save_world_blocks()
                        save_player_inventory()
                    else:
                        print("Selected slot is empty or contains air block.")
                else:
                    print("No block selected or selected slot is empty.")
            else:
                print("Cannot place block inside player.")

# --- インベントリヘルパー関数 ---
def add_item_to_inventory(block_id):
    """
    指定されたブロックIDをインベントリに追加する。
    スタック可能であれば既存のスタックに加える。
    """
    if block_id == BLOCK_IDENTIFIER_TO_ID["minecraft:air"]:
        return

    for item in player_inventory:
        if item["id"] == block_id and item["count"] < ITEM_STACK_LIMIT:
            item["count"] += 1
            print(f"Added 1 {BLOCK_ID_TO_IDENTIFIER.get(block_id)} to inventory. Count: {item['count']}")
            return

    for i in range(INVENTORY_SLOT_COUNT):
        if player_inventory[i]["id"] == BLOCK_IDENTIFIER_TO_ID["minecraft:air"] or player_inventory[i]["count"] == 0:
            player_inventory[i] = {"id": block_id, "count": 1}
            print(f"Added 1 {BLOCK_ID_TO_IDENTIFIER.get(block_id)} to new slot {i}. Count: 1")
            return
    
    print(f"Inventory full! Could not add {BLOCK_ID_TO_IDENTIFIER.get(block_id)}.")

# --- UI描画関数 ---
def draw_hotbar():
    """ホットバーを画面下部に描画する"""
    slot_size = 64
    padding = 8
    total_width = INVENTORY_SLOT_COUNT * (slot_size + padding) - padding
    start_x = (window.width - total_width) / 2
    start_y = 20

    for i in range(INVENTORY_SLOT_COUNT):
        x = start_x + i * (slot_size + padding)
        y = start_y

        # スロットの背景 (半透明の黒)
        glColor4f(0.0, 0.0, 0.0, 0.5)
        glRectf(x, y, x + slot_size, y + slot_size)

        # 選択中のスロットのハイライト
        if i == selected_slot:
            glColor4f(1.0, 1.0, 1.0, 0.8)
            glLineWidth(3)
            glBegin(GL_LINE_LOOP)
            glVertex2f(x, y)
            glVertex2f(x + slot_size, y)
            glVertex2f(x + slot_size, y + slot_size)
            glVertex2f(x, y + slot_size)
            glEnd()

        # スロット内のアイテムを描画
        if i < len(player_inventory) and player_inventory[i]["count"] > 0:
            item_id = player_inventory[i]["id"]
            item_count = player_inventory[i]["count"]
            
            identifier = BLOCK_ID_TO_IDENTIFIER.get(item_id)
            if identifier and identifier in BLOCK_DEFINITIONS:
                block_props = BLOCK_DEFINITIONS[identifier]
                texture_key = block_props.get("texture_key")
                
                if texture_key and texture_key in textures:
                    texture = textures[texture_key]
                    glBindTexture(texture.target, texture.id)
                    glColor4f(1.0, 1.0, 1.0, 1.0)
                    
                    tex_draw_size = slot_size * 0.8
                    tex_offset = (slot_size - tex_draw_size) / 2
                    glBegin(GL_QUADS)
                    glTexCoord2f(0.0, 0.0); glVertex2f(x + tex_offset, y + tex_offset)
                    glTexCoord2f(1.0, 0.0); glVertex2f(x + tex_offset + tex_draw_size, y + tex_offset)
                    glTexCoord2f(1.0, 1.0); glVertex2f(x + tex_offset + tex_draw_size, y + tex_offset + tex_draw_size)
                    glTexCoord2f(0.0, 1.0); glVertex2f(x + tex_offset, y + tex_offset + tex_draw_size)
                    glEnd()
                    glBindTexture(texture.target, 0)

                    count_label = pyglet.text.Label(str(item_count),
                                                    font_name='Arial',
                                                    font_size=16,
                                                    x=x + slot_size - 10, y=y + 5,
                                                    anchor_x='right', anchor_y='bottom',
                                                    color=(255, 255, 255, 255))
                    count_label.draw()


# --- 衝突判定ヘルパー関数 ---
def get_block_at_coords(x, y, z):
    """指定された座標のブロックIDを返す"""
    return world_data.get(f"{int(x)},{int(y)},{int(z)}", BLOCK_IDENTIFIER_TO_ID["minecraft:air"])

def is_solid(block_id):
    """ブロックIDがソリッドブロックかどうかを判定する"""
    identifier = BLOCK_ID_TO_IDENTIFIER.get(block_id)
    if identifier and identifier in BLOCK_DEFINITIONS:
        return BLOCK_DEFINITIONS[identifier].get('is_solid', False)
    return False

def is_falling_block(block_id):
    """ブロックIDが落下ブロックかどうかを判定する"""
    return block_id in FALLING_BLOCK_IDS


def get_player_bounding_box_blocks():
    """プレイヤーのバウンディングボックスが占めるブロックの座標リストを返す"""
    player_min_x = camera_x - PLAYER_WIDTH / 2
    player_max_x = camera_x + PLAYER_WIDTH / 2
    player_min_y = camera_y - EYE_HEIGHT_OFFSET
    player_max_y = camera_y + (PLAYER_HEIGHT - EYE_HEIGHT_OFFSET)
    player_min_z = camera_z - PLAYER_WIDTH / 2
    player_max_z = camera_z + PLAYER_WIDTH / 2

    occupied_blocks = []
    for x in range(int(math.floor(player_min_x)), int(math.ceil(player_max_x))):
        for y in range(int(math.floor(player_min_y)), int(math.ceil(player_max_y))):
            for z in range(int(math.floor(player_min_z)), int(math.ceil(player_max_z))):
                occupied_blocks.append((x, y, z))
    return occupied_blocks

def handle_suffocation(dt):
    """
    プレイヤーがブロックに埋まっているかチェックし、
    埋まっていればスライド移動を試みるか、窒息ダメージを与える。
    """
    global player_hp, suffocation_timer, camera_x, camera_y, camera_z

    is_suffocating = False
    occupied_blocks = get_player_bounding_box_blocks()
    
    head_block_y = int(math.floor(camera_y + (PLAYER_HEIGHT - EYE_HEIGHT_OFFSET) - 0.1))
    
    for bx, by, bz in occupied_blocks:
        if by == head_block_y and is_solid(get_block_at_coords(bx, by, bz)):
            is_suffocating = True
            break
    
    if is_suffocating:
        suffocation_timer += dt
        if suffocation_timer >= SUFFOCATION_DAMAGE_INTERVAL:
            player_hp -= 1.0
            print(f"Suffocating! Player HP: {player_hp}")
            suffocation_timer = 0.0

            if player_hp <= 0:
                print("Player suffocated! Game Over.")
                pyglet.app.exit()
                return

            search_offsets = [
                (1, 0), (-1, 0), (0, 1), (0, -1),
                (1, 1), (1, -1), (-1, 1), (-1, -1)
            ]
            
            found_safe_spot = False
            for dx_offset, dz_offset in search_offsets:
                test_x = int(math.floor(camera_x)) + dx_offset
                test_z = int(math.floor(camera_z)) + dz_offset
                
                for dy_offset in range(-1, 2):
                    test_y_base = int(math.floor(camera_y - EYE_HEIGHT_OFFSET)) + dy_offset
                    
                    is_clear = True
                    for y_check in range(test_y_base, int(test_y_base + PLAYER_HEIGHT + 0.1)):
                        if is_solid(get_block_at_coords(test_x, y_check, test_z)):
                            is_clear = False
                            break
                    
                    if is_clear:
                        camera_x = test_x + PLAYER_WIDTH / 2
                        camera_y = test_y_base + EYE_HEIGHT_OFFSET + 0.001
                        camera_z = test_z + PLAYER_WIDTH / 2
                        velocity_y = 0
                        on_ground = True
                        print(f"Player slid to safe spot: ({camera_x}, {camera_y}, {camera_z})")
                        found_safe_spot = True
                        suffocation_timer = 0.0
                        return
            
            if not found_safe_spot:
                print("No safe spot found to slide to.")
    else:
        suffocation_timer = 0.0


def check_collision_and_move(dx, dy, dz, dt):
    """
    プレイヤーの移動を試み、衝突があれば調整する。
    dtは時間差分
    """
    global camera_x, camera_y, camera_z, velocity_y, on_ground

    px_min = camera_x - PLAYER_WIDTH / 2
    px_max = camera_x + PLAYER_WIDTH / 2
    py_min = camera_y - EYE_HEIGHT_OFFSET
    py_max = camera_y + (PLAYER_HEIGHT - EYE_HEIGHT_OFFSET)
    pz_min = camera_z - PLAYER_WIDTH / 2
    pz_max = camera_z + PLAYER_WIDTH / 2

    # Y軸 (垂直方向)
    dy_actual = dy * dt
    
    if dy_actual < 0:
        block_y_at_feet = int(math.floor(py_min + dy_actual))
        
        collision_y = False
        for x_idx in range(int(math.floor(px_min)), int(math.ceil(px_max - 0.001))):
            for z_idx in range(int(math.floor(pz_min)), int(math.ceil(pz_max - 0.001))):
                if is_solid(get_block_at_coords(x_idx, block_y_at_feet, z_idx)):
                    camera_y = block_y_at_feet + EYE_HEIGHT_OFFSET + 0.001
                    velocity_y = 0.0
                    on_ground = True
                    dy_actual = 0
                    collision_y = True
                    break
            if collision_y: break
    elif dy_actual > 0:
        block_y_at_head = int(math.floor(py_max + dy_actual))
        
        collision_y = False
        for x_idx in range(int(math.floor(px_min)), int(math.ceil(px_max - 0.001))):
            for z_idx in range(int(math.floor(pz_min)), int(math.ceil(pz_max - 0.001))):
                if is_solid(get_block_at_coords(x_idx, block_y_at_head, z_idx)):
                    camera_y = block_y_at_head - (PLAYER_HEIGHT - EYE_HEIGHT_OFFSET) - 0.001
                    velocity_y = 0.0
                    dy_actual = 0
                    collision_y = True
                    break
            if collision_y: break

    camera_y += dy_actual
    
    # X軸 (水平方向)
    dx_actual = dx * dt
    if dx_actual != 0:
        y_blocks_to_check_horizontal = range(int(math.floor(py_min)), int(math.ceil(py_max - 0.001)))
        
        collision_x = False
        for y_idx in y_blocks_to_check_horizontal:
            for z_idx in range(int(math.floor(pz_min)), int(math.ceil(pz_max - 0.001))):
                block_x_check = int(math.floor(px_min + dx_actual)) if dx_actual < 0 else int(math.floor(px_max + dx_actual))
                if is_solid(get_block_at_coords(block_x_check, y_idx, z_idx)):
                    collision_x = True
                    break
            if collision_x: break
        
        if collision_x:
            dx_actual = 0
    camera_x += dx_actual

    # Z軸 (水平方向)
    dz_actual = dz * dt
    if dz_actual != 0:
        y_blocks_to_check_horizontal = range(int(math.floor(py_min)), int(math.ceil(py_max - 0.001)))

        collision_z = False
        for y_idx in y_blocks_to_check_horizontal:
            for x_idx in range(int(math.floor(px_min)), int(math.ceil(px_max - 0.001))):
                block_z_check = int(math.floor(pz_min + dz_actual)) if dz_actual < 0 else int(math.floor(pz_max + dz_actual))
                if is_solid(get_block_at_coords(x_idx, y_idx, block_z_check)):
                    collision_z = True
                    break
            if collision_z: break
        
        if collision_z:
            dz_actual = 0
    camera_z += dz_actual

    # 地面判定の更新
    temp_on_ground = False
    check_y = int(math.floor(camera_y - EYE_HEIGHT_OFFSET - 0.01))
    
    px_min_int = int(math.floor(camera_x - PLAYER_WIDTH / 2))
    px_max_int = int(math.ceil(camera_x + PLAYER_WIDTH / 2 - 0.001))
    pz_min_int = int(math.floor(camera_z - PLAYER_WIDTH / 2))
    pz_max_int = int(math.ceil(camera_z + PLAYER_WIDTH / 2 - 0.001))

    for x_idx in range(px_min_int, px_max_int):
        for z_idx in range(pz_min_int, pz_max_int):
            if is_solid(get_block_at_coords(x_idx, check_y, z_idx)):
                temp_on_ground = True
                break
        if temp_on_ground:
            break
    on_ground = temp_on_ground


def update(dt):
    """ゲームの状態を毎フレーム更新する"""
    global camera_x, camera_y, camera_z, velocity_x, velocity_y, velocity_z, on_ground, suffocation_timer

    move_speed = 5.0
    
    # 重力を適用
    velocity_y -= GRAVITY * dt

    # キー入力による水平方向の速度計算
    target_vx, target_vz = 0.0, 0.0

    yaw_rad = math.radians(camera_rot_y)
    
    forward_x = math.sin(yaw_rad)
    forward_z = -math.cos(yaw_rad)
    
    right_x = math.sin(math.radians(camera_rot_y + 90))
    right_z = -math.cos(math.radians(camera_rot_y + 90))

    if keys[pyglet.window.key.W]:
        target_vx += forward_x * move_speed
        target_vz += forward_z * move_speed
    if keys[pyglet.window.key.S]:
        target_vx -= forward_x * move_speed
        target_vz -= forward_z * move_speed
    if keys[pyglet.window.key.A]:
        target_vx -= right_x * move_speed
        target_vz -= right_z * move_speed
    if keys[pyglet.window.key.D]:
        target_vx += right_x * move_speed
        target_vz += right_z * move_speed

    if (target_vx != 0 or target_vz != 0):
        norm = math.sqrt(target_vx**2 + target_vz**2)
        target_vx = (target_vx / norm) * move_speed
        target_vz = (target_vz / norm) * move_speed

    velocity_x = target_vx
    velocity_z = target_vz

    # ジャンプ
    if keys[pyglet.window.key.SPACE] and on_ground:
        velocity_y = JUMP_SPEED
        on_ground = False

    # 衝突判定と移動
    check_collision_and_move(velocity_x, 0, 0, dt)
    check_collision_and_move(0, 0, velocity_z, dt)
    check_collision_and_move(0, velocity_y, 0, dt)

    # 窒息ダメージの処理
    handle_suffocation(dt)

    # 落下ブロックの処理 (簡易版: 毎フレーム全ブロックをチェック)
    blocks_to_update = []
    for pos_str, block_id in list(world_data.items()):
        if is_falling_block(block_id):
            x, y, z = map(int, pos_str.split(','))
            if get_block_at_coords(x, y - 1, z) == BLOCK_IDENTIFIER_TO_ID["minecraft:air"]:
                blocks_to_update.append((x, y, z, block_id))
    
    for x, y, z, block_id in blocks_to_update:
        world_data[f"{x},{y},{z}"] = BLOCK_IDENTIFIER_TO_ID["minecraft:air"]
        world_data[f"{x},{y-1},{z}"] = block_id
        print(f"Falling block {BLOCK_ID_TO_IDENTIFIER.get(block_id)} moved from ({x},{y},{z}) to ({x},{y-1},{z})")
    
    if blocks_to_update:
        save_world_blocks()

    # プレイヤー位置の保存（例：5秒に1回）
    if update.counter % (5 * 60) == 0:
        save_player_position()
        save_player_inventory()
    update.counter += 1

update.counter = 0

pyglet.clock.schedule_interval(update, 1/60.0)

window.set_mouse_visible(False)
window.set_exclusive_mouse(True)

# --- ゲーム開始時のパック読み込み ---
load_default_textures()

PACKS_GITHUB_PATH = 'packs'
github_packs_list = list_github_directory(PACKS_GITHUB_PATH)

if github_packs_list:
    for item in github_packs_list:
        if item['type'] == 'file' and item['name'].endswith(('.mcpack', '.mcaddon')):
            pack_filename = item['name']
            pack_github_full_path = f"{PACKS_GITHUB_PATH}/{pack_filename}"
            print(f"Attempting to download pack from GitHub: {pack_github_full_path}")
            
            pack_content_bytes = download_github_raw_file(pack_github_full_path)
            if pack_content_bytes:
                load_and_process_pack(pack_filename, pack_content_bytes)
            else:
                print(f"Could not download pack: {pack_filename}. Skipping.")
else:
    print(f"No packs found in GitHub directory '{PACKS_GITHUB_PATH}'.")


# ゲーム開始時にワールドデータとインベントリをロード
load_world_blocks()
load_player_inventory()

# アプリケーションの実行
pyglet.app.run()

print("\n--- Game simulation ends ---")
# 実際にはここでゲームループが実行されます
# 簡単な例として、ゲームがすぐに終了しないようにユーザー入力を待つ
input("Press Enter to exit game simulation...")

