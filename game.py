import pyglet
from pyglet.gl import *
import math
import json
import os
import requests
import base64
from dotenv import load_dotenv
import noise # 追加: ノイズ生成ライブラリ
import random # 追加: シード値のランダム生成用

# .envファイルをロード
load_dotenv()

# --- GitHub API 設定 ---
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_OWNER = os.getenv('GITHUB_OWNER')
GITHUB_REPO = os.getenv('GITHUB_REPO') # .envから読み込む

if not GITHUB_TOKEN or not GITHUB_OWNER or not GITHUB_REPO:
    print("エラー: .env ファイルに GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO が設定されていません。")
    print("または GITHUB_OWNER, GITHUB_REPO が正しく設定されていません。")
    exit(1)

GITHUB_API_BASE_URL = f'https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents'
HEADERS = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.v3+json',
    'User-Agent': 'Pyglet-Minecraft-Game'
}

# --- GitHub API ヘルパー関数 ---
def get_github_file_content(path):
    """GitHubからファイルの内容を取得し、JSONとしてデコードする"""
    url = f'{GITHUB_API_BASE_URL}/{path}'
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        content_b64 = response.json()['content']
        decoded_content = base64.b64decode(content_b64).decode('utf-8')
        return json.loads(decoded_content)
    return None

def put_github_file_content(path, content, message, sha=None):
    """GitHubにファイルの内容をJSONとしてエンコードし、保存する"""
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
    """GitHubからファイルのSHAなどの情報を取得する"""
    url = f'{GITHUB_API_BASE_URL}/{path}'
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        return response.json()
    return None

# --- グローバル変数と初期設定 ---
window = pyglet.window.Window(width=1024, height=768, caption='Cave Game (with Terrain & Textures)', resizable=True)

# OpenGLの設定
glEnable(GL_DEPTH_TEST)
glEnable(GL_CULL_FACE)
glEnable(GL_TEXTURE_2D) # テクスチャを有効にする

camera_x, camera_y, camera_z = 0.0, 0.0, -5.0
camera_rot_x, camera_rot_y = 0.0, 0.0
mouse_sensitivity = 0.1
keys = pyglet.window.key.KeyStateHandler()
window.push_handlers(keys)

# ブロックの種類とテクスチャ座標の定義
# 各ブロックタイプは、テクスチャアトラス上のどの部分を使用するかを定義
# ここでは、プレースホルダー画像を使用し、各ブロックが異なる色を持つようにする
# 実際のMinecraftでは、テクスチャアトラス（複数のテクスチャを1枚の画像にまとめたもの）を使用し、
# その中のUV座標を指定する
BLOCK_TEXTURE_COORDS = {
    # テクスチャアトラスのUV座標 (左下X, 左下Y, 右上X, 右上Y)
    # ここでは簡易的に、各ブロックに異なるプレースホルダー画像を割り当てる
    # 実際は、1枚のテクスチャアトラスからUV座標を切り出す
    0: None, # 空気 (描画しない)
    1: 'https://placehold.co/64x64/00FF00/FFFFFF?text=Grass', # 草ブロック
    2: 'https://placehold.co/64x64/8B4513/FFFFFF?text=Dirt',  # 土ブロック
    3: 'https://placehold.co/64x64/808080/FFFFFF?text=Stone', # 石ブロック
    4: 'https://placehold.co/64x64/FFFF00/000000?text=Sand',  # 砂ブロック
}

# ロードされたテクスチャを保持する辞書
textures = {}

def load_texture(url):
    """URLからテクスチャをロードする"""
    if url in textures:
        return textures[url]
    
    try:
        # Pygletのimage.load()はファイルパスかファイルライクオブジェクトを期待する
        # URLから直接ロードするには、requestsで画像をダウンロードしてからBytesIOで渡す
        response = requests.get(url, stream=True)
        response.raise_for_status() # HTTPエラーをチェック
        from io import BytesIO
        image_data = BytesIO(response.content)
        
        image = pyglet.image.load('', file=image_data)
        texture = image.get_texture()
        textures[url] = texture
        print(f"Loaded texture from {url}")
        return texture
    except Exception as e:
        print(f"Failed to load texture from {url}: {e}")
        # ロード失敗時のフォールバック (赤いテクスチャなど)
        # 簡易的なフォールバックとして、単色のテクスチャを生成
        fallback_image = pyglet.image.create(64, 64, pyglet.image.SolidColorImagePattern((255, 0, 0, 255)))
        fallback_texture = fallback_image.get_texture()
        textures[url] = fallback_texture
        return fallback_texture

