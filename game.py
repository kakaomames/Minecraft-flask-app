import os
import pyglet
from pyglet.gl import *
import requests
import base64
from io import BytesIO
import traceback
import math # 角度計算のためにインポート

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
        'Accept': 'application/vnd.github.com.v3.raw', # 生のコンテンツを直接リクエスト
        'User-Agent': 'Pyglet-Minecraft-Game'
    }

    try:
        print(f"DEBUG: GitHubからダウンロードを試行中: {url}")
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            print(f"DEBUG: {github_path} のダウンロードに成功しました。")
            return response.content # 生のバイトデータを返す
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
block_texture = None

# Pygletウィンドウ設定
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
window = pyglet.window.Window(width=WINDOW_WIDTH, height=WINDOW_HEIGHT, 
                              caption=f"Minecraft風ゲーム - {WORLD_NAME}", resizable=True)

# --- カメラとプレイヤーの状態変数 ---
# プレイヤーの初期位置
x, y, z = 0.0, 0.0, 3.0 # Z軸を少し手前にしてキューブが見えるように
# プレイヤーの視点角度 (ヨー: 左右, ピッチ: 上下)
yaw = 0.0
pitch = 0.0

# --- ゲームの初期化 ---
def setup_game():
    global block_texture
    print("\n--- ゲームの初期化 ---")

    # リソースパックが選択されている場合、最初のパックからテクスチャをロード
    if resource_pack_paths:
        first_pack_path = resource_pack_paths[0]
        # テスト用のテクスチャパス (例: resourcePack.vanilla_server.name/textures/block/dirt.png)
        texture_github_path = f"{first_pack_path}/textures/block/dirt.png" 
        print(f"DEBUG: 選択されたリソースパックからテクスチャのロードを試行中: {texture_github_path}")
        texture_bytes = download_github_file_content(texture_github_path)

        if texture_bytes:
            try:
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
    glEnable(GL_DEPTH_TEST) # 3Dのための深度テストを有効にする
    glEnable(GL_CULL_FACE) # 背面カリングを有効にする (見えない面を描画しない)
    glEnable(GL_TEXTURE_2D) # 2Dテクスチャを有効にする
    
    # マウスカーソルを非表示にし、ウィンドウ中央に固定
    window.set_mouse_visible(False)
    window.set_exclusive_mouse(True) # マウスをウィンドウ内にロック

# --- 描画イベントハンドラ ---
@window.event
def on_draw():
    """
    ウィンドウが再描画されるたびに呼び出されるイベントハンドラ。
    """
    window.clear()
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(60, window.width / window.height, 0.1, 100.0) # 透視投影を設定
    
    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()

    # カメラの回転を適用 (ピッチとヨー)
    glRotatef(pitch, 1, 0, 0) # X軸周りの回転 (上下)
    glRotatef(yaw, 0, 1, 0)   # Y軸周りの回転 (左右)
    
    # プレイヤーの位置を逆方向に移動 (カメラをプレイヤーの位置に合わせる)
    glTranslatef(-x, -y, -z)

    # テクスチャ付きのキューブを描画
    if block_texture:
        block_texture.bind()
        glColor3f(1.0, 1.0, 1.0) # テクスチャ本来の色を見るために色を白に設定
        
        # キューブの頂点とテクスチャ座標
        # 各面に対してテクスチャを適用
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

    else:
        # テクスチャがロードされなかった場合のフォールバック（色付きキューブ）
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
        glVertex3f(-0.5,  0.5,  0.5)
        glVertex3f(-0.5,  0.5, -0.5)
        glEnd()

    # テキスト表示 (2Dオーバーレイ)
    glMatrixMode(GL_PROJECTION)
    glPushMatrix() # 現在のプロジェクション行列を保存
    glLoadIdentity()
    gluOrtho2D(0, window.width, 0, window.height) # 2D正投影に切り替え
    glMatrixMode(GL_MODELVIEW)
    glPushMatrix() # 現在のモデルビュー行列を保存
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

    glPopMatrix() # 保存したモデルビュー行列を復元
    glMatrixMode(GL_PROJECTION)
    glPopMatrix() # 保存したプロジェクション行列を復元
    glMatrixMode(GL_MODELVIEW) # モデルビュー行列モードに戻る


# --- ウィンドウのリサイズイベントハンドラ ---
@window.event
def on_resize(width, height):
    """
    ウィンドウがリサイズされたときに呼び出されるイベントハンドラ。
    OpenGLのビューポートと透視投影を更新します。
    """
    glViewport(0, 0, width, height)
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(60, width / height, 0.1, 100.0)
    glMatrixMode(GL_MODELVIEW)
    return pyglet.event.EVENT_HANDLED

# --- マウス移動イベントハンドラ ---
@window.event
def on_mouse_motion(x, y, dx, dy):
    """
    マウスが移動したときに呼び出されるイベントハンドラ。
    カメラの視点角度 (yaw, pitch) を更新します。
    """
    global yaw, pitch
    
    # マウス感度
    sensitivity = 0.15

    # ヨー (左右) の更新
    yaw += dx * sensitivity
    # ピッチ (上下) の更新
    pitch -= dy * sensitivity # dyは上方向が正なので、視点を下げるにはマイナス

    # ピッチの制限 (上下の回転を制限して、逆さまにならないようにする)
    if pitch > 90:
        pitch = 90
    if pitch < -90:
        pitch = -90

# --- メインゲームループ ---
setup_game()

print("\n--- Pygletゲームウィンドウを開始します ---")
pyglet.app.run()
print("--- Pygletゲームウィンドウが閉じられました ---")

print("\n--- ゲームシミュレーション終了 ---")
