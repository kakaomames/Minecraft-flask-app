import os
import pyglet
from pyglet.gl import *
import requests
import base64
from io import BytesIO
import traceback
import math

# 環境変数を取得
WORLD_NAME = os.getenv('WORLD_NAME', 'Default World')
PLAYER_UUID = os.getenv('PLAYER_UUID', 'default-player-uuid')
WORLD_UUID = os.getenv('WORLD_UUID', 'default-world-uuid')
RESOURCE_PACK_PATHS_STR = os.getenv('RESOURCE_PACK_PATHS', '')
BEHAVIOR_PACK_PATHS_STR = os.getenv('BEHAVIOR_PACK_PATHS', '')

# GitHub APIの認証情報も環境変数から取得
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_OWNER = os.getenv('GITHUB_OWNER')
GITHUB_REPO = os.getenv('GITHUB_REPO')

print(f"ゲームを開始します:")
print(f"  ワールド名: {WORLD_NAME}")
print(f"  プレイヤーUUID: {PLAYER_UUID}")
print(f"  ワールドUUID: {WORLD_UUID}")

# パック情報を処理
resource_pack_paths = []
if RESOURCE_PACK_PATHS_STR:
    resource_pack_paths = RESOURCE_PACK_PATHS_STR.split(',')
    print(f"  選択されたリソースパックのGitHubパス: {resource_pack_paths}")
else:
    print("  リソースパックは選択されていません。")

behavior_pack_paths = []
if BEHAVIOR_PACK_PATHS_STR:
    behavior_pack_paths = BEHAVIOR_PACK_PATHS_STR.split(',')
    print(f"  選択されたビヘイビアパックのGitHubパス: {behavior_pack_paths}")
else:
    print("  ビヘイビアパックは選択されていません。")