# 全てのブロックテクスチャを事前にロード
for block_id, url in BLOCK_TEXTURE_COORDS.items():
    if url:
        load_texture(url)

# ワールドデータ (辞書: キーは "(x,y,z)" 形式の文字列、値はブロックID)
world_data = {}

# 現在のワールド名とプレイヤーUUID、ワールドUUID (仮)
# これらはFlaskのセッションなどから渡されるべき情報だが、
# ゲーム単体でテストするため、今回は直接設定する
# 実際の統合版風実装では、Flaskからゲーム起動時にこれらの情報が渡される
current_world_name = "MyFirstCave"
current_player_uuid = "test-player-uuid-1234" # 登録したプレイヤーのUUIDに合わせる
current_world_uuid = "test-world-uuid-abcd" # 新規に生成するか、既存のUUIDを使う

# ワールドデータのファイルパス
WORLD_BLOCK_FILE_PATH = f'worlds/{current_player_uuid}/{current_world_name}-{current_player_uuid}-block-{current_world_uuid}.json'
PLAYER_POS_FILE_PATH = f'worlds/{current_player_uuid}/{current_world_name}-{current_player_uuid}-playerxyz-{current_world_uuid}.json'

# --- ワールドデータのロード/セーブ関数 ---
def load_world_blocks():
    """GitHubからワールドブロックデータとプレイヤー位置データをロードする"""
    global world_data, camera_x, camera_y, camera_z

    # GitHubからブロックデータをロード
    loaded_blocks = get_github_file_content(WORLD_BLOCK_FILE_PATH)
    if loaded_blocks:
        world_data = loaded_blocks
        print(f"Loaded world blocks from {WORLD_BLOCK_FILE_PATH}")
    else:
        print(f"No existing world blocks found for {WORLD_BLOCK_FILE_PATH}. Generating new world.")
        # シード値をランダムに生成（または既存のワールド設定から取得）
        seed = random.randint(0, 100000)
        generate_noise_terrain(seed) # ノイズベースの地形を生成
        save_world_blocks() # 生成したものを保存

    # プレイヤー位置もロード
    loaded_pos = get_github_file_content(PLAYER_POS_FILE_PATH)
    if loaded_pos:
        camera_x, camera_y, camera_z = loaded_pos['x'], loaded_pos['y'], loaded_pos['z']
        print(f"Loaded player position: ({camera_x}, {camera_y}, {camera_z})")
    else:
        # 初期位置を設定 (生成された地形の高さに合わせて調整)
        # 例えば、ワールドの中心あたりの高さに設定
        initial_x = WORLD_SIZE_X // 2
        initial_z = WORLD_SIZE_Z // 2
        # 初期Y座標は地形の高さ＋数ブロック上
        initial_y = get_terrain_height(initial_x, initial_z) + 3 
        camera_x, camera_y, camera_z = float(initial_x), float(initial_y), float(initial_z)
        print(f"No player position found. Setting default: ({camera_x}, {camera_y}, {camera_z})")
        save_player_position() # 初期位置を保存


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

# --- 地形生成関数 (ノイズベースに変更) ---
WORLD_SIZE_X = 64 # ワールドのX方向のサイズ
WORLD_SIZE_Y = 64 # ワールドのY方向の最大高さ
WORLD_SIZE_Z = 64 # ワールドのZ方向のサイズ
NOISE_SCALE = 20.0 # ノイズのスケール（値が小さいほど滑らか）
TERRAIN_HEIGHT_OFFSET = 10 # 地形の基準となる高さ

def get_terrain_height(x, z, seed=0):
    """指定された(x,z)座標の地形の高さをノイズで計算する"""
    # Perlinノイズは-1.0から1.0の値を返す
    # これを0から1の範囲に変換し、スケールとオフセットを適用
    height = noise.pnoise2(x / NOISE_SCALE, z / NOISE_SCALE, octaves=4, persistence=0.5, lacunarity=2.0, repeatx=1024, repeaty=1024, base=seed)
    height = (height + 1.0) / 2.0 # -1.0 to 1.0 -> 0.0 to 1.0
    return int(height * (WORLD_SIZE_Y / 2)) + TERRAIN_HEIGHT_OFFSET # 高さを整数に変換し、オフセットを加える

