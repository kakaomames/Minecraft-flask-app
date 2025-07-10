import os
import pyglet
from pyglet.gl import * # OpenGL関数をインポート
import requests
import base64 # GitHub APIがBase64でコンテンツを返す場合のためにインポート
from io import BytesIO # バイトデータをファイルライクオブジェクトとして扱うためにインポート
import traceback # エラーの詳細なトレースバックを出力するためにインポート

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

# --- ゲームの初期化 ---
def setup_game():
    global block_texture
    print("\n--- ゲームの初期化 ---")

    # リソースパックが選択されている場合、最初のパックからテクスチャをロード
    if resource_pack_paths:
        first_pack_path = resource_pack_paths[0]
        # Minecraftのリソースパック内の一般的なテクスチャパスの例
        # このパスは、アップロードするパックの実際の構造に合わせて調整してください。
        # 例: resourcePack.vanilla_server.name/textures/block/dirt.png
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
            block_texture = pyglet.image.create(32, 32, pyglet.image.SolidColorImagePattern((255, 0, 0, 255))) # フォールバック：赤色
    else:
        print("WARNING: リソースパックが選択されていません。フォールバックの緑色テクスチャを使用します。")
        block_texture = pyglet.image.create(32, 32, pyglet.image.SolidColorImagePattern((0, 255, 0, 255))) # フォールバック：緑色

    # OpenGLの3D描画設定
    glEnable(GL_DEPTH_TEST) # 3Dのための深度テストを有効にする
    glEnable(GL_TEXTURE_2D) # 2Dテクスチャを有効にする
    glMatrixMode(GL_PROJECTION) # プロジェクション行列モードに切り替え
    glLoadIdentity() # 行列をリセット
    gluPerspective(60, WINDOW_WIDTH / WINDOW_HEIGHT, 0.1, 100.0) # 透視投影を設定
    glMatrixMode(GL_MODELVIEW) # モデルビュー行列モードに切り替え
    glLoadIdentity()
    # カメラ位置 (x,y,z, 注視点x,y,z, 上方向x,y,z)
    gluLookAt(0, 0, 5, 0, 0, 0, 0, 1, 0) 

# --- 描画イベントハンドラ ---
@window.event
def on_draw():
    """
    ウィンドウが再描画されるたびに呼び出されるイベントハンドラ。
    """
    window.clear() # 画面をクリア
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT) # カラーバッファと深度バッファをクリア

    glLoadIdentity()
    gluLookAt(0, 0, 5, 0, 0, 0, 0, 1, 0) # カメラ位置を維持

    # テクスチャ付きの四角形を描画
    if block_texture:
        block_texture.bind() # テクスチャをバインド
        glBegin(GL_QUADS)
        glColor3f(1.0, 1.0, 1.0) # テクスチャ本来の色を見るために色を白に設定
        # キューブの前面 (簡略化して四角形として描画)
        glTexCoord2f(0.0, 0.0); glVertex3f(-1.0, -1.0, 0.0)
        glTexCoord2f(1.0, 0.0); glVertex3f( 1.0, -1.0, 0.0)
        glTexCoord2f(1.0, 1.0); glVertex3f( 1.0,  1.0, 0.0)
        glTexCoord2f(0.0, 1.0); glVertex3f(-1.0,  1.0, 0.0)
        glEnd()
    else:
        # テクスチャがロードされなかった場合のフォールバック
        glBegin(GL_QUADS)
        glColor3f(0.5, 0.5, 0.5) # 灰色
        glVertex3f(-1.0, -1.0, 0.0)
        glVertex3f( 1.0, -1.0, 0.0)
        glVertex3f( 1.0,  1.0, 0.0)
        glVertex3f(-1.0,  1.0, 0.0)
        glEnd()

    # テキスト表示
    label = pyglet.text.Label(f"ワールド: {WORLD_NAME}",
                              font_name='Arial',
                              font_size=18,
                              x=10, y=window.height - 30,
                              anchor_x='left', anchor_y='top', color=(255, 255, 255, 255))
    label.draw()

    label_pack = pyglet.text.Label("パックロード済み: " + (resource_pack_paths[0].split('/')[-1] if resource_pack_paths else "なし"),
                                   font_name='Arial',
                               _size=14,
                               x=10, y=window.height - 60,
                               anchor_x='left', anchor_y='top', color=(255, 255, 0, 255))
    label_pack.draw()


# --- ウィンドウのリサイズイベントハンドラ ---
@window.event
def on_resize(width, height):
    """
    ウィンドウがリサイズされたときに呼び出されるイベントハンドラ。
    OpenGLのビューポートを更新して、描画がウィンドウ全体にフィットするようにします。
    """
    glViewport(0, 0, width, height) # ビューポートを新しいサイズに設定
    glMatrixMode(GL_PROJECTION) # プロジェクション行列モードに切り替え
    glLoadIdentity() # 行列をリセット
    gluPerspective(60, width / height, 0.1, 100.0) # 透視投影を設定
    glMatrixMode(GL_MODELVIEW) # モデルビュー行列モードに切り替え
    return pyglet.event.EVENT_HANDLED # イベントを処理済みとしてマーク

# --- メインゲームループ ---
# アプリケーション実行前にゲームコンポーネントを初期化
setup_game()

print("\n--- Pygletゲームウィンドウを開始します ---")
pyglet.app.run()
print("--- Pygletゲームウィンドウが閉じられました ---")

# ゲーム終了時のメッセージ
print("\n--- ゲームシミュレーション終了 ---")