# --- GitHubからファイルをバイトデータとしてダウンロードするヘルパー関数 ---
def download_github_file_content(github_path):
    """
    GitHubリポジトリから指定されたパスのファイルコンテンツをバイトデータとしてダウンロードします。
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

# グローバルなテクスチャ変数
block_texture = None # 今回はすべてのブロックに同じテクスチャを使用

# --- ワールドデータとブロックタイプ ---
# ワールドデータ: {(x, y, z): block_type_id}
world_data = {}

# シンプルなブロックタイプID
BLOCK_DIRT = 1

# Pygletウィンドウ設定
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
window = pyglet.window.Window(width=WINDOW_WIDTH, height=WINDOW_HEIGHT, 
                              caption=f"Minecraft風ゲーム - {WORLD_NAME}", resizable=True)

# --- カメラとプレイヤーの状態変数 ---
# プレイヤーの初期位置 (ワールドの中心を見下ろす位置に調整)
x, y, z = 8.0, 5.0, 8.0 
# プレイヤーの視点角度 (ヨー: 左右, ピッチ: 上下)
yaw = -45.0 # ワールドの中心を見るように調整
pitch = -30.0 # 少し下を見るように調整

# プレイヤーの移動速度
PLAYER_SPEED = 5.0 # 1秒あたりの移動量

# キー入力の状態を保持する辞書
keys = pyglet.window.key.KeyStateHandler()
window.push_handlers(keys)

# デフォルトのキー割り当て
DEFAULT_KEY_BINDINGS = {
    'forward': pyglet.window.key.W,
    'backward': pyglet.window.key.S,
    'strafe_left': pyglet.window.key.A,
    'strafe_right': pyglet.window.key.D,
    'jump': pyglet.window.key.SPACE,
    'crouch': pyglet.window.key.LSHIFT,
}

# --- ワールド生成関数 ---
def generate_flat_world(width, depth, height, block_type):
    """
    指定されたサイズの平らなワールドを生成します。
    """
    print(f"DEBUG: Generating a flat world of size {width}x{depth} at y={height}...")
    for x_coord in range(width):
        for z_coord in range(depth):
            world_data[(x_coord, height, z_coord)] = block_type
    print(f"DEBUG: World generation complete. Total blocks: {len(world_data)}")

# --- ゲームの初期化 ---
def setup_game():
    global block_texture
    print("\n--- ゲームの初期化 ---")

    # ワールドを生成
    generate_flat_world(16, 16, 0, BLOCK_DIRT) # 16x16の平らな土のワールドをy=0に生成

    # リソースパックからテクスチャをロード
    if resource_pack_paths:
        first_pack_path = resource_pack_paths[0]
        # Minecraftのバニラパックのdirt.pngパスを想定
        # 例: packs_extracted/behavior/resourcePack.vanilla_server.name/textures/block/dirt.png
        texture_github_path = f"{first_pack_path}/textures/block/dirt.png" 
        print(f"DEBUG: 選択されたリソースパックからテクスチャのロードを試行中: {texture_github_path}")
        texture_bytes = download_github_file_content(texture_github_path)

        if texture_bytes:
            try:
                # PygletはBytesIOオブジェクトから画像をロードできます
                block_texture = pyglet.image.load('dummy_name_for_pyglet.png', file=BytesIO(texture_bytes))
                print("INFO: GitHubからブロックテクスチャのロードに成功しました。")
            except Exception as e:
                print(f"ERROR: ダウンロードしたバイトデータから画像をロードできませんでした: {e}")
                traceback.print_exc()
                # ロード失敗時のフォールバック：赤色の四角形
                block_texture = pyglet.image.create(32, 32, pyglet.image.SolidColorImagePattern((255, 0, 0, 255)))
        else:
            print("WARNING: テクスチャのバイトデータがダウンロードされませんでした。フォールバックの赤色テクスチャを使用します。")
            block_texture = pyglet.image.create(32, 32, pyglet.image.SolidColorImagePattern((255, 0, 0, 255)))
    else:
        print("WARNING: リソースパックが選択されていません。フォールバックの緑色テクスチャを使用します。")
        block_texture = pyglet.image.create(32, 32, pyglet.image.SolidColorImagePattern((0, 255, 0, 255)))

    # OpenGLの3D描画設定
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_CULL_FACE)
    glEnable(GL_TEXTURE_2D)
    
    window.set_mouse_visible(False)
    window.set_exclusive_mouse(True)

# --- 描画イベントハンドラ ---
@window.event
def on_draw():
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
    if block_texture:
        block_texture.bind()
        glColor3f(1.0, 1.0, 1.0) # テクスチャ本来の色を見るために色を白に設定
        
        for position, block_type in world_data.items():
            block_x, block_y, block_z = position
            
            glPushMatrix() # 各ブロックの描画前に現在の行列を保存
            glTranslatef(block_x + 0.5, block_y + 0.5, block_z + 0.5) # ブロックの中心に移動 (+0.5はMinecraftの座標系に合わせるため)
            
            # キューブの頂点とテクスチャ座標 (サイズは1x1x1)
            # 前面
            glBegin(GL_QUADS)
            glTexCoord2f(0.0, 0.0); glVertex3f(-0.5, -0.5,  0.5)
            glTexCoord2f(1.0, 0.0); glVertex3f( 0.5, -0.5,  0.5)
            glTexCoord2f(1.0, 1.0); glVertex3f( 0.5,  0.5,  0.5)
            glTexCoord2f(0.0, 1.0); glVertex3f(-0.5,  0.5,  0.5)
            glEnd()

            # 背面
            glBegin(GL_QUADS)
            glTexCoord2f(1.0, 0.0); glVertex3f(-0.5, -0.5, -0.5)
            glTexCoord2f(1.0, 1.0); glVertex3f(-0.5,  0.5, -0.5)
            glTexCoord2f(0.0, 1.0); glVertex3f( 0.5,  0.5, -0.5)
            glTexCoord2f(0.0, 0.0); glVertex3f( 0.5, -0.5, -0.5)
            glEnd()

            # 上面
            glBegin(GL_QUADS)
            glTexCoord2f(0.0, 1.0); glVertex3f(-0.5,  0.5, -0.5)
            glTexCoord2f(0.0, 0.0); glVertex3f(-0.5,  0.5,  0.5)
            glTexCoord2f(1.0, 0.0); glVertex3f( 0.5,  0.5,  0.5)
            glTexCoord2f(1.0, 1.0); glVertex3f( 0.5,  0.5, -0.5)
            glEnd()

            # 下面
            glBegin(GL_QUADS)
            glTexCoord2f(1.0, 1.0); glVertex3f(-0.5, -0.5, -0.5)
            glTexCoord2f(0.0, 1.0); glVertex3f( 0.5, -0.5, -0.5)
            glTexCoord2f(0.0, 0.0); glVertex3f( 0.5, -0.5,  0.5)
            glTexCoord2f(1.0, 0.0); glVertex3f(-0.5, -0.5,  0.5)
            glEnd()

            # 右面
            glBegin(GL_QUADS)
            glTexCoord2f(1.0, 0.0); glVertex3f( 0.5, -0.5, -0.5)
            glTexCoord2f(1.0, 1.0); glVertex3f( 0.5,  0.5, -0.5)
            glTexCoord2f(0.0, 1.0); glVertex3f( 0.5,  0.5,  0.5)
            glTexCoord2f(0.0, 0.0); glVertex3f( 0.5, -0.5,  0.5)
            glEnd()

            # 左面
            glBegin(GL_QUADS)
            glTexCoord2f(0.0, 0.0); glVertex3f(-0.5, -0.5, -0.5)
            glTexCoord2f(1.0, 0.0); glVertex3f(-0.5, -0.5,  0.5)
            glTexCoord2f(1.0, 1.0); glVertex3f(-0.5,  0.5,  0.5)
            glTexCoord2f(0.0, 1.0); glVertex3f(-0.5,  0.5, -0.5)
            glEnd()
            
            glPopMatrix() # ブロックの描画後に保存した行列を復元

    else:
        # テクスチャがロードされなかった場合のフォールバック（色付きキューブ）
        # 各ブロックを個別に描画
        for position, block_type in world_data.items():
            block_x, block_y, block_z = position
            glPushMatrix()
            glTranslatef(block_x + 0.5, block_y + 0.5, block_z + 0.5)
            glBegin(GL_QUADS)
            # 前面 (赤)
            glColor3f(1.0, 0.0, 0.0)
            glVertex3f(-0.5, -0.5,  0.5)
            glVertex3f( 0.5, -0.5,  0.5)
            glVertex3f( 0.5,  0.5,  0.5)
            glVertex3f(-0.5,  0.5,  0.5)
            # 背面 (緑)
            glColor3f(0.0, 1.0, 0.0)
            glVertex3f(-0.5, -0.5, -0.5)
            glVertex3f(-0.5,  0.5, -0.5)
            glVertex3f( 0.5,  0.5, -0.5)
            glVertex3f( 0.5, -0.5, -0.5)
            # 上面 (青)
            glColor3f(0.0, 0.0, 1.0)
            glVertex3f(-0.5,  0.5, -0.5)
            glVertex3f(-0.5,  0.5,  0.5)
            glVertex3f( 0.5,  0.5,  0.5)
            glVertex3f( 0.5,  0.5, -0.5)
            # 下面 (黄)
            glColor3f(1.0, 1.0, 0.0)
            glVertex3f(-0.5, -0.5, -0.5)
            glVertex3f( 0.5, -0.5, -0.5)
            glVertex3f( 0.5, -0.5,  0.5)
            glVertex3f(-0.5, -0.5,  0.5)
            # 右面 (シアン)
            glColor3f(0.0, 1.0, 1.0)
            glVertex3f( 0.5, -0.5, -0.5)
            glVertex3f( 0.5,  0.5, -0.5)
            glVertex3f( 0.5,  0.5,  0.5)
            glVertex3f( 0.5, -0.5,  0.5)
            # 左面 (マゼンタ)
            glColor3f(1.0, 0.0, 1.0)
            glVertex3f(-0.5, -0.5, -0.5)
            glVertex3f(-0.5, -0.5,  0.5)
            glVertex3f(1.0, 1.0); glVertex3f(-0.5,  0.5,  0.5)
            glTexCoord2f(0.0, 1.0); glVertex3f(-0.5,  0.5, -0.5)
            glEnd()
            glPopMatrix()

    # テキスト表示 (2Dオーバーレイ)
    glMatrixMode(GL_PROJECTION)
    glPushMatrix()
    glLoadIdentity()
    gluOrtho2D(0, window.width, 0, window.height)
    glMatrixMode(GL_MODELVIEW)
    glPushMatrix()
    glLoadIdentity()

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

    glPopMatrix()
    glMatrixMode(GL_PROJECTION)
    glPopMatrix()
    glMatrixMode(GL_MODELVIEW)


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
    
    sensitivity = 0.15

    yaw += dx * sensitivity
    pitch -= dy * sensitivity

    if pitch > 90:
        pitch = 90
    if pitch < -90:
        pitch = -90

# --- ゲーム状態の更新関数 ---
def update(dt):
    global x, y, z, yaw, pitch

    s = dt * PLAYER_SPEED

    if keys[DEFAULT_KEY_BINDINGS['forward']]:
        x -= s * math.sin(math.radians(yaw))
        z -= s * math.cos(math.radians(yaw))
    if keys[DEFAULT_KEY_BINDINGS['backward']]:
        x += s * math.sin(math.radians(yaw))
        z += s * math.cos(math.radians(yaw))

    if keys[DEFAULT_KEY_BINDINGS['strafe_left']]:
        x -= s * math.sin(math.radians(yaw - 90))
        z -= s * math.cos(math.radians(yaw - 90))
    if keys[DEFAULT_KEY_BINDINGS['strafe_right']]:
        x += s * math.sin(math.radians(yaw - 90))
        z += s * math.cos(math.radians(yaw - 90))

    if keys[DEFAULT_KEY_BINDINGS['jump']]:
        y += s
    if keys[DEFAULT_KEY_BINDINGS['crouch']]:
        y -= s

# --- メインゲームループ ---
setup_game()

pyglet.clock.schedule_interval(update, 1/60.0)

print("\n--- Pygletゲームウィンドウを開始します ---")
pyglet.app.run()
print("--- Pygletゲームウィンドウが閉じられました ---")

print("\n--- ゲームシミュレーション終了 ---")