def generate_noise_terrain(seed):
    """ノイズベースの地形を生成し、world_dataに格納する"""
    global world_data
    world_data = {} # 既存のワールドデータをクリア

    print(f"Generating terrain with seed: {seed}")

    for x in range(WORLD_SIZE_X):
        for z in range(WORLD_SIZE_Z):
            height = get_terrain_height(x, z, seed)
            
            # 地表は草ブロック
            world_data[f"{x},{height},{z}"] = 1 # 草ブロック (ID:1)
            
            # その下は土ブロック
            for y_dirt in range(height - 1, height - 3, -1): # 2層の土
                if y_dirt >= 0:
                    world_data[f"{x},{y_dirt},{z}"] = 2 # 土ブロック (ID:2)
            
            # その下は石ブロック
            for y_stone in range(height - 3, -WORLD_SIZE_Y, -1): # 土の下からワールドの底まで石
                if y_stone >= -WORLD_SIZE_Y: # ワールドのY範囲内かチェック
                    world_data[f"{x},{y_stone},{z}"] = 3 # 石ブロック (ID:3)
    print("Terrain generation complete.")

# --- ブロックの描画関数 (テクスチャ対応) ---
def draw_block(x, y, z, block_id):
    """指定された位置に、指定されたブロックIDのブロックを描画する（テクスチャ付き）"""
    if block_id == 0: # 空気ブロックは描画しない
        return

    texture_url = BLOCK_TEXTURE_COORDS.get(block_id)
    if not texture_url:
        print(f"Warning: No texture URL defined for block ID {block_id}")
        return

    texture = textures.get(texture_url)
    if not texture:
        print(f"Warning: Texture not loaded for block ID {block_id} (URL: {texture_url})")
        return

    # テクスチャをバインド
    glBindTexture(texture.target, texture.id)
    
    glPushMatrix()
    glTranslatef(x + 0.5, y + 0.5, z + 0.5) # ブロックの中心に移動 (サイズが1x1x1なので0.5オフセット)
    
    # 立方体の頂点とテクスチャ座標
    # テクスチャ座標は0.0から1.0の範囲
    # ここでは、テクスチャ全体を各面に適用
    
    # 前面 (Z+)
    glBegin(GL_QUADS)
    glTexCoord2f(0.0, 0.0); glVertex3f(-0.5, -0.5, 0.5)
    glTexCoord2f(1.0, 0.0); glVertex3f( 0.5, -0.5, 0.5)
    glTexCoord2f(1.0, 1.0); glVertex3f( 0.5,  0.5, 0.5)
    glTexCoord2f(0.0, 1.0); glVertex3f(-0.5,  0.5, 0.5)
    glEnd()

    # 後面 (Z-)
    glBegin(GL_QUADS)
    glTexCoord2f(1.0, 0.0); glVertex3f(-0.5, -0.5, -0.5)
    glTexCoord2f(1.0, 1.0); glVertex3f(-0.5,  0.5, -0.5)
    glTexCoord2f(0.0, 1.0); glVertex3f( 0.5,  0.5, -0.5)
    glTexCoord2f(0.0, 0.0); glVertex3f( 0.5, -0.5, -0.5)
    glEnd()

    # 上面 (Y+)
    glBegin(GL_QUADS)
    glTexCoord2f(0.0, 1.0); glVertex3f(-0.5,  0.5, -0.5)
    glTexCoord2f(0.0, 0.0); glVertex3f(-0.5,  0.5,  0.5)
    glTexCoord2f(1.0, 0.0); glVertex3f( 0.5,  0.5,  0.5)
    glTexCoord2f(1.0, 1.0); glVertex3f( 0.5,  0.5, -0.5)
    glEnd()

    # 下面 (Y-)
    glBegin(GL_QUADS)
    glTexCoord2f(1.0, 1.0); glVertex3f(-0.5, -0.5, -0.5)
    glTexCoord2f(0.0, 1.0); glVertex3f( 0.5, -0.5, -0.5)
    glTexCoord2f(0.0, 0.0); glVertex3f( 0.5, -0.5,  0.5)
    glTexCoord2f(1.0, 0.0); glVertex3f(-0.5, -0.5,  0.5)
    glEnd()

    # 右面 (X+)
    glBegin(GL_QUADS)
    glTexCoord2f(1.0, 0.0); glVertex3f( 0.5, -0.5, -0.5)
    glTexCoord2f(1.0, 1.0); glVertex3f( 0.5,  0.5, -0.5)
    glTexCoord2f(0.0, 1.0); glVertex3f( 0.5,  0.5,  0.5)
    glTexCoord2f(0.0, 0.0); glVertex3f( 0.5, -0.5,  0.5)
    glEnd()

    # 左面 (X-)
    glBegin(GL_QUADS)
    glTexCoord2f(0.0, 0.0); glVertex3f(-0.5, -0.5, -0.5)
    glTexCoord2f(1.0, 0.0); glVertex3f(-0.5, -0.5,  0.5)
    glTexCoord2f(1.0, 1.0); glVertex3f(-0.5,  0.5,  0.5)
    glTexCoord2f(0.0, 1.0); glVertex3f(-0.5,  0.5, -0.5)
    glEnd()

    glPopMatrix()
    # テクスチャのバインドを解除 (次の描画に影響を与えないため)
    glBindTexture(texture.target, 0)


