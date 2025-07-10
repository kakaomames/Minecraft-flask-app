import os
import pyglet
from pyglet.gl import *
import requests
import base64
from io import BytesIO
import traceback
import math
import json
import pyglet.media
import random
import time
from collections import deque # ★追加: 光伝播のためのdequeをインポート

# 環境変数を取得
WORLD_NAME = os.getenv('WORLD_NAME', 'Default World')
PLAYER_UUID = os.getenv('PLAYER_UUID', 'default-player-uuid')
WORLD_UUID = os.getenv('WORLD_UUID', 'default-world-uuid')
RESOURCE_PACK_PATHS_STR = os.getenv('RESOURCE_PACK_PATHS', '')
BEHAVIOR_PACKS_PATHS_STR = os.getenv('BEHAVIOR_PACKS_PATHS', '')
WORLD_SEED = os.getenv('WORLD_SEED', '')

# GitHub APIの認証情報も環境変数から取得
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_OWNER = os.getenv('GITHUB_OWNER')
GITHUB_REPO = os.getenv('GITHUB_REPO')

print(f"ゲームを開始します:")
print(f"  ワールド名: {WORLD_NAME}")
print(f"  プレイヤーUUID: {PLAYER_UUID}")
print(f"  ワールドUUID: {WORLD_UUID}")
print(f"  ワールドシード: {WORLD_SEED if WORLD_SEED else 'ランダム'}")

# パック情報を処理
resource_pack_paths = []
if RESOURCE_PACK_PATHS_STR:
    resource_pack_paths = RESOURCE_PACK_PATHS_STR.split(',')
    print(f"  選択されたリソースパックのGitHubパス: {resource_pack_paths}")
else:
    print("  リソースパックは選択されていません。")

behavior_pack_paths = []
if BEHAVIOR_PACKS_PATHS_STR:
    behavior_pack_paths = BEHAVIOR_PACKS_PATHS_STR.split(',')
    print(f"  選択されたビヘイビアパックのGitHubパス: {behavior_pack_paths}")
else:
    print("  ビヘイビアパックは選択されていません。")