@window.event
def on_draw():
    window.clear()
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(75, window.width / window.height, 0.1, 100.0)

    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()

    glRotatef(-camera_rot_x, 1, 0, 0)
    glRotatef(-camera_rot_y, 0, 1, 0)
    glTranslatef(-camera_x, -camera_y, -camera_z)

    # ワールド内のすべてのブロックを描画
    # 描画範囲をプレイヤーの周囲に限定するとパフォーマンスが向上する
    # 例: プレイヤーから一定距離内のチャンクのみを描画
    
    # 簡易的に、ワールドデータ内の全ブロックを描画
    for pos_str, block_id in world_data.items():
        x, y, z = map(int, pos_str.split(','))
        # プレイヤーの視界内にあるブロックのみを描画するカリング処理を追加すると良い
        draw_block(x, y, z, block_id)

@window.event
def on_mouse_motion(x, y, dx, dy):
    global camera_rot_y, camera_rot_x
    camera_rot_y += dx * mouse_sensitivity
    camera_rot_x += dy * mouse_sensitivity
    if camera_rot_x > 90: camera_rot_x = 90
    if camera_rot_x < -90: camera_rot_x = -90

# --- ブロックの設置・破壊 (Raycasting) ---
def get_looked_at_block_and_face():
    """プレイヤーの視線が当たっているブロックとその面を特定する"""
    # プレイヤーの向いている方向ベクトルを計算
    yaw_rad = math.radians(camera_rot_y)
    pitch_rad = math.radians(camera_rot_x)

    # 前方方向ベクトル
    front_x = math.sin(yaw_rad) * math.cos(pitch_rad)
    front_y = -math.sin(pitch_rad)
    front_z = -math.cos(yaw_rad) * math.cos(pitch_rad)
    
    # レイの開始位置 (プレイヤーの目の位置)
    ray_start = (camera_x, camera_y, camera_z)
    
    # レイの探索ステップ
    step_size = 0.1 # 細かくステップして正確性を上げる
    max_distance = 8.0 # 最大探索距離

    current_x, current_y, current_z = ray_start
    
    last_block_pos = None # レイが最後に通過したブロックの座標
    
    for _ in range(int(max_distance / step_size)):
        # 現在のレイの位置にあるブロックの座標
        block_x = int(math.floor(current_x))
        block_y = int(math.floor(current_y))
        block_z = int(math.floor(current_z))
        
        current_block_pos = (block_x, block_y, block_z)
        pos_key = f"{block_x},{block_y},{block_z}"
        
        # もし現在の位置にブロックがあれば、それがヒットしたブロック
        if world_data.get(pos_key, 0) != 0: # 空気でなければブロックがある
            # ヒットしたブロックの座標と、そのブロックの「手前」の座標から面を特定
            # 面の法線は、レイがブロックに入る直前の位置から現在のブロックへのベクトル
            if last_block_pos:
                face_normal = (
                    block_x - last_block_pos[0],
                    block_y - last_block_pos[1],
                    block_z - last_block_pos[2]
                )
            else:
                # 最初のブロックに当たった場合、簡易的にレイの逆方向を法線とする
                face_normal = (-int(round(front_x)), -int(round(front_y)), -int(round(front_z)))
                
            # 法線を正規化
            mag = math.sqrt(face_normal[0]**2 + face_normal[1]**2 + face_normal[2]**2)
            if mag != 0:
                face_normal = (face_normal[0]/mag, face_normal[1]/mag, face_normal[2]/mag)
            else:
                face_normal = (0,0,0)
            
            return current_block_pos, face_normal
        
        # レイを前方に進める
        current_x += front_x * step_size
        current_y += front_y * step_size
        current_z += front_z * step_size
        
        # レイが新しいブロックの境界を越えたら、last_block_posを更新
        if last_block_pos is None or current_block_pos != last_block_pos:
            last_block_pos = current_block_pos

    return None, None


@window.event
def on_mouse_press(x, y, button, modifiers):
    block_pos, face_normal = get_looked_at_block_and_face()
    if block_pos:
        if button == pyglet.window.mouse.LEFT: # 左クリックで破壊
            pos_key = f"{block_pos[0]},{block_pos[1]},{block_pos[2]}"
            if world_data.get(pos_key, 0) != 0: # 空気でなければ削除
                del world_data[pos_key]
                print(f"Broke block at {block_pos}")
                save_world_blocks() # ワールドデータ保存
        elif button == pyglet.window.mouse.RIGHT and face_normal: # 右クリックで設置
            # 設置する位置は、破壊したブロックの隣の面
            place_x = block_pos[0] + int(round(face_normal[0]))
            place_y = block_pos[1] + int(round(face_normal[1]))
            place_z = block_pos[2] + int(round(face_normal[2]))
            
            # プレイヤーが自分自身をブロックで埋めないようにするチェック
            # プレイヤーの簡易バウンディングボックス (足元から頭上まで)
            player_bb_min_x = int(math.floor(camera_x - 0.3))
            player_bb_max_x = int(math.floor(camera_x + 0.3))
            player_bb_min_y = int(math.floor(camera_y - 1.8)) # プレイヤーの高さ約1.8ブロック
            player_bb_max_y = int(math.floor(camera_y + 0.1))
            player_bb_min_z = int(math.floor(camera_z - 0.3))
            player_bb_max_z = int(math.floor(camera_z + 0.3))

            # 設置しようとしているブロックがプレイヤーのバウンディングボックスと重ならないか
            is_overlapping_player = False
            for px in range(player_bb_min_x, player_bb_max_x + 1):
                for py in range(player_bb_min_y, player_bb_max_y + 1):
                    for pz in range(player_bb_min_z, player_bb_max_z + 1):
                        if px == place_x and py == place_y and pz == place_z:
                            is_overlapping_player = True
                            break
                    if is_overlapping_player: break
                if is_overlapping_player: break

            if not is_overlapping_player:
                pos_key = f"{place_x},{place_y},{place_z}"
                world_data[pos_key] = 1 # 仮に草ブロックを設置
                print(f"Placed block at {place_x},{place_y},{place_z}")
                save_world_blocks() # ワールドデータ保存
            else:
                print("Cannot place block inside player.")


def update(dt):
    """ゲームの状態を毎フレーム更新する"""
    global camera_x, camera_y, camera_z, camera_rot_y

    move_speed = 5.0 * dt

    # 前後移動 (W, S)
    if keys[pyglet.window.key.W]:
        camera_x += math.sin(math.radians(camera_rot_y)) * move_speed
        camera_z -= math.cos(math.radians(camera_rot_y)) * move_speed
    if keys[pyglet.window.key.S]:
        camera_x -= math.sin(math.radians(camera_rot_y)) * move_speed
        camera_z += math.cos(math.radians(camera_rot_y)) * move_speed

    # 左右移動 (A, D)
    if keys[pyglet.window.key.A]:
        camera_x -= math.cos(math.radians(camera_rot_y)) * move_speed
        camera_z -= math.sin(math.radians(camera_rot_y)) * move_speed
    if keys[pyglet.window.key.D]:
        camera_x += math.cos(math.radians(camera_rot_y)) * move_speed
        camera_z += math.sin(math.radians(camera_rot_y)) * move_speed

    # 上下移動 (SPACE, LSHIFT)
    if keys[pyglet.window.key.SPACE]:
        camera_y += move_speed
    if keys[pyglet.window.key.LSHIFT]:
        camera_y -= move_speed
    
    # プレイヤー位置の保存（例：5秒に1回）
    if update.counter % (5 * 60) == 0: # 60FPSの場合、5秒に1回
        save_player_position()
    update.counter += 1

update.counter = 0 # カウンターを初期化

pyglet.clock.schedule_interval(update, 1/60.0)

# マウスカーソルを非表示にしてウィンドウの中心に固定
window.set_mouse_visible(False)
window.set_exclusive_mouse(True)

# ゲーム開始時にワールドデータをロード
load_world_blocks()

# アプリケーションの実行
pyglet.app.run()