# --- GitHubからファイルをバイトデータとしてダウンロードするヘルパー関数 ---
def download_github_file_content(github_path):
    """
    GitHubリポジリから指定されたパスのファイルコンテンツをバイトデータとしてダウンロードします。
    """
    if not GITHUB_TOKEN or not GITHUB_OWNER or not GITHUB_REPO:
        print("エラー: GitHubの認証情報がgame.pyで利用できません。ファイルをダウンロードできません。")
        return None

    url = f'https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{github_path}'
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.com.v3.raw',
        'User-Agent': 'Pyglet-Minecraft-Game'
    }

    try:
        print(f"DEBUG: GitHubからダウンロードを試行中: {url}")
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            print(f"DEBUG: {github_path} のダウンロードに成功しました。")
            return response.content
        elif response.status_code == 404:
            print(f"WARNING: GitHubにファイルが見つかりません: {github_path}")
        else:
            print(f"ERROR: {github_path} のダウンロードに失敗しました。ステータス: {response.status_code}, レスポンス: {response.text}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"ERROR: GitHubダウンロード中にネットワークエラーが発生しました {github_path}: {e}")
        traceback.print_exc()
        return None

# --- グローバルなテクスチャ辞書 ---
textures = {}

# --- ワールドデータとブロックタイプ ---
world_data = {}
WORLD_SAVE_FILE = 'world_save.json' # ワールドの保存ファイル名

# ドロップされたアイテムのリスト
# 各要素は {'position': (x, y, z), 'type': 'block_type', 'rotation_angle': float}
dropped_items = []

# ブロックタイプ名 (テクスチャファイル名と対応させる)
BLOCK_TYPES = {
    'dirt': {
        'top': 'dirt.png',
        'bottom': 'dirt.png',
        'side': 'dirt.png'
    },
    'grass': {
        'top': 'grass_block_top.png',
        'bottom': 'dirt.png',
        'side': 'grass_block_side.png'
    },
    'stone': {
        'top': 'stone.png',
        'bottom': 'stone.png',
        'side': 'stone.png'
    },
    'cobblestone': {
        'top': 'cobblestone.png',
        'bottom': 'cobblestone.png',
        'side': 'cobblestone.png'
    },
    'planks_oak': {
        'top': 'oak_planks.png',
        'bottom': 'oak_planks.png',
        'side': 'oak_planks.png'
    },
    'crafting_table': {
        'top': 'crafting_table_top.png',
        'bottom': 'oak_planks.png',
        'side': 'crafting_table_side.png'
    },
    'stick': { # スティックはブロックではないが、アイテムとして扱うためダミーテクスチャ
        'top': 'stick.png',
        'bottom': 'stick.png',
        'side': 'stick.png'
    },
    'pickaxe': {
        'top': 'iron_pickaxe.png', # 仮のテクスチャ名、実際のリソースパックに合わせてください
        'bottom': 'iron_pickaxe.png',
        'side': 'iron_pickaxe.png'
    },
    'shovel': {
        'top': 'iron_shovel.png', # 仮のテクスチャ名、実際のリソースパックに合わせてください
        'bottom': 'iron_shovel.png',
        'side': 'iron_shovel.png'
    },
    # ★追加: トーチブロックの定義
    'torch': {
        'top': 'torch.png',
        'bottom': 'torch.png',
        'side': 'torch.png'
    }
}

# ブロックの硬さ (破壊にかかる時間の基準)
BLOCK_HARDNESS = {
    'dirt': 0.5,
    'grass': 0.6,
    'stone': 1.5,
    'cobblestone': 2.0,
    'planks_oak': 1.0,
    'crafting_table': 1.0,
    'stick': 0.1, # アイテムは通常破壊されないが、念のため
    'pickaxe': 0.1,
    'shovel': 0.1,
    'torch': 0.1 # トーチは簡単に壊れる
}

# ツールごとのブロック破壊効率 (乗数)
TOOL_EFFECTIVENESS = {
    'pickaxe': {
        'stone': 2.0, # ピッケルは石系のブロックに2倍の効果
        'cobblestone': 2.0,
    },
    'shovel': {
        'dirt': 2.0, # シャベルは土系のブロックに2倍の効果
        'grass': 2.0,
    },
    # 他のツールやブロックタイプを追加可能
}

# ブロック破壊の進行状況を管理する変数
block_breaking_target = None # (x, y, z) tuple of the block currently being broken
block_breaking_progress = 0.0 # Current progress (0.0 to 1.0)
BREAK_TIME_PER_HARDNESS = 0.5 # 硬さ1.0のブロックをツールなしで壊すのにかかる基準時間 (秒)

# Pygletウィンドウ設定
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
window = pyglet.window.Window(width=WINDOW_WIDTH, height=WINDOW_HEIGHT, 
                              caption=f"Minecraft風ゲーム - {WORLD_NAME}", resizable=True)

# --- カメラとプレイヤーの状態変数 ---
x, y, z = 8.0, 5.0, 8.0 # プレイヤーの初期位置
yaw = -45.0
pitch = -30.0

PLAYER_SPEED = 5.0
GRAVITY = 20.0 # 重力の強さ
JUMP_SPEED = 8.0 # ジャンプの初速度
TERMINAL_VELOCITY = -50.0 # 落下速度の最大値

dy = 0.0 # プレイヤーの垂直方向の速度
on_ground = False # プレイヤーが地面にいるかどうか

# プレイヤーの衝突判定のためのサイズ (Minecraftのプレイヤーは高さ1.8ブロック、幅0.6ブロック)
PLAYER_HEIGHT = 1.8
PLAYER_WIDTH = 0.6

# --- インベントリ関連変数 ---
# ほとんどのアイテムの最大スタックサイズ
MAX_STACK_SIZE = 64 

# プレイヤーのインベントリ (ホットバーとそれ以外のスロット)
# キーはブロックタイプ名、値は数量
inventory_counts = {
    'grass': 1, # 初期アイテム数を減らしてスタックテストを容易にする
    'dirt': 1,
    'stone': 1,
    'cobblestone': 1,
    'planks_oak': 1,
    'crafting_table': 0,
    'stick': 0,
    'pickaxe': 1,
    'shovel': 1,
    'torch': 4 # ★追加: 初期インベントリにトーチを4つ追加
}
# ホットバーに表示されるブロックタイプ (インベントリにあるものから選択)
hotbar_slots = ['grass', 'dirt', 'stone', 'cobblestone', 'planks_oak', 'pickaxe', 'shovel', 'torch', None] # 9スロット

# メインインベントリスロット (3x9 = 27スロット)
# 各要素はアイテムタイプ名、Noneは空スロット
main_inventory_slots = [None] * 27 
# 初期アイテムをメインインベントリに追加 (例: 木材)
if 'planks_oak' in inventory_counts and inventory_counts['planks_oak'] > 0:
    main_inventory_slots[0] = 'planks_oak' # 最初のスロットに木材を配置

selected_inventory_slot = 0 # 現在選択されているホットバースロットのインデックス (0から始まる)

is_inventory_open = False # インベントリUIが表示されているか

crafting_grid_size = 2 # 2x2のクラフトグリッド
crafting_input_slots = [None] * (crafting_grid_size * crafting_grid_size) # クラフト入力スロットのアイテムタイプ
crafting_output_item = None # クラフト結果のアイテムタイプ
crafting_output_count = 0 # クラフト結果の数量

current_drag_item = None # ドラッグ中のアイテムタイプ
current_drag_count = 0 # ドラッグ中のアイテム数量
drag_from_slot_type = None # 'hotbar', 'main_inventory', 'crafting_input', 'crafting_output'
drag_from_slot_index = -1 # 元のスロットのインデックス

keys = pyglet.window.key.KeyStateHandler()
window.push_handlers(keys)

DEFAULT_KEY_BINDINGS = {
    'forward': pyglet.window.key.W,
    'backward': pyglet.window.key.S,
    'strafe_left': pyglet.window.key.A,
    'strafe_right': pyglet.window.key.D,
    'jump': pyglet.window.key.SPACE,
    'crouch': pyglet.window.key.LSHIFT,
    'toggle_inventory': pyglet.window.key.E,
}

# --- 昼夜サイクル関連変数 ---
# 1日の長さ (秒) - 例: 600秒 (10分) で1日
DAY_LENGTH_SECONDS = 600 
current_day_time = DAY_LENGTH_SECONDS / 4 # 初期時間を昼間の始まりに設定 (0.0 - DAY_LENGTH_SECONDS)

# 昼間の色 (RGB 0.0-1.0)
DAY_COLOR = (0.53, 0.81, 0.98) # スカイブルー
# 夜間の色 (RGB 0.0-1.0)
NIGHT_COLOR = (0.05, 0.05, 0.2) # 濃い青
# 夕焼け/朝焼けの色 (RGB 0.0-1.0)
SUNSET_COLOR = (1.0, 0.5, 0.2) # オレンジ

# --- サウンド関連変数 ---
background_music_player = None
sound_effects = {}
breaking_sound_player = None # ブロック破壊中のループサウンド用プレイヤー

# サウンドファイル名とリソースパック内のパス
SOUND_FILES = {
    'background_music': 'sounds/music/background_music.ogg',
    'break_block': 'sounds/dig/generic.ogg', # 破壊中のループサウンド
    'place_block': 'sounds/dig/place.ogg',   # 設置サウンド
    'jump': 'sounds/player/jump.ogg',
    'pickup_item': 'sounds/random/pop.ogg',
    'craft': 'sounds/random/anvil_use.ogg',
}

# クラフトレシピ定義
CRAFTING_RECIPES = {
    # 作業台 (2x2)
    # 4つの木材の板 -> 作業台1つ
    ((None, None),
     (None, None),
     ('planks_oak', 'planks_oak'),
     ('planks_oak', 'planks_oak')): ('crafting_table', 1),

    # 棒 (2x2)
    # 2つの木材の板 -> 棒4つ
    ((None, None),
     (None, None),
     ('planks_oak', None),
     ('planks_oak', None)): ('stick', 4),
    
    # ピッケルのレシピ (例: 棒2つ、石3つ)
    ((None, None),
     ('stone', 'stone'),
     ('stone', None),
     (None, 'stick'),
     (None, 'stick')): ('pickaxe', 1),
    
    # シャベルのレシピ (例: 棒2つ、石1つ)
    ((None, None),
     (None, None),
     ('stone', None),
     ('stick', None),
     ('stick', None)): ('shovel', 1),

    # ★追加: トーチのレシピ (1つの棒と1つの木材の板 -> 4つのトーチ)
    ((None, None),
     (None, None),
     ('planks_oak', None),
     ('stick', None)): ('torch', 4),
}

# ★追加: 光源システム関連変数
MAX_LIGHT_LEVEL = 15 # 最大光レベル (Minecraftの基準)
block_light_levels = {} # 各ブロック位置の光レベルを格納する辞書

# --- ワールド生成関数 ---
def generate_layered_world(width, depth, layers):
    """
    指定されたサイズの多層ワールドを生成します。
    layers: [(height, block_type_name), ...] のリスト
    例: [(1, 'stone'), (3, 'dirt'), (1, 'grass')]
    """
    print(f"DEBUG: Generating a layered world of size {width}x{depth}...")
    
    # ワールドシードに基づいて乱数ジェネレータを初期化
    if WORLD_SEED:
        try:
            seed_value = int(WORLD_SEED)
        except ValueError:
            seed_value = sum(ord(c) for c in WORLD_SEED) # 文字列シードを数値に変換
        random.seed(seed_value)
        print(f"INFO: ワールドシード '{WORLD_SEED}' を使用して乱数ジェネレータを初期化しました。")
    else:
        # シードが指定されていない場合は、現在の時刻に基づいて初期化 (デフォルトの動作)
        random.seed(time.time())
        print("INFO: ワールドシードが指定されていないため、ランダムなワールドを生成します。")

    # 既存のワールドデータがあればクリア
    world_data.clear()

    # シンプルなパーリンノイズに基づく高さマップ生成 (簡易版)
    height_map = {}
    
    for x_coord in range(width):
        for z_coord in range(depth):
            # 2Dパーリンノイズ (簡易的な実装)
            height_val = int(random.random() * 5) + 3 # 3から7の範囲で高さを生成

            height_map[(x_coord, z_coord)] = height_val

            # 地形生成
            for y_coord in range(height_val):
                if y_coord == height_val - 1: # 最上層
                    world_data[(x_coord, y_coord, z_coord)] = 'grass'
                elif y_coord >= height_val - 4: # その下の数層
                    world_data[(x_coord, y_coord, z_coord)] = 'dirt'
                else: # それより下
                    world_data[(x_coord, y_coord, z_coord)] = 'stone'
    
    print(f"DEBUG: World generation complete. Total blocks: {len(world_data)}")

# --- ワールド保存関数 ---
def save_world():
    print(f"INFO: ワールドデータを '{WORLD_SAVE_FILE}' に保存しています...")
    try:
        # タプルのキーを文字列に変換（JSONのキーは文字列である必要があるため）
        serializable_world_data = {str(k): v for k, v in world_data.items()}
        # ドロップアイテムとインベントリも保存
        serializable_data = {
            'world_data': serializable_world_data,
            'player_position': (x, y, z),
            'player_rotation': (yaw, pitch),
            'inventory_counts': inventory_counts,
            'hotbar_slots': hotbar_slots,
            'main_inventory_slots': main_inventory_slots,
            'dropped_items': [{'position': item['position'], 'type': item['type'], 'rotation_angle': item['rotation_angle']} for item in dropped_items]
        }
        with open(WORLD_SAVE_FILE, 'w') as f:
            json.dump(serializable_data, f)
        print("INFO: ワールドデータの保存が完了しました。")
    except Exception as e:
        print(f"ERROR: ワールドデータの保存中にエラーが発生しました: {e}")
        traceback.print_exc()

# --- ワールド読み込み関数 ---
def load_world():
    global world_data, x, y, z, yaw, pitch, inventory_counts, dropped_items, hotbar_slots, main_inventory_slots
    print(f"INFO: ワールドデータを '{WORLD_SAVE_FILE}' から読み込んでいます...")
    if os.path.exists(WORLD_SAVE_FILE):
        try:
            with open(WORLD_SAVE_FILE, 'r') as f:
                loaded_data = json.load(f)
            
            # ワールドデータ
            world_data = {eval(k): v for k, v in loaded_data.get('world_data', {}).items()}
            print(f"INFO: ワールドデータの読み込みが完了しました。ブロック数: {len(world_data)}")

            # プレイヤーの位置と向き
            if 'player_position' in loaded_data:
                x, y, z = loaded_data['player_position']
            if 'player_rotation' in loaded_data:
                yaw, pitch = loaded_data['player_rotation']
            
            # インベントリ
            loaded_inventory_counts = loaded_data.get('inventory_counts', {})
            # ロードしたデータを既存のinventory_countsにマージ
            # ロードされたアイテムが既存のinventory_countsにない場合も追加
            for item_type, count in loaded_inventory_counts.items():
                inventory_counts[item_type] = count 

            # ホットバースロットとメインインベントリスロットの読み込み
            loaded_hotbar_slots = loaded_data.get('hotbar_slots', [])
            if len(loaded_hotbar_slots) == len(hotbar_slots):
                hotbar_slots[:] = loaded_hotbar_slots
            else:
                print("WARNING: ロードされたホットバースロットの数が一致しません。デフォルトを使用します。")

            loaded_main_inventory_slots = loaded_data.get('main_inventory_slots', [])
            if len(loaded_main_inventory_slots) == len(main_inventory_slots):
                main_inventory_slots[:] = loaded_main_inventory_slots
            else:
                print("WARNING: ロードされたメインインベントリスロットの数が一致しません。デフォルトを使用します。")

            # ドロップアイテム
            dropped_items = loaded_data.get('dropped_items', [])

        except json.JSONDecodeError as e:
            print(f"ERROR: ワールド保存ファイルの読み込み中にJSONデコードエラーが発生しました: {e}")
            print("INFO: 新しいワールドを生成します。")
            generate_layered_world(16, 16, [(1, 'stone'), (3, 'dirt'), (1, 'grass')])
        except Exception as e:
            print(f"ERROR: ワールドデータの読み込み中にエラーが発生しました: {e}")
            print("INFO: 新しいワールドを生成します。")
            traceback.print_exc()
            generate_layered_world(16, 16, [(1, 'stone'), (3, 'dirt'), (1, 'grass')])
    else:
        print("INFO: ワールド保存ファイルが見つかりませんでした。新しいワールドを生成します。")
        generate_layered_world(16, 16, [(1, 'stone'), (3, 'dirt'), (1, 'grass')])

# ★追加: 光レベル計算関数
def calculate_light_levels():
    """
    ワールド内のすべてのブロックの光レベルを再計算します。
    光源からBFSで光を伝播させます。
    """
    global block_light_levels
    block_light_levels.clear() # 既存の光レベルをクリア

    light_sources = []
    # すべての光源ブロックを特定 (現在はトーチのみ)
    for pos, block_type in world_data.items():
        if block_type == 'torch':
            light_sources.append((pos, MAX_LIGHT_LEVEL)) # (位置, 初期光レベル)

    q = deque(light_sources) # 光伝播のためのキュー
    
    while q:
        (x_b, y_b, z_b), current_light = q.popleft()
        
        # このブロックが既に同等以上の光レベルを持っている場合はスキップ
        if block_light_levels.get((x_b, y_b, z_b), 0) >= current_light:
            continue
            
        block_light_levels[(x_b, y_b, z_b)] = current_light # 光レベルを更新
        
        if current_light <= 1: # 光が0になるまで伝播
            continue
            
        # 隣接ブロックに光を伝播
        neighbors = [
            (x_b + 1, y_b, z_b), (x_b - 1, y_b, z_b),
            (x_b, y_b + 1, z_b), (x_b, y_b - 1, z_b),
            (x_b, y_b, z_b + 1), (x_b, y_b, z_b - 1)
        ]
        
        for nx, ny, nz in neighbors:
            neighbor_pos = (nx, ny, nz)
            # 新しい光レベルは現在の光レベルから1減らす
            new_light = current_light - 1
            
            # 隣接ブロックの現在の光レベルよりも新しい光レベルが高い場合のみキューに追加
            if block_light_levels.get(neighbor_pos, 0) < new_light:
                q.append((neighbor_pos, new_light))

    print(f"INFO: 光レベルが計算されました。明るいブロックの総数: {len(block_light_levels)}")


# --- ゲームの初期化 ---
def setup_game():
    print("\n--- ゲームの初期化 ---")

    # 必要なテクスチャをロード
    if resource_pack_paths:
        first_pack_path = resource_pack_paths[0]
        for block_type_name, texture_map in BLOCK_TYPES.items():
            for face, texture_filename in texture_map.items():
                github_texture_path = f"{first_pack_path}/textures/block/{texture_filename}"
                print(f"DEBUG: ロードを試行中: {github_texture_path}")
                texture_bytes = download_github_file_content(github_texture_path)
                if texture_bytes:
                    try:
                        textures[(block_type_name, face)] = pyglet.image.load(f'{texture_filename}', file=BytesIO(texture_bytes)).get_texture()
                        print(f"INFO: {github_texture_path} のロードに成功しました。")
                    except Exception as e:
                        print(f"ERROR: {github_texture_path} から画像をロードできませんでした: {e}")
                        traceback.print_exc()
                        textures[(block_type_name, face)] = pyglet.image.create(32, 32, pyglet.image.SolidColorImagePattern((255, 0, 0, 255))).get_texture()
                else:
                    print(f"WARNING: {github_texture_path} のバイトデータがダウンロードされませんでした。フォールバックの赤色テクスチャを使用します。")
                    textures[(block_type_name, face)] = pyglet.image.create(32, 32, pyglet.image.SolidColorImagePattern((255, 0, 0, 255))).get_texture()
    else:
        print("WARNING: リソースパックが選択されていません。フォールバックの緑色テクスチャを使用します。")
        for block_type_name, texture_map in BLOCK_TYPES.items():
            for face in texture_map.keys():
                textures[(block_type_name, face)] = pyglet.image.create(32, 32, pyglet.image.SolidColorImagePattern((0, 255, 0, 255))).get_texture()

    load_world() # ワールド生成の代わりに読み込みを試みる
    calculate_light_levels() # ★追加: ワールドロード後に光レベルを計算

    glEnable(GL_DEPTH_TEST)
    glEnable(GL_CULL_FACE)
    glEnable(GL_TEXTURE_2D)
    
    window.set_mouse_visible(False)
    window.set_exclusive_mouse(True)

    # サウンドのロードと再生
    global background_music_player, sound_effects
    if resource_pack_paths:
        first_pack_path = resource_pack_paths[0] # サウンドも最初のリソースパックからロード
        for sound_name, sound_path_in_pack in SOUND_FILES.items():
            github_sound_path = f"{first_pack_path}/{sound_path_in_pack}"
            print(f"DEBUG: サウンドロードを試行中: {github_sound_path}")
            sound_bytes = download_github_file_content(github_sound_path)
            if sound_bytes:
                try:
                    # ストリーミングをFalseに設定し、メモリにロードする
                    source = pyglet.media.load(f'{sound_path_in_pack}', file=BytesIO(sound_bytes), streaming=False)
                    if sound_name == 'background_music':
                        background_music_player = pyglet.media.Player()
                        background_music_player.queue(source)
                        background_music_player.loop = True
                        background_music_player.play()
                        print(f"INFO: 背景音楽 {github_sound_path} の再生を開始しました。")
                    else:
                        sound_effects[sound_name] = source
                        print(f"INFO: サウンドエフェクト {github_sound_path} のロードに成功しました。")
                except Exception as e:
                    print(f"ERROR: {github_sound_path} からサウンドをロードできませんでした: {e}")
                    traceback.print_exc()
            else:
                print(f"WARNING: {github_sound_path} のバイトデータがダウンロードされませんでした。")
    else:
        print("WARNING: リソースパックが選択されていません。サウンドは再生されません。")
    
    pyglet.clock.schedule_interval(update, 1/60.0)

    print("\n--- Pygletゲームウィンドウを開始します ---")
    pyglet.app.run()
    print("--- Pygletゲームウィンドウが閉じられました ---")

    print("\n--- ゲームシミュレーション終了 ---")


# --- ブロック描画ヘルパー関数 ---
def draw_cube(x_pos, y_pos, z_pos, block_type_name):
    """
    指定された位置に、指定されたブロックタイプのキューブを描画します。
    光源からの光のレベルを考慮して描画します。
    """
    glPushMatrix()
    glTranslatef(x_pos + 0.5, y_pos + 0.5, z_pos + 0.5) # ブロックの中心に移動

    # ★変更: ブロックの光レベルを取得
    # デフォルトは0 (完全な暗闇)
    light_level = block_light_levels.get((x_pos, y_pos, z_pos), 0)
    
    # 環境光 (最低限の明るさ)
    ambient_light = 0.2
    
    # 光レベルを0.0から1.0のスケールに変換し、環境光を加算
    # MAX_LIGHT_LEVEL (15) で割る
    light_factor = ambient_light + (light_level / MAX_LIGHT_LEVEL) * (1.0 - ambient_light)
    light_factor = min(light_factor, 1.0) # 最大1.0にクランプ

    # 各面に適切なテクスチャをバインドして描画
    # 前面
    if (block_type_name, 'side') in textures:
        textures[(block_type_name, 'side')].bind()
    else:
        pyglet.image.create(32, 32, pyglet.image.SolidColorImagePattern((255, 0, 0, 255))).get_texture().bind()
    glBegin(GL_QUADS)
    glColor3f(light_factor, light_factor, light_factor) # ★変更: 光レベルを適用
    glTexCoord2f(0.0, 0.0); glVertex3f(-0.5, -0.5,  0.5)
    glTexCoord2f(1.0, 0.0); glVertex3f( 0.5, -0.5,  0.5)
    glTexCoord2f(1.0, 1.0); glVertex3f( 0.5,  0.5,  0.5)
    glTexCoord2f(0.0, 1.0); glVertex3f(-0.5,  0.5,  0.5)
    glEnd()

    # 背面
    if (block_type_name, 'side') in textures:
        textures[(block_type_name, 'side')].bind()
    else:
        pyglet.image.create(32, 32, pyglet.image.SolidColorImagePattern((255, 0, 0, 255))).get_texture().bind()
    glBegin(GL_QUADS)
    glColor3f(light_factor, light_factor, light_factor) # ★変更: 光レベルを適用
    glTexCoord2f(1.0, 0.0); glVertex3f(-0.5, -0.5, -0.5)
    glTexCoord2f(1.0, 1.0); glVertex3f(-0.5,  0.5, -0.5)
    glTexCoord2f(0.0, 1.0); glVertex3f( 0.5,  0.5, -0.5)
    glTexCoord2f(0.0, 0.0); glVertex3f( 0.5, -0.5, -0.5)
    glEnd()

    # 上面
    if (block_type_name, 'top') in textures:
        textures[(block_type_name, 'top')].bind()
    else:
        pyglet.image.create(32, 32, pyglet.image.SolidColorImagePattern((255, 0, 0, 255))).get_texture().bind()
    glBegin(GL_QUADS)
    glColor3f(light_factor, light_factor, light_factor) # ★変更: 光レベルを適用
    glTexCoord2f(0.0, 1.0); glVertex3f(-0.5,  0.5, -0.5)
    glTexCoord2f(0.0, 0.0); glVertex3f(-0.5,  0.5,  0.5)
    glTexCoord2f(1.0, 0.0); glVertex3f( 0.5,  0.5,  0.5)
    glTexCoord2f(1.0, 1.0); glVertex3f( 0.5,  0.5, -0.5)
    glEnd()

    # 下面
    if (block_type_name, 'bottom') in textures:
        textures[(block_type_name, 'bottom')].bind()
    else:
        pyglet.image.create(32, 32, pyglet.image.SolidColorImagePattern((255, 0, 0, 255))).get_texture().bind()
    glBegin(GL_QUADS)
    glColor3f(light_factor, light_factor, light_factor) # ★変更: 光レベルを適用
    glTexCoord2f(1.0, 1.0); glVertex3f(-0.5, -0.5, -0.5)
    glTexCoord2f(0.0, 1.0); glVertex3f( 0.5, -0.5, -0.5)
    glTexCoord2f(0.0, 0.0); glVertex3f( 0.5, -0.5,  0.5)
    glTexCoord2f(1.0, 0.0); glVertex3f(-0.5, -0.5,  0.5)
    glEnd()

    # 右面
    if (block_type_name, 'side') in textures:
        textures[(block_type_name, 'side')].bind()
    else:
        pyglet.image.create(32, 32, pyglet.image.SolidColorImagePattern((255, 0, 0, 255))).get_texture().bind()
    glBegin(GL_QUADS)
    glColor3f(light_factor, light_factor, light_factor) # ★変更: 光レベルを適用
    glTexCoord2f(1.0, 0.0); glVertex3f( 0.5, -0.5, -0.5)
    glTexCoord2f(1.0, 1.0); glVertex3f( 0.5,  0.5, -0.5)
    glTexCoord2f(0.0, 1.0); glVertex3f( 0.5,  0.5,  0.5)
    glTexCoord2f(0.0, 0.0); glVertex3f( 0.5, -0.5,  0.5)
    glEnd()

    # 左面
    if (block_type_name, 'side') in textures:
        textures[(block_type_name, 'side')].bind()
    else:
        pyglet.image.create(32, 32, pyglet.image.SolidColorImagePattern((255, 0, 0, 255))).get_texture().bind()
    glBegin(GL_QUADS)
    glColor3f(light_factor, light_factor, light_factor) # ★変更: 光レベルを適用
    glTexCoord2f(0.0, 0.0); glVertex3f(-0.5, -0.5, -0.5)
    glTexCoord2f(1.0, 0.0); glVertex3f(-0.5, -0.5,  0.5)
    glTexCoord2f(1.0, 1.0); glVertex3f(-0.5,  0.5,  0.5)
    glTexCoord2f(0.0, 1.0); glVertex3f(-0.5,  0.5, -0.5)
    glEnd()
    
    glPopMatrix()

# アイテム描画ヘルパー関数
def draw_item(x_pos, y_pos, z_pos, item_type, rotation_angle):
    """
    指定された位置に、指定されたアイテムタイプの小さなキューブを描画します。
    光源からの光のレベルを考慮して描画します。
    """
    glPushMatrix()
    glTranslatef(x_pos + 0.5, y_pos + 0.5, z_pos + 0.5) # アイテムの中心に移動
    glScalef(0.3, 0.3, 0.3) # 小さく描画
    glRotatef(rotation_angle, 0, 1, 0) # Y軸を中心に回転

    # ★変更: アイテムの光レベルを取得 (アイテムが位置するブロックの光レベルを使用)
    # または、周囲の光レベルの平均を取るなど、より複雑なロジックも可能
    # ここではアイテムがドロップされた位置のブロックの光レベルを単純に適用
    light_level = block_light_levels.get((math.floor(x_pos), math.floor(y_pos), math.floor(z_pos)), 0)
    
    ambient_light = 0.2
    light_factor = ambient_light + (light_level / MAX_LIGHT_LEVEL) * (1.0 - ambient_light)
    light_factor = min(light_factor, 1.0)

    # アイテムのテクスチャはブロックの上面テクスチャを使用
    if (item_type, 'top') in textures:
        textures[(item_type, 'top')].bind()
    else:
        # フォールバックの赤色テクスチャ
        pyglet.image.create(32, 32, pyglet.image.SolidColorImagePattern((255, 0, 0, 255))).get_texture().bind()

    # 各面を描画 (簡略化のため、すべての面で同じテクスチャを使用)
    glBegin(GL_QUADS)
    glColor3f(light_factor, light_factor, light_factor) # ★変更: 光レベルを適用
    # 前面
    glTexCoord2f(0.0, 0.0); glVertex3f(-0.5, -0.5,  0.5)
    glTexCoord2f(1.0, 0.0); glVertex3f( 0.5, -0.5,  0.5)
    glTexCoord2f(1.0, 1.0); glVertex3f( 0.5,  0.5,  0.5)
    glTexCoord2f(0.0, 1.0); glVertex3f(-0.5,  0.5,  0.5)
    # 背面
    glTexCoord2f(1.0, 0.0); glVertex3f(-0.5, -0.5, -0.5)
    glTexCoord2f(1.0, 1.0); glVertex3f(-0.5,  0.5, -0.5)
    glTexCoord2f(0.0, 1.0); glVertex3f( 0.5,  0.5, -0.5)
    glTexCoord2f(0.0, 0.0); glVertex3f( 0.5, -0.5, -0.5)
    # 上面
    glTexCoord2f(0.0, 1.0); glVertex3f(-0.5,  0.5, -0.5)
    glTexCoord2f(0.0, 0.0); glVertex3f(-0.5,  0.5,  0.5)
    glTexCoord2f(1.0, 0.0); glVertex3f( 0.5,  0.5,  0.5)
    glTexCoord2f(1.0, 1.0); glVertex3f( 0.5,  0.5, -0.5)
    # 下面
    glTexCoord2f(1.0, 1.0); glVertex3f(-0.5, -0.5, -0.5)
    glTexCoord2f(0.0, 1.0); glVertex3f( 0.5, -0.5, -0.5)
    glTexCoord2f(0.0, 0.0); glVertex3f( 0.5, -0.5,  0.5)
    glTexCoord2f(1.0, 0.0); glVertex3f(-0.5, -0.5,  0.5)
    # 右面
    glTexCoord2f(1.0, 0.0); glVertex3f( 0.5, -0.5, -0.5)
    glTexCoord2f(1.0, 1.0); glVertex3f( 0.5,  0.5, -0.5)
    glTexCoord2f(0.0, 1.0); glVertex3f( 0.5,  0.5,  0.5)
    glTexCoord2f(0.0, 0.0); glVertex3f( 0.5, -0.5,  0.5)
    glEnd()

    # 左面
    glTexCoord2f(0.0, 0.0); glVertex3f(-0.5, -0.5, -0.5)
    glTexCoord2f(1.0, 0.0); glVertex3f(-0.5, -0.5,  0.5)
    glTexCoord2f(1.0, 1.0); glVertex3f(-0.5,  0.5,  0.5)
    glTexCoord2f(0.0, 1.0); glVertex3f(-0.5,  0.5, -0.5)
    glEnd()
    
    glPopMatrix()

# --- 描画イベントハンドラ ---
@window.event
def on_draw():
    # 昼夜サイクルに基づいて背景色を設定
    # 時間を0.0から1.0の範囲に正規化
    normalized_time = current_day_time / DAY_LENGTH_SECONDS

    # 昼から夕方、夜、朝へ滑らかに色を補間
    if 0.0 <= normalized_time < 0.25: # 夜明けから昼
        # NIGHT_COLOR から DAY_COLOR へ補間
        t = normalized_time / 0.25
        r = NIGHT_COLOR[0] * (1-t) + DAY_COLOR[0] * t
        g = NIGHT_COLOR[1] * (1-t) + DAY_COLOR[1] * t
        b = NIGHT_COLOR[2] * (1-t) + DAY_COLOR[2] * t
    elif 0.25 <= normalized_time < 0.5: # 昼
        r, g, b = DAY_COLOR
    elif 0.5 <= normalized_time < 0.75: # 昼から夕方
        # DAY_COLOR から SUNSET_COLOR へ補間
        t = (normalized_time - 0.5) / 0.25
        r = DAY_COLOR[0] * (1-t) + SUNSET_COLOR[0] * t
        g = DAY_COLOR[1] * (1-t) + SUNSET_COLOR[1] * t
        b = DAY_COLOR[2] * (1-t) + SUNSET_COLOR[2] * t
    else: # 0.75 <= normalized_time < 1.0 (夕方から夜)
        # SUNSET_COLOR から NIGHT_COLOR へ補間
        t = (normalized_time - 0.75) / 0.25
        r = SUNSET_COLOR[0] * (1-t) + NIGHT_COLOR[0] * t
        g = SUNSET_COLOR[1] * (1-t) + NIGHT_COLOR[1] * t
        b = SUNSET_COLOR[2] * (1-t) + NIGHT_COLOR[2] * t

    glClearColor(r, g, b, 1.0) # 背景色を設定

    window.clear()
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(60, window.width / window.height, 0.1, 100.0)
    
    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()

    glRotatef(pitch, 1, 0, 0)
    glRotatef(yaw, 0, 1, 0)
    
    glTranslatef(-x, -y, -z)

    # ワールド内のすべてのブロックを描画
    for position, block_type_name in world_data.items():
        block_x, block_y, block_z = position
        draw_cube(block_x, block_y, block_z, block_type_name)
        
        # ブロック破壊中のアニメーション表示
        if block_breaking_target == position and block_breaking_progress > 0:
            glPushMatrix()
            glTranslatef(block_x + 0.5, block_y + 0.5, block_z + 0.5)
            # 破壊進捗に応じて色を暗くする (簡易的なひび割れ表現)
            # progressが0.0から1.0なので、1.0-progressで明るさを調整
            alpha = 0.5 # 半透明
            color_factor = 1.0 - (block_breaking_progress * 0.7) # 進捗に応じて暗くなる
            glColor4f(color_factor, color_factor, color_factor, alpha)
            
            # ワイヤーフレームを描画してひび割れを表現 (簡易版)
            glLineWidth(2 + block_breaking_progress * 5) # 進捗に応じて線が太くなる
            glDisable(GL_TEXTURE_2D)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            
            pyglet.graphics.draw(24, GL_LINES,
                ('v3f', (-0.5, -0.5, -0.5,  0.5, -0.5, -0.5,
                         -0.5,  0.5, -0.5,  0.5,  0.5, -0.5,
                         -0.5, -0.5,  0.5,  0.5, -0.5,  0.5,
                         -0.5,  0.5,  0.5,  0.5,  0.5,  0.5,
                         -0.5, -0.5, -0.5, -0.5,  0.5, -0.5,
                          0.5, -0.5, -0.5,  0.5,  0.5, -0.5,
                         -0.5, -0.5,  0.5, -0.5,  0.5,  0.5,
                          0.5, -0.5,  0.5,  0.5,  0.5,  0.5,
                         -0.5, -0.5, -0.5, -0.5, -0.5,  0.5,
                          0.5, -0.5, -0.5,  0.5, -0.5,  0.5,
                         -0.5,  0.5, -0.5, -0.5,  0.5,  0.5,
                          0.5,  0.5, -0.5,  0.5,  0.5,  0.5))
            )
            glDisable(GL_BLEND)
            glEnable(GL_TEXTURE_2D) # テクスチャ描画を再度有効にする
            glPopMatrix()


    # ドロップされたアイテムを描画
    for item in dropped_items:
        item_x, item_y, item_z = item['position']
        item_type = item['type']
        # アイテムが地面に浮いているように少しY座標を上げる
        draw_item(item_x, item_y + 0.1, item_z, item_type, item.get('rotation_angle', 0)) # 回転角度も渡す

    # テキスト表示とUI要素 (2Dオーバーレイ)
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    gluOrtho2D(0, window.width, 0, window.height)
    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()

    # ワールド名とパック情報
    label = pyglet.text.Label(f"ワールド: {WORLD_NAME}",
                              font_name='Arial',
                              font_size=18,
                              x=10, y=window.height - 30,
                              anchor_x='left', anchor_y='top', color=(255, 255, 255, 255))
    label.draw()

    label_pack = pyglet.text.Label("パックロード済み: " + (resource_pack_paths[0].split('/')[-1] if resource_pack_paths else "なし"),
                                   font_name='Arial',
                                   font_size=14,
                                   x=10, y=window.height - 60,
                                   anchor_x='left', anchor_y='top', color=(255, 255, 0, 255))
    label_pack.draw()

    # プレイヤーの座標表示
    coords_label = pyglet.text.Label(f"X: {x:.2f} Y: {y:.2f} Z: {z:.2f}",
                                     font_name='Arial',
                                     font_size=14,
                                     x=10, y=window.height - 90,
                                     anchor_x='left', anchor_y='top', color=(255, 255, 255, 255))
    coords_label.draw()

    # 時刻表示
    # 時間をHH:MM形式に変換 (例: 0.0=00:00, 0.25=06:00, 0.5=12:00, 0.75=18:00)
    total_minutes = int((normalized_time * 24 * 60) % (24 * 60))
    display_hour = total_minutes // 60
    display_minute = total_minutes % 60
    time_label = pyglet.text.Label(f"時刻: {display_hour:02d}:{display_minute:02d}",
                                   font_name='Arial',
                                   font_size=14,
                                   x=10, y=window.height - 120,
                                   anchor_x='left', anchor_y='top', color=(255, 255, 255, 255))
    time_label.draw()

    # クロスヘアの描画
    glLineWidth(2)
    glColor3f(1.0, 1.0, 1.0) # 白色のクロスヘア
    
    # 垂直線
    pyglet.graphics.draw(2, GL_LINES,
        ('v2f', (window.width // 2, window.height // 2 - 10,
                 window.width // 2, window.height // 2 + 10))
    )
    # 水平線
    pyglet.graphics.draw(2, GL_LINES,
        ('v2f', (window.width // 2 - 10, window.height // 2,
                 window.width // 2 + 10, window.width // 2))
    )

    # ホットバーの描画 (インベントリが開いていない場合のみ)
    if not is_inventory_open:
        hotbar_slot_size = 50
        hotbar_spacing = 5
        hotbar_total_width = len(hotbar_slots) * hotbar_slot_size + (len(hotbar_slots) - 1) * hotbar_spacing
        hotbar_start_x = (window.width - hotbar_total_width) // 2
        hotbar_start_y = 10 # 画面下部から10ピクセル上

        for i, block_type in enumerate(hotbar_slots):
            slot_x = hotbar_start_x + i * (hotbar_slot_size + hotbar_spacing)
            slot_y = hotbar_start_y

            # スロットの背景を描画
            if i == selected_inventory_slot:
                # 選択中のスロットは枠を太くする
                glColor3f(1.0, 1.0, 1.0) # 白
                glLineWidth(3)
                pyglet.graphics.draw(4, GL_LINE_LOOP,
                    ('v2f', (slot_x - 2, slot_y - 2,
                             slot_x + hotbar_slot_size + 2, slot_y - 2,
                             slot_x + hotbar_slot_size + 2, slot_y + hotbar_slot_size + 2,
                             slot_x - 2, slot_y + hotbar_slot_size + 2))
                )
                glColor3f(0.5, 0.5, 0.5) # 選択中のスロットの背景は少し暗く
            else:
                glColor3f(0.3, 0.3, 0.3) # 通常のスロットの背景
            
            glBegin(GL_QUADS)
            glVertex2f(slot_x, slot_y)
            glVertex2f(slot_x + hotbar_slot_size, slot_y)
            glVertex2f(slot_x + hotbar_slot_size, slot_y + hotbar_slot_size)
            glVertex2f(slot_x, slot_y + hotbar_slot_size)
            glEnd()

            # スロット内のブロックアイコンを描画
            if block_type and (block_type, 'top') in textures:
                glEnable(GL_TEXTURE_2D)
                glColor3f(1.0, 1.0, 1.0) # テクスチャの色をリセット
                textures[(block_type, 'top')].blit(slot_x + 5, slot_y + 5, width=hotbar_slot_size - 10, height=hotbar_slot_size - 10)
                glDisable(GL_TEXTURE_2D)
                
                # 数量を表示
                # hotbar_slots[i] が None でないことを確認
                if block_type is not None and block_type in inventory_counts and inventory_counts[block_type] > 1: # 数量が1より大きい場合のみ表示
                    count_label = pyglet.text.Label(str(inventory_counts[block_type]),
                                                    font_name='Arial',
                                                    font_size=10,
                                                    x=slot_x + hotbar_slot_size - 5, y=slot_y + 5,
                                                    anchor_x='right', anchor_y='bottom', color=(255, 255, 255, 255))
                    count_label.draw()
            elif block_type: # テクスチャがない場合のフォールバック
                glColor3f(1.0, 0.0, 0.0) # 赤色の四角
                glBegin(GL_QUADS)
                glVertex2f(slot_x + 5, slot_y + 5)
                glVertex2f(slot_x + hotbar_slot_size - 5, slot_y + 5)
                glVertex2f(slot_x + hotbar_slot_size - 5, slot_y + hotbar_slot_size - 5)
                glVertex2f(slot_x + 5, slot_y + hotbar_slot_size - 5)
                glEnd()

    # インベントリUIの描画
    if is_inventory_open:
        draw_inventory_ui()

    # ドラッグ中のアイテムの描画
    if current_drag_item and current_drag_count > 0:
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glColor4f(1.0, 1.0, 1.0, 0.7) # 半透明
        
        if (current_drag_item, 'top') in textures:
            textures[(current_drag_item, 'top')].blit(window.mouse_x - 25, window.mouse_y - 25, width=50, height=50)
        else:
            glColor4f(1.0, 0.0, 0.0, 0.7)
            glBegin(GL_QUADS)
            glVertex2f(window.mouse_x - 25, window.mouse_y - 25)
            glVertex2f(window.mouse_x + 25, window.mouse_y - 25)
            glVertex2f(window.mouse_x + 25, window.mouse_y + 25)
            glVertex2f(window.mouse_x - 25, window.mouse_y + 25)
            glEnd()
        
        # 数量表示
        count_label = pyglet.text.Label(str(current_drag_count),
                                        font_name='Arial',
                                        font_size=12,
                                        x=window.mouse_x + 20, y=window.mouse_y - 20,
                                        anchor_x='right', anchor_y='bottom', color=(255, 255, 255, 255))
        count_label.draw()
        glDisable(GL_BLEND)


    glPopMatrix()
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)

# インベントリUI描画関数 (クラフトグリッドを含む)
def draw_inventory_ui():
    global crafting_input_slots, crafting_output_item, crafting_output_count

    # UI全体のサイズと位置
    ui_width = 600
    ui_height = 400
    ui_x = (window.width - ui_width) // 2
    ui_y = (window.height - ui_height) // 2

    # 背景
    glColor4f(0.2, 0.2, 0.2, 0.8) # 半透明の暗い背景
    glBegin(GL_QUADS)
    glVertex2f(ui_x, ui_y)
    glVertex2f(ui_x + ui_width, ui_y)
    glVertex2f(ui_x + ui_width, ui_y + ui_height)
    glVertex2f(ui_x, ui_y + ui_height)
    glEnd()

    # タイトル
    title_label = pyglet.text.Label("Inventory & Crafting",
                                    font_name='Arial',
                                    font_size=20,
                                    x=ui_x + ui_width // 2, y=ui_y + ui_height - 30,
                                    anchor_x='center', anchor_y='center', color=(255, 255, 255, 255))
    title_label.draw()

    slot_size = 50
    slot_padding = 10

    # ホットバーの描画 (インベントリUI内)
    # インベントリUIの下部に配置
    hotbar_start_x = ui_x + (ui_width - (len(hotbar_slots) * slot_size + (len(hotbar_slots) - 1) * slot_padding)) // 2
    hotbar_start_y = ui_y + 20

    for i, item_type in enumerate(hotbar_slots):
        slot_x = hotbar_start_x + i * (slot_size + slot_padding)
        slot_y = hotbar_start_y
        draw_inventory_slot(slot_x, slot_y, slot_size, item_type, inventory_counts.get(item_type, 0), 'hotbar', i)

    # メインインベントリの描画 (3行9列)
    main_inv_rows = 3
    main_inv_cols = 9
    main_inv_start_x = ui_x + (ui_width - (main_inv_cols * slot_size + (main_inv_cols - 1) * slot_padding)) // 2
    main_inv_start_y = hotbar_start_y + slot_size + slot_padding + 20 # ホットバーの上に配置

    for row in range(main_inv_rows):
        for col in range(main_inv_cols):
            slot_index = row * main_inv_cols + col
            item_type = main_inventory_slots[slot_index]
            
            slot_x = main_inv_start_x + col * (slot_size + slot_padding)
            slot_y = main_inv_start_y + (main_inv_rows - 1 - row) * (slot_size + slot_padding) # 上から下に描画

            draw_inventory_slot(slot_x, slot_y, slot_size, item_type, inventory_counts.get(item_type, 0), 'main_inventory', slot_index)

    # クラフトグリッドの描画 (インベントリUIの左上)
    craft_grid_start_x = ui_x + 50
    craft_grid_start_y = ui_y + ui_height - 100 - (crafting_grid_size * slot_size + (crafting_grid_size - 1) * slot_padding)

    crafting_grid_label = pyglet.text.Label("Crafting Grid",
                                            font_name='Arial',
                                            font_size=14,
                                            x=craft_grid_start_x + (crafting_grid_size * slot_size + (crafting_grid_size - 1) * slot_padding) / 2,
                                            y=craft_grid_start_y + crafting_grid_size * slot_size + crafting_grid_size * slot_padding + 10,
                                            anchor_x='center', anchor_y='bottom', color=(255, 255, 255, 255))
    crafting_grid_label.draw()


    for i in range(crafting_grid_size):
        for j in range(crafting_grid_size):
            slot_index = i * crafting_grid_size + j
            slot_item_type = crafting_input_slots[slot_index]

            slot_x = craft_grid_start_x + j * (slot_size + slot_padding)
            slot_y = craft_grid_start_y + (crafting_grid_size - 1 - i) * (slot_size + slot_padding)

            # クラフト入力スロットは常に数量1として描画
            draw_inventory_slot(slot_x, slot_y, slot_size, slot_item_type, 1, 'crafting_input', slot_index)

    # 矢印の描画
    glColor3f(1.0, 1.0, 1.0)
    glLineWidth(2)
    arrow_start_x = craft_grid_start_x + crafting_grid_size * (slot_size + slot_padding) + 20
    arrow_start_y = craft_grid_start_y + (crafting_grid_size * slot_size + (crafting_grid_size - 1) * slot_padding) / 2
    pyglet.graphics.draw(2, GL_LINES, ('v2f', (arrow_start_x, arrow_start_y, arrow_start_x + 40, arrow_start_y)))
    pyglet.graphics.draw(2, GL_LINES, ('v2f', (arrow_start_x + 40, arrow_start_y, arrow_start_x + 30, arrow_start_y + 10)))
    pyglet.graphics.draw(2, GL_LINES, ('v2f', (arrow_start_x + 40, arrow_start_y, arrow_start_x + 30, arrow_start_y - 10)))

    # クラフト結果スロットの描画
    output_slot_x = arrow_start_x + 60
    output_slot_y = craft_grid_start_y + (crafting_grid_size * slot_size + (crafting_grid_size - 1) * slot_padding) / 2 - slot_size / 2

    # クラフト結果スロットは数量をそのまま表示
    draw_inventory_slot(output_slot_x, output_slot_y, slot_size, crafting_output_item, crafting_output_count, 'crafting_output', 0)

    # クラフトボタン
    craft_button_width = 100
    craft_button_height = 40
    craft_button_x = ui_x + ui_width // 2 - craft_button_width // 2
    craft_button_y = ui_y + 20

    if crafting_output_item and crafting_output_count > 0: # クラフト可能な場合
        glColor3f(0.0, 0.8, 0.0) # 緑色
    else:
        glColor3f(0.5, 0.5, 0.5) # 灰色 (無効)
    
    glBegin(GL_QUADS)
    glVertex2f(craft_button_x, craft_button_y)
    glVertex2f(craft_button_x + craft_button_width, craft_button_y)
    glVertex2f(craft_button_x + craft_button_width, craft_button_y + craft_button_height)
    glVertex2f(craft_button_x, craft_button_y + craft_button_height)
    glEnd()

    craft_button_label = pyglet.text.Label("Craft",
                                           font_name='Arial',
                                           font_size=16,
                                           x=craft_button_x + craft_button_width // 2, y=craft_button_y + craft_button_height // 2,
                                           anchor_x='center', anchor_y='center', color=(255, 255, 255, 255))
    craft_button_label.draw()

# インベントリスロット描画ヘルパー関数
def draw_inventory_slot(x_pos, y_pos, size, item_type, count, slot_type, slot_index):
    """
    インベントリスロットとアイテムアイコン、数量を描画します。
    slot_type: 'hotbar', 'main_inventory', 'crafting_input', 'crafting_output'
    """
    # スロットの背景
    glColor3f(0.3, 0.3, 0.3)
    glBegin(GL_QUADS)
    glVertex2f(x_pos, y_pos)
    glVertex2f(x_pos + size, y_pos)
    glVertex2f(x_pos + size, y_pos + size)
    glVertex2f(x_pos, y_pos + size)
    glEnd()

    # アイテムアイコン
    if item_type and (item_type, 'top') in textures:
        glEnable(GL_TEXTURE_2D)
        glColor3f(1.0, 1.0, 1.0) # テクスチャの色をリセット
        textures[(item_type, 'top')].blit(x_pos + 5, y_pos + 5, width=size - 10, height=size - 10)
        glDisable(GL_TEXTURE_2D)
        
        # 数量を表示 (クラフト結果以外は1個の場合表示しない)
        if count > 1 or (slot_type == 'crafting_output' and count > 0):
            count_label = pyglet.text.Label(str(count),
                                            font_name='Arial',
                                            font_size=10,
                                            x=x_pos + size - 5, y=y_pos + 5,
                                            anchor_x='right', anchor_y='bottom', color=(255, 255, 255, 255))
            count_label.draw()
    elif item_type: # テクスチャがない場合のフォールバック
        glColor3f(1.0, 0.0, 0.0) # 赤色の四角
        glBegin(GL_QUADS)
        glVertex2f(x_pos + 5, y_pos + 5)
        glVertex2f(x_pos + size - 5, y_pos + 5)
        glVertex2f(x_pos + size - 5, y_pos + size - 5)
        glVertex2f(x_pos + 5, y_pos + size - 5)
        glEnd()

# クラフトレシピのチェックと結果の更新
def check_crafting_recipe():
    global crafting_output_item, crafting_output_count

    # 現在のクラフト入力スロットのパターンを取得
    current_pattern = tuple(crafting_input_slots)

    # 2x2グリッドのパターンをレシピの形式に変換
    # レシピはタプルのタプルで定義されているため、グリッドを整形
    grid_pattern = []
    for i in range(crafting_grid_size):
        row = []
        for j in range(crafting_grid_size):
            row.append(current_pattern[i * crafting_grid_size + j])
        grid_pattern.append(tuple(row))
    grid_pattern = tuple(grid_pattern)

    # レシピをチェック
    found_recipe = False
    for recipe_pattern, (result_item, result_count) in CRAFTING_RECIPES.items():
        # レシピのパターンがクラフトグリッドのサイズと一致するか確認
        if len(recipe_pattern) == crafting_grid_size and all(len(row) == crafting_grid_size for row in recipe_pattern):
            # パターンが一致するかチェック
            match = True
            for r_row, g_row in zip(recipe_pattern, grid_pattern):
                if r_row != g_row:
                    match = False
                    break
            if match:
                # 材料がインベントリに十分にあるか確認
                materials_sufficient = True
                temp_inventory_counts = inventory_counts.copy() # 一時的なコピーでチェック
                for material_slot in current_pattern:
                    if material_slot and temp_inventory_counts.get(material_slot, 0) < 1:
                        materials_sufficient = False
                        break
                    elif material_slot:
                        temp_inventory_counts[material_slot] -= 1 # 消費をシミュレート
                
                if materials_sufficient:
                    crafting_output_item = result_item
                    crafting_output_count = result_count
                    found_recipe = True
                    break
    
    if not found_recipe:
        crafting_output_item = None
        crafting_output_count = 0

# インベントリにアイテムを追加するヘルパー関数 (スタック対応)
def add_item_to_inventory(item_type, count):
    global inventory_counts, hotbar_slots, main_inventory_slots
    
    if count <= 0:
        return

    remaining_to_add = count

    # 既存のホットバースロットにスタック
    for i in range(len(hotbar_slots)):
        slot_item = hotbar_slots[i]
        if slot_item == item_type:
            current_in_slot = inventory_counts.get(item_type, 0)
            can_add = min(remaining_to_add, MAX_STACK_SIZE - current_in_slot)
            if can_add > 0:
                inventory_counts[item_type] = current_in_slot + can_add
                remaining_to_add -= can_add
                if remaining_to_add == 0:
                    print(f"DEBUG: {count}個の{item_type}をホットバースロット {i} にスタックしました。")
                    return

    # 既存のメインインベントリスロットにスタック
    for i in range(len(main_inventory_slots)):
        slot_item = main_inventory_slots[i]
        if slot_item == item_type:
            current_in_slot = inventory_counts.get(item_type, 0)
            can_add = min(remaining_to_add, MAX_STACK_SIZE - current_in_slot)
            if can_add > 0:
                inventory_counts[item_type] = current_in_slot + can_add
                remaining_to_add -= can_add
                if remaining_to_add == 0:
                    print(f"DEBUG: {count}個の{item_type}をメインインベントリスロット {i} にスタックしました。")
                    return

    # 新しい空きスロットに配置 (ホットバー優先)
    if remaining_to_add > 0:
        for i in range(len(hotbar_slots)):
            if hotbar_slots[i] is None:
                hotbar_slots[i] = item_type
                to_place = min(remaining_to_add, MAX_STACK_SIZE)
                inventory_counts[item_type] = inventory_counts.get(item_type, 0) + to_place
                remaining_to_add -= to_place
                print(f"DEBUG: {to_place}個の{item_type}をホットバースロット {i} に配置しました。")
                if remaining_to_add == 0:
                    return
    
    # 新しい空きスロットに配置 (メインインベントリ)
    if remaining_to_add > 0:
        for i in range(len(main_inventory_slots)):
            if main_inventory_slots[i] is None:
                main_inventory_slots[i] = item_type
                to_place = min(remaining_to_add, MAX_STACK_SIZE)
                inventory_counts[item_type] = inventory_counts.get(item_type, 0) + to_place
                remaining_to_add -= to_place
                print(f"DEBUG: {to_place}個の{item_type}をメインインベントリスロット {i} に配置しました。")
                if remaining_to_add == 0:
                    return
    
    if remaining_to_add > 0:
        print(f"WARNING: {item_type} をインベントリに追加できませんでした。空きスロットがありません。残り: {remaining_to_add}")


# --- ウィンドウのリサイズイベントハンドラ ---
@window.event
def on_resize(width, height):
    glViewport(0, 0, width, height)
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(60, width / height, 0.1, 100.0)
    glMatrixMode(GL_MODELVIEW)
    return pyglet.event.EVENT_HANDLED

# --- マウス移動イベントハンドラ ---
@window.event
def on_mouse_motion(x_mouse, y_mouse, dx, dy):
    global yaw, pitch
    
    if not is_inventory_open: # インベントリUIが開いている間はカメラ操作を無効化
        sensitivity = 0.15

        yaw += dx * sensitivity
        pitch -= dy * sensitivity

        if pitch > 90:
            pitch = 90
        if pitch < -90:
            pitch = -90

# --- マウススクロールイベントハンドラ (ホットバー選択) ---
@window.event
def on_mouse_scroll(x, y, scroll_x, scroll_y):
    global selected_inventory_slot
    if not is_inventory_open: # インベントリが開いていない時のみホットバーをスクロール
        if scroll_y > 0: # 上スクロール (前のスロット)
            selected_inventory_slot = (selected_inventory_slot - 1 + len(hotbar_slots)) % len(hotbar_slots)
        elif scroll_y < 0: # 下スクロール (次のスロット)
            selected_inventory_slot = (selected_inventory_slot + 1) % len(hotbar_slots)
        print(f"INFO: ホットバースロット {selected_inventory_slot + 1} を選択しました。")


# --- スロット情報を取得するヘルパー関数 ---
def get_slot_at_mouse(mouse_x, mouse_y):
    """
    マウス座標に基づいて、どのインベントリスロットがクリックされたかを返します。
    返り値: (slot_type, slot_index, slot_list) または (None, -1, None)
    """
    slot_size = 50
    slot_padding = 10
    ui_width = 600
    ui_height = 400
    ui_x = (window.width - ui_width) // 2
    ui_y = (window.height - ui_height) // 2

    # ホットバー
    hotbar_start_x = ui_x + (ui_width - (len(hotbar_slots) * slot_size + (len(hotbar_slots) - 1) * slot_padding)) // 2
    hotbar_start_y = ui_y + 20
    for i in range(len(hotbar_slots)):
        slot_x = hotbar_start_x + i * (slot_size + slot_padding)
        slot_y = hotbar_start_y
        if slot_x <= mouse_x < slot_x + slot_size and slot_y <= mouse_y < slot_y + slot_size:
            return 'hotbar', i, hotbar_slots

    # メインインベントリ
    main_inv_rows = 3
    main_inv_cols = 9
    main_inv_start_x = ui_x + (ui_width - (main_inv_cols * slot_size + (main_inv_cols - 1) * slot_padding)) // 2
    main_inv_start_y = hotbar_start_y + slot_size + slot_padding + 20
    for row in range(main_inv_rows):
        for col in range(main_inv_cols):
            slot_index = row * main_inv_cols + col
            slot_x = main_inv_start_x + col * (slot_size + slot_padding)
            slot_y = main_inv_start_y + (main_inv_rows - 1 - row) * (slot_size + slot_padding)
            if slot_x <= mouse_x < slot_x + slot_size and slot_y <= mouse_y < slot_y + slot_size:
                return 'main_inventory', slot_index, main_inventory_slots

    # クラフト入力
    craft_grid_start_x = ui_x + 50
    craft_grid_start_y = ui_y + ui_height - 100 - (crafting_grid_size * slot_size + (crafting_grid_size - 1) * slot_padding)
    for i in range(crafting_grid_size):
        for j in range(crafting_grid_size):
            slot_index = i * crafting_grid_size + j
            slot_x = craft_grid_start_x + j * (slot_size + slot_padding)
            slot_y = craft_grid_start_y + (crafting_grid_size - 1 - i) * (slot_size + slot_padding)
            if slot_x <= mouse_x < slot_x + slot_size and slot_y <= mouse_y < slot_y + slot_size:
                return 'crafting_input', slot_index, crafting_input_slots

    # クラフト結果 (クリックでクラフトはボタンで処理するため、ここではスロット情報のみ)
    output_slot_x = craft_grid_start_x + crafting_grid_size * (slot_size + slot_padding) + 60
    output_slot_y = craft_grid_start_y + (crafting_grid_size * slot_size + (crafting_grid_size - 1) * slot_padding) / 2 - slot_size / 2
    if output_slot_x <= mouse_x < output_slot_x + slot_size and output_slot_y <= mouse_y < output_slot_y + slot_size:
        return 'crafting_output', 0, None # None for slot_list as it's special

    return None, -1, None # スロットがヒットしなかった場合


# --- マウスボタンクリックイベントハンドラ ---
@window.event
def on_mouse_press(x_mouse, y_mouse, button, modifiers):
    global world_data, hotbar_slots, selected_inventory_slot, dropped_items, inventory_counts
    global is_inventory_open, current_drag_item, current_drag_count, drag_from_slot_type, drag_from_slot_index
    global crafting_input_slots, crafting_output_item, crafting_output_count, main_inventory_slots
    global block_breaking_target, block_breaking_progress, breaking_sound_player

    if is_inventory_open:
        # インベントリUIが開いている場合のクリック処理
        slot_type, slot_index, slot_list = get_slot_at_mouse(x_mouse, y_mouse)

        # クラフトボタンのクリック判定
        ui_width = 600
        ui_height = 400
        ui_x = (window.width - ui_width) // 2
        ui_y = (window.height - ui_height) // 2
        craft_button_width = 100
        craft_button_height = 40
        craft_button_x = ui_x + ui_width // 2 - craft_button_width // 2
        craft_button_y = ui_y + 20

        if craft_button_x <= x_mouse < craft_button_x + craft_button_width and \
           craft_button_y <= y_mouse < craft_button_y + craft_button_height:
            if button == pyglet.window.mouse.LEFT and crafting_output_item and crafting_output_count > 0:
                # クラフト結果をインベントリに追加
                add_item_to_inventory(crafting_output_item, crafting_output_count)
                print(f"INFO: {crafting_output_item} を {crafting_output_count} 個クラフトしました。")
                if 'craft' in sound_effects:
                    sound_effects['craft'].play()

                # 材料を消費
                for i in range(len(crafting_input_slots)):
                    if crafting_input_slots[i]:
                        inventory_counts[crafting_input_slots[i]] -= 1
                        # 数量が0になったらスロットをNoneにする
                        if inventory_counts[crafting_input_slots[i]] <= 0:
                            crafting_input_slots[i] = None 
                check_crafting_recipe() # レシピを再チェック
            return # クラフトボタンがクリックされたら他のスロット処理は行わない

        # クラフト結果スロットのクリック判定 (ドラッグ開始用)
        if slot_type == 'crafting_output':
            if button == pyglet.window.mouse.LEFT and crafting_output_item and crafting_output_count > 0:
                # クラフト結果をドラッグ開始
                current_drag_item = crafting_output_item
                current_drag_count = crafting_output_count
                drag_from_slot_type = 'crafting_output'
                drag_from_slot_index = 0 # クラフト結果スロットは常にインデックス0
                
                # クラフト結果スロットを空にする (ドラッグ開始時に結果を消す)
                crafting_output_item = None
                crafting_output_count = 0
                
                # 材料を消費
                for i in range(len(crafting_input_slots)):
                    if crafting_input_slots[i]:
                        inventory_counts[crafting_input_slots[i]] -= 1
                        if inventory_counts[crafting_input_slots[i]] <= 0:
                            crafting_input_slots[i] = None
                check_crafting_recipe() # レシピを再チェック
            return

        # 通常のスロット (ホットバー、メインインベントリ、クラフト入力) のクリック処理
        if slot_type and slot_list is not None:
            clicked_item_type = slot_list[slot_index]
            clicked_item_count = inventory_counts.get(clicked_item_type, 0) if clicked_item_type else 0

            if current_drag_item is None: # ドラッグ中のアイテムがない場合 (スロットからアイテムをピックアップ)
                if clicked_item_type is not None and clicked_item_count > 0:
                    if button == pyglet.window.mouse.LEFT: # 左クリック: 全てピックアップ
                        current_drag_item = clicked_item_type
                        current_drag_count = clicked_item_count
                        slot_list[slot_index] = None # 元のスロットを空にする
                        inventory_counts[clicked_item_type] = 0 # インベントリのカウントをゼロにする
                        drag_from_slot_type = slot_type
                        drag_from_slot_index = slot_index
                        print(f"DEBUG: {clicked_item_count}個の{clicked_item_type}を{slot_type}スロット{slot_index}からドラッグ開始。")
                    elif button == pyglet.window.mouse.RIGHT: # 右クリック: 1つピックアップ
                        current_drag_item = clicked_item_type
                        current_drag_count = 1
                        inventory_counts[clicked_item_type] = clicked_item_count - 1
                        if inventory_counts[clicked_item_type] <= 0:
                            slot_list[slot_index] = None # 数量が0になったらスロットを空にする
                        drag_from_slot_type = slot_type
                        drag_from_slot_index = slot_index
                        print(f"DEBUG: 1個の{clicked_item_type}を{slot_type}スロット{slot_index}からドラッグ開始。")
            else: # ドラッグ中のアイテムがある場合 (スロットにアイテムをドロップ)
                if clicked_item_type is None: # クリックされたスロットが空の場合
                    if button == pyglet.window.mouse.LEFT: # 左クリック: 全てドロップ
                        # クラフト入力スロットは1つずつしか置けない
                        if slot_type == 'crafting_input' and current_drag_count > 1:
                            slot_list[slot_index] = current_drag_item
                            inventory_counts[current_drag_item] = inventory_counts.get(current_drag_item, 0) + 1
                            current_drag_count -= 1
                            print(f"DEBUG: クラフトスロットに1個の{current_drag_item}を配置。残り{current_drag_count}。")
                        else:
                            slot_list[slot_index] = current_drag_item
                            inventory_counts[current_drag_item] = inventory_counts.get(current_drag_item, 0) + current_drag_count
                            current_drag_item = None
                            current_drag_count = 0
                            print(f"DEBUG: {current_drag_count}個の{current_drag_item}を{slot_type}スロット{slot_index}に配置しました。")
                    elif button == pyglet.window.mouse.RIGHT: # 右クリック: 1つドロップ
                        # クラフト入力スロットは1つずつしか置けない
                        if slot_type == 'crafting_input' and slot_list[slot_index] is not None:
                            # 既にアイテムがある場合は何もしない
                            pass
                        else:
                            slot_list[slot_index] = current_drag_item
                            inventory_counts[current_drag_item] = inventory_counts.get(current_drag_item, 0) + 1
                            current_drag_count -= 1
                            if current_drag_count <= 0:
                                current_drag_item = None
                                current_drag_count = 0
                            print(f"DEBUG: 1個の{current_drag_item}を{slot_type}スロット{slot_index}に配置しました。")

                elif clicked_item_type == current_drag_item: # 同じアイテムの場合 (スタック)
                    if button == pyglet.window.mouse.LEFT: # 左クリック: 全て結合
                        can_add = min(current_drag_count, MAX_STACK_SIZE - clicked_item_count)
                        inventory_counts[clicked_item_type] = clicked_item_count + can_add
                        current_drag_count -= can_add
                        if current_drag_count <= 0:
                            current_drag_item = None
                            current_drag_count = 0
                        print(f"DEBUG: {can_add}個の{clicked_item_type}を{slot_type}スロット{slot_index}に結合しました。残り{current_drag_count}。")
                    elif button == pyglet.window.mouse.RIGHT: # 右クリック: 1つ結合
                        if clicked_item_count < MAX_STACK_SIZE:
                            inventory_counts[clicked_item_type] = clicked_item_count + 1
                            current_drag_count -= 1
                            if current_drag_count <= 0:
                                current_drag_item = None
                                current_drag_count = 0
                            print(f"DEBUG: 1個の{clicked_item_type}を{slot_type}スロット{slot_index}に結合しました。残り{current_drag_count}。")
                        else:
                            print(f"DEBUG: スロットが満杯のため、{clicked_item_type}を結合できませんでした。")
                else: # 異なるアイテムの場合 (スワップ)
                    if button == pyglet.window.mouse.LEFT: # 左クリック: スワップ
                        # 現在ドラッグしているアイテムを一時保存
                        temp_drag_item = current_drag_item
                        temp_drag_count = current_drag_count

                        # クリックされたスロットのアイテムをドラッグ状態にする
                        current_drag_item = clicked_item_type
                        current_drag_count = clicked_item_count
                        
                        # クリックされたスロットに一時保存したアイテムを配置
                        slot_list[slot_index] = temp_drag_item
                        inventory_counts[temp_drag_item] = inventory_counts.get(temp_drag_item, 0) + temp_drag_count
                        
                        # クリックされたスロットのアイテム数をインベントリから減らす (後でcurrent_drag_countがセットされるため0にする)
                        inventory_counts[clicked_item_type] = 0 
                        print(f"DEBUG: {slot_type}スロット{slot_index}のアイテムをスワップしました。")
                    # 右クリックで異なるアイテムのスワップは行わない (Minecraftの挙動に合わせる)
            check_crafting_recipe() # インベントリ操作後にレシピを再チェック
            return

        # UI外をクリックした場合、UIを閉じる
        if not (ui_x <= x_mouse < ui_x + ui_width and ui_y <= y_mouse < ui_y + ui_height):
            is_inventory_open = False
            window.set_exclusive_mouse(True) # マウスを再びゲームにロック
            # ドラッグ中のアイテムがあればインベントリに戻す
            if current_drag_item and current_drag_count > 0:
                add_item_to_inventory(current_drag_item, current_drag_count)
                current_drag_item = None
                current_drag_count = 0
            # クラフトグリッド内のアイテムをインベントリに戻す
            for i in range(len(crafting_input_slots)):
                if crafting_input_slots[i]:
                    add_item_to_inventory(crafting_input_slots[i], 1)
                    crafting_input_slots[i] = None
            crafting_output_item = None
            crafting_output_count = 0
            return

    else: # インベントリUIが開いていない場合のクリック処理 (既存のブロック操作)
        # レイキャスティングの開始点と方向
        start_pos = (x, y, z)
        
        # カメラの向きからレイの方向を計算
        rad_yaw = math.radians(yaw)
        rad_pitch = math.radians(pitch)

        dx_dir = -math.sin(rad_yaw)
        dz_dir = -math.cos(rad_yaw)
        dy_dir = math.sin(rad_pitch)

        xz_length = math.cos(rad_pitch)
        direction = (dx_dir * xz_length, dy_dir, dz_dir * xz_length)

        reach = 5.0
        step_size = 0.1

        hit_block_pos = None
        place_block_pos = None

        current_ray_pos = list(start_pos)

        for _ in range(int(reach / step_size)):
            current_ray_pos[0] += direction[0] * step_size
            current_ray_pos[1] += direction[1] * step_size
            current_ray_pos[2] += direction[2] * step_size

            block_x = math.floor(current_ray_pos[0])
            block_y = math.floor(current_ray_pos[1])
            block_z = math.floor(current_ray_pos[2])

            current_block_coords = (block_x, block_y, block_z)

            player_block_x = math.floor(x)
            player_block_y = math.floor(y)
            player_block_z = math.floor(z)
            if (player_block_x, player_block_y, player_block_z) == current_block_coords or \
               (player_block_x, player_block_y + 1, player_block_z) == current_block_coords:
                continue

            if current_block_coords in world_data:
                hit_block_pos = current_block_coords
                prev_ray_pos = (current_ray_pos[0] - direction[0] * step_size,
                                current_ray_pos[1] - direction[1] * step_size,
                                current_ray_pos[2] - direction[2] * step_size)
                place_block_pos = (math.floor(prev_ray_pos[0]), math.floor(prev_ray_pos[1]), math.floor(prev_ray_pos[2]))
                break

        if button == pyglet.window.mouse.LEFT: # 左クリック (破壊)
            if hit_block_pos:
                block_breaking_target = hit_block_pos
                block_breaking_progress = 0.0
                if 'break_block' in sound_effects:
                    if breaking_sound_player:
                        breaking_sound_player.pause() # 既に再生中なら停止
                    breaking_sound_player = pyglet.media.Player()
                    breaking_sound_player.queue(sound_effects['break_block'])
                    breaking_sound_player.loop = True # ループ再生
                    breaking_sound_player.play()
                print(f"INFO: ブロック破壊開始: {hit_block_pos}")
            else:
                block_breaking_target = None # ターゲットがない場合はリセット
                if breaking_sound_player:
                    breaking_sound_player.pause()
                    breaking_sound_player = None
                print("INFO: 破壊するブロックが見つかりませんでした。")
        elif button == pyglet.window.mouse.RIGHT: # 右クリック (配置)
            block_breaking_target = None
            block_breaking_progress = 0.0
            if breaking_sound_player:
                breaking_sound_player.pause()
                breaking_sound_player = None

            selected_block_type = hotbar_slots[selected_inventory_slot]
            if selected_block_type is None:
                print("INFO: 選択されたスロットにブロックがありません。")
                return

            if selected_block_type not in inventory_counts or inventory_counts[selected_block_type] <= 0:
                print(f"INFO: {selected_block_type} の在庫がありません。")
                return

            if place_block_pos and place_block_pos not in world_data:
                player_current_block_x = math.floor(x)
                player_current_block_y = math.floor(y)
                player_current_block_z = math.floor(z)
                
                if (place_block_pos != (player_current_block_x, player_current_block_y, player_current_block_z) and
                    place_block_pos != (player_current_block_x, player_current_block_y + 1, player_current_block_z)):
                    
                    print(f"INFO: ブロックを配置: {place_block_pos} ({selected_block_type})")
                    world_data[place_block_pos] = selected_block_type
                    inventory_counts[selected_block_type] -= 1
                    if 'place_block' in sound_effects:
                        sound_effects['place_block'].play()
                    calculate_light_levels() # ★追加: ブロック配置後に光レベルを再計算
                else:
                    print("WARNING: プレイヤーの位置にブロックを配置することはできません。")
            else:
                print("INFO: 配置する位置が見つからないか、既にブロックがあります。")

# マウスリリースイベントハンドラ (ドラッグ＆ドロップ用)
@window.event
def on_mouse_release(x_mouse, y_mouse, button, modifiers):
    global current_drag_item, current_drag_count, drag_from_slot_type, drag_from_slot_index
    global inventory_counts, crafting_input_slots, hotbar_slots, main_inventory_slots
    global block_breaking_target, block_breaking_progress, breaking_sound_player

    if button == pyglet.window.mouse.LEFT: # 左クリックが離された場合
        block_breaking_target = None
        block_breaking_progress = 0.0
        if breaking_sound_player:
            breaking_sound_player.pause()
            breaking_sound_player = None

        if current_drag_item: # ドラッグ中のアイテムがある場合のみ処理
            slot_type, slot_index, slot_list = get_slot_at_mouse(x_mouse, y_mouse)

            if slot_type and slot_list is not None and slot_type != 'crafting_output': # 通常のスロットへのドロップ
                target_item_in_slot = slot_list[slot_index]
                target_item_count = inventory_counts.get(target_item_in_slot, 0) if target_item_in_slot else 0

                if target_item_in_slot is None: # ターゲットスロットが空の場合
                    # クラフト入力スロットは1つずつしか置けない
                    if slot_type == 'crafting_input' and current_drag_count > 1:
                        slot_list[slot_index] = current_drag_item
                        inventory_counts[current_drag_item] = inventory_counts.get(current_drag_item, 0) + 1
                        current_drag_count -= 1
                        print(f"DEBUG: クラフトスロットに1個の{current_drag_item}を配置。残り{current_drag_count}。")
                    else:
                        slot_list[slot_index] = current_drag_item
                        inventory_counts[current_drag_item] = inventory_counts.get(current_drag_item, 0) + current_drag_count
                        current_drag_item = None
                        current_drag_count = 0
                        print(f"DEBUG: {current_drag_count}個の{current_drag_item}を{slot_type}スロット{slot_index}にドロップしました。")

                elif target_item_in_slot == current_drag_item: # 同じアイテムの場合 (スタック)
                    can_add = min(current_drag_count, MAX_STACK_SIZE - target_item_count)
                    inventory_counts[current_drag_item] = target_item_count + can_add
                    current_drag_count -= can_add
                    if current_drag_count <= 0:
                        current_drag_item = None
                        current_drag_count = 0
                    print(f"DEBUG: {can_add}個の{current_drag_item}を{slot_type}スロット{slot_index}に結合しました。残り{current_drag_count}。")
                else: # 異なるアイテムの場合 (スワップ)
                    # 現在ドラッグしているアイテムを一時保存
                    temp_drag_item = current_drag_item
                    temp_drag_count = current_drag_count

                    # ターゲットスロットのアイテムをドラッグ状態にする
                    current_drag_item = target_item_in_slot
                    current_drag_count = target_item_count
                    
                    # ターゲットスロットに一時保存したアイテムを配置
                    slot_list[slot_index] = temp_drag_item
                    inventory_counts[temp_drag_item] = inventory_counts.get(temp_drag_item, 0) + temp_drag_count
                    
                    # ターゲットスロットの元のアイテム数をインベントリから減らす
                    inventory_counts[target_item_in_slot] = 0 # 後でcurrent_drag_countがセットされるため0にする

                    print(f"DEBUG: {target_slot_type}スロット{target_slot_index}のアイテムをスワップしました。")
            else: # どこにもドロップされなかった場合、元のインベントリに戻す
                print(f"INFO: ドラッグ中のアイテムを元の位置に戻します。")
                if current_drag_item and current_drag_count > 0:
                    add_item_to_inventory(current_drag_item, current_drag_count)
                
            current_drag_item = None
            current_drag_count = 0
            drag_from_slot_type = None
            drag_from_slot_index = -1
            check_crafting_recipe() # ドロップ後にレシピを再チェック

# マウスドラッグイベントハンドラ (アイテムドラッグ用)
@window.event
def on_mouse_drag(x_mouse, y_mouse, dx, dy, buttons, modifiers):
    global current_drag_item, current_drag_count, drag_from_slot_type, drag_from_slot_index
    global inventory_counts, crafting_input_slots, hotbar_slots, main_inventory_slots

    if not is_inventory_open:
        return # インベントリUIが開いていない場合は何もしない

    # ドラッグ開始時のみ処理 (current_drag_itemがNoneの場合)
    if current_drag_item is None and (buttons & pyglet.window.mouse.LEFT or buttons & pyglet.window.mouse.RIGHT):
        slot_type, slot_index, slot_list = get_slot_at_mouse(x_mouse, y_mouse)

        if slot_type and slot_list is not None:
            clicked_item_type = slot_list[slot_index]
            clicked_item_count = inventory_counts.get(clicked_item_type, 0) if clicked_item_type else 0

            if clicked_item_type is not None and clicked_item_count > 0:
                if buttons & pyglet.window.mouse.LEFT: # 左ドラッグ: 全てピックアップ
                    current_drag_item = clicked_item_type
                    current_drag_count = clicked_item_count
                    slot_list[slot_index] = None # 元のスロットを空にする
                    inventory_counts[clicked_item_type] = 0 # インベントリのカウントをゼロにする
                    drag_from_slot_type = slot_type
                    drag_from_slot_index = slot_index
                    print(f"DEBUG: {clicked_item_count}個の{clicked_item_type}を{slot_type}スロット{slot_index}からドラッグ開始。")
                elif buttons & pyglet.window.mouse.RIGHT: # 右ドラッグ: 1つピックアップ
                    current_drag_item = clicked_item_type
                    current_drag_count = 1
                    inventory_counts[clicked_item_type] = clicked_item_count - 1
                    if inventory_counts[clicked_item_type] <= 0:
                        slot_list[slot_index] = None # 数量が0になったらスロットを空にする
                    drag_from_slot_type = slot_type
                    drag_from_slot_index = slot_index
                    print(f"DEBUG: 1個の{clicked_item_type}を{slot_type}スロット{slot_index}からドラッグ開始。")
                check_crafting_recipe() # ドラッグ開始でレシピ再チェック


# --- キーボードイベントハンドラ ---
@window.event
def on_key_press(symbol, modifiers):
    global selected_inventory_slot, is_inventory_open
    # 数字キー1-9でインベントリスロットを選択
    if pyglet.window.key._1 <= symbol <= pyglet.window.key._9:
        slot_index = symbol - pyglet.window.key._1
        if slot_index < len(hotbar_slots):
            selected_inventory_slot = slot_index
            print(f"INFO: ホットバースロット {selected_inventory_slot + 1} を選択しました。")
    
    # EキーでインベントリUIの表示/非表示を切り替え
    if symbol == DEFAULT_KEY_BINDINGS['toggle_inventory']:
        is_inventory_open = not is_inventory_open
        window.set_exclusive_mouse(not is_inventory_open) # UIが開いている間はマウスをロックしない
        if is_inventory_open:
            print("INFO: インベントリUIを開きました。")
            check_crafting_recipe() # UIを開いたときにレシピをチェック
        else:
            print("INFO: インベントリUIを閉じました。")
            # UIを閉じる際に、ドラッグ中のアイテムやクラフトグリッド内のアイテムをインベントリに戻す
            if current_drag_item and current_drag_count > 0:
                add_item_to_inventory(current_drag_item, current_drag_count)
                current_drag_item = None
                current_drag_count = 0
            for i in range(len(crafting_input_slots)):
                if crafting_input_slots[i]:
                    add_item_to_inventory(crafting_input_slots[i], 1)
                    crafting_input_slots[i] = None
            crafting_output_item = None
            crafting_output_count = 0


# --- ウィンドウを閉じるイベントハンドラ ---
@window.event
def on_close():
    save_world() # ゲーム終了時にワールドを保存
    # 背景音楽を停止
    if background_music_player:
        background_music_player.pause()
    # 破壊音を停止
    if breaking_sound_player:
        breaking_sound_player.pause()
    pyglet.app.exit() # アプリケーションを終了

# --- 衝突判定ヘルパー関数 ---
def hit_test_block(pos):
    """
    指定された浮動小数点座標がブロックの内部にあるかどうかを判定し、
    そのブロックの整数座標を返します。
    """
    block_x = math.floor(pos[0])
    block_y = math.floor(pos[1])
    block_z = math.floor(pos[2])
    
    if (block_x, block_y, block_z) in world_data:
        return (block_x, block_y, block_z)
    return None

def check_collision(current_pos, dx, dy_val, dz):
    """
    プレイヤーの移動を考慮した衝突判定を行います。
    dx, dy_val, dz は、各軸での移動量です。
    """
    global x, y, z, on_ground, dy

    # プレイヤーの足元の座標
    px, py, pz = current_pos

    # プレイヤーの衝突ボックスの角をチェック
    # プレイヤーは高さPLAYER_HEIGHT、幅PLAYER_WIDTH
    # 足元が(px, py, pz)で、頭上が(px, py + PLAYER_HEIGHT, pz)と考える

    # X軸方向の移動
    if dx != 0:
        target_x = px + dx
        # プレイヤーのX軸方向の移動で衝突する可能性のあるブロックの座標をチェック
        # 足元、頭上、そして幅を考慮
        for check_y_offset in [0, PLAYER_HEIGHT - 0.1]: # 足元と頭上付近
            for check_z_offset in [-PLAYER_WIDTH/2 + 0.1, PLAYER_WIDTH/2 - 0.1]: # プレイヤーの幅
                block_hit = hit_test_block((target_x + (PLAYER_WIDTH/2 if dx > 0 else -PLAYER_WIDTH/2), py + check_y_offset, pz + check_z_offset))
                if block_hit:
                    # 衝突した場合、X方向の移動をキャンセル
                    if dx > 0: # 右に移動中に衝突
                        x = block_hit[0] - PLAYER_WIDTH/2 - 0.001
                    else: # 左に移動中に衝突
                        x = block_hit[0] + 1 + PLAYER_WIDTH/2 + 0.001
                    dx = 0 # 移動量をゼロにする
                    break # 他のZオフセットはチェックしない
            if dx == 0: # 衝突して移動がキャンセルされたら、次の軸へ
                break
        x += dx # 衝突がなければ移動を適用

    # Z軸方向の移動
    if dz != 0:
        target_z = pz + dz
        # プレイヤーのZ軸方向の移動で衝突する可能性のあるブロックの座標をチェック
        for check_y_offset in [0, PLAYER_HEIGHT - 0.1]:
            for check_x_offset in [-PLAYER_WIDTH/2 + 0.1, PLAYER_WIDTH/2 - 0.1]:
                block_hit = hit_test_block((px + check_x_offset, py + check_y_offset, target_z + (PLAYER_WIDTH/2 if dz > 0 else -PLAYER_WIDTH/2)))
                if block_hit:
                    # 衝突した場合、Z方向の移動をキャンセル
                    if dz > 0: # 前に移動中に衝突
                        z = block_hit[2] - PLAYER_WIDTH/2 - 0.001
                    else: # 後ろに移動中に衝突
                        z = block_hit[2] + 1 + PLAYER_WIDTH/2 + 0.001
                    dz = 0
                    break
            if dz == 0:
                break
        z += dz # 衝突がなければ移動を適用

    # Y軸方向の移動 (重力とジャンプ)
    if dy_val != 0:
        target_y = py + dy_val
        
        # プレイヤーのY軸方向の移動で衝突する可能性のあるブロックの座標をチェック
        # プレイヤーの足元と頭上を考慮
        
        # 落下中 (dy_val < 0)
        if dy_val < 0:
            # プレイヤーの足元が衝突するかチェック
            for check_x_offset in [-PLAYER_WIDTH/2 + 0.1, PLAYER_WIDTH/2 - 0.1]:
                for check_z_offset in [-PLAYER_WIDTH/2 + 0.1, PLAYER_WIDTH/2 - 0.1]:
                    block_hit = hit_test_block((px + check_x_offset, target_y, pz + check_z_offset))
                    if block_hit:
                        # 衝突した場合、地面に接地
                        y = block_hit[1] + 1.0 # ブロックの上面に合わせる
                        dy = 0.0 # 垂直速度をゼロに
                        on_ground = True # 地面にいる状態に
                        dy_val = 0 # Y方向の移動をキャンセル
                        break
                if dy_val == 0:
                    break
        # 上昇中 (dy_val > 0)
        elif dy_val > 0:
            # プレイヤーの頭上が衝突するかチェック
            for check_x_offset in [-PLAYER_WIDTH/2 + 0.1, PLAYER_WIDTH/2 - 0.1]:
                for check_z_offset in [-PLAYER_WIDTH/2 + 0.1, PLAYER_WIDTH/2 - 0.1]:
                    block_hit = hit_test_block((px + check_x_offset, target_y + PLAYER_HEIGHT, pz + check_z_offset))
                    if block_hit:
                        # 衝突した場合、天井にぶつかったので落下に転じる
                        y = block_hit[1] - PLAYER_HEIGHT - 0.001 # ブロックの下面に合わせる
                        dy = 0.0 # 垂直速度をゼロに
                        dy_val = 0 # Y方向の移動をキャンセル
                        break
                if dy_val == 0:
                    break
        
        y += dy_val # 衝突がなければ移動を適用


# --- ゲーム状態の更新関数 ---
def update(dt):
    global x, y, z, yaw, pitch, dy, on_ground, current_day_time, dropped_items, inventory_counts
    global block_breaking_target, block_breaking_progress, breaking_sound_player

    if not is_inventory_open: # インベントリUIが開いている間はプレイヤー移動を無効化
        # 水平方向の移動量
        dx_move = 0
        dz_move = 0

        s = dt * PLAYER_SPEED

        if keys[DEFAULT_KEY_BINDINGS['forward']]:
            dx_move -= s * math.sin(math.radians(yaw))
            dz_move -= s * math.cos(math.radians(yaw))
        if keys[DEFAULT_KEY_BINDINGS['backward']]:
            dx_move += s * math.sin(math.radians(yaw))
            dz_move += s * math.cos(math.radians(yaw))

        if keys[DEFAULT_KEY_BINDINGS['strafe_left']]:
            dx_move -= s * math.sin(math.radians(yaw - 90))
            dz_move -= s * math.cos(math.radians(yaw - 90))
        if keys[DEFAULT_KEY_BINDINGS['strafe_right']]:
            dx_move += s * math.sin(math.radians(yaw - 90))
            dz_move += s * math.cos(math.radians(yaw - 90))

        # ジャンプ
        if keys[DEFAULT_KEY_BINDINGS['jump']] and on_ground:
            dy = JUMP_SPEED
            on_ground = False # ジャンプしたら地面から離れる
            if 'jump' in sound_effects:
                sound_effects['jump'].play()

        # クロール (落下速度を速める)
        if keys[DEFAULT_KEY_BINDINGS['crouch']]:
            # dyを負の方向に加速させることで、より速く落下させる
            dy = max(dy - GRAVITY * dt * 2, TERMINAL_VELOCITY) # 通常の重力より強くする
        
        # 重力適用
        if not on_ground:
            dy -= GRAVITY * dt
            dy = max(dy, TERMINAL_VELOCITY) # 落下速度に上限を設定

        # 衝突判定を伴う移動の適用
        # まず水平移動を試行
        check_collision((x, y, z), dx_move, 0, dz_move) # Y軸移動はここではゼロ

        # 次に垂直移動を試行
        check_collision((x, y, z), 0, dy * dt, 0) # XZ軸移動はここではゼロ

        # プレイヤーが地面にいるかどうかの再チェック (念のため)
        # プレイヤーの足元から少し下のブロックをチェック
        block_below = hit_test_block((x, y - 0.1, z))
        if block_below:
            on_ground = True
            # 地面にめり込まないように調整
            if y < block_below[1] + 1.0:
                y = block_below[1] + 1.0
                dy = 0.0
        else:
            on_ground = False

    # 昼夜の時間を更新
    current_day_time += dt
    if current_day_time >= DAY_LENGTH_SECONDS:
        current_day_time = 0.0 # 1日が終わったらリセット

    # ブロック破壊の進行状況を更新
    if block_breaking_target and block_breaking_target in world_data:
        target_block_type = world_data[block_breaking_target]
        base_hardness = BLOCK_HARDNESS.get(target_block_type, 1.0) # デフォルトの硬さ

        # 現在選択中のホットバースロットのアイテムを取得
        held_item = hotbar_slots[selected_inventory_slot]
        
        # ツールによる効果を計算
        tool_multiplier = 1.0
        if held_item in TOOL_EFFECTIVENESS:
            effectiveness_map = TOOL_EFFECTIVENESS[held_item]
            tool_multiplier = effectiveness_map.get(target_block_type, 1.0) # 特定のブロックに対する効果
        
        # 破壊速度の計算 (硬さに反比例し、ツール効果に比例)
        break_speed = (1.0 / (base_hardness * BREAK_TIME_PER_HARDNESS)) * tool_multiplier
        
        block_breaking_progress += break_speed * dt

        if block_breaking_progress >= 1.0:
            # ブロック破壊完了
            block_type_broken = world_data[block_breaking_target]
            print(f"INFO: ブロックを破壊: {block_breaking_target} ({block_type_broken})")
            del world_data[block_breaking_target]
            dropped_items.append({
                'position': (block_breaking_target[0], block_breaking_target[1], block_breaking_target[2]),
                'type': block_type_broken,
                'rotation_angle': 0
            })
            block_breaking_target = None # ターゲットをリセット
            block_breaking_progress = 0.0 # 進捗をリセット
            if breaking_sound_player:
                breaking_sound_player.pause()
                breaking_sound_player = None
            calculate_light_levels() # ★変更: ブロック破壊後に光レベルを再計算
    else:
        # ターゲットブロックがない、または壊されてしまった場合はリセット
        if block_breaking_target: # ターゲットが設定されていたが、もう存在しない場合
            block_breaking_target = None
            block_breaking_progress = 0.0
            if breaking_sound_player:
                breaking_sound_player.pause()
                breaking_sound_player = None


    # ドロップされたアイテムの回転とピックアップ
    player_center_x = x
    player_center_y = y + PLAYER_HEIGHT / 2 # プレイヤーの中心Y座標
    player_center_z = z
    player_pickup_range_sq = 1.5**2 # アイテムを拾う範囲 (半径1.5ブロック)の二乗

    items_to_remove = []
    for i, item in enumerate(dropped_items):
        item_x, item_y, item_z = item['position']
        item_type = item['type']

        # アイテムを回転させる
        item['rotation_angle'] = (item.get('rotation_angle', 0) + 90 * dt) % 360 # 毎秒90度回転

        # プレイヤーとアイテムの距離を計算
        dist_sq = (player_center_x - (item_x + 0.5))**2 + \
                  (player_center_y - (item_y + 0.5))**2 + \
                  (player_center_z - (item_z + 0.5))**2
        
        if dist_sq < player_pickup_range_sq:
            # プレイヤーがアイテムの近くにいる場合、インベントリに追加
            add_item_to_inventory(item_type, 1) # ドロップアイテムは1つずつ
            print(f"INFO: アイテムを拾いました: {item_type}. 現在の数量: {inventory_counts[item_type]}")
            items_to_remove.append(i) # 削除対象としてマーク
            if 'pickup_item' in sound_effects:
                sound_effects['pickup_item'].play()

    # 収集されたアイテムをリストから削除 (逆順に削除することでインデックスのずれを防ぐ)
    for i in sorted(items_to_remove, reverse=True):
        del dropped_items[i]


# --- メインゲームループ ---
setup_game()
