import pyglet
from pyglet.gl import *
import math

# ウィンドウの作成
window = pyglet.window.Window(width=800, height=600, caption='Cave Game Test', resizable=True)

# OpenGLの設定
# 3D描画に必要な深度テストを有効にする
glEnable(GL_DEPTH_TEST)
# 面の法線に基づいて裏面を描画しないようにする（パフォーマンス向上）
glEnable(GL_CULL_FACE)

# カメラの位置と向きを管理する変数
camera_x, camera_y, camera_z = 0.0, 0.0, -5.0 # カメラの初期位置
camera_rot_x, camera_rot_y = 0.0, 0.0       # カメラの初期回転（ピッチ、ヨー）

# マウスの移動量でカメラの回転を制御するための変数
mouse_dx, mouse_dy = 0, 0
mouse_sensitivity = 0.1

# キー入力の状態を管理する変数
keys = pyglet.window.key.KeyStateHandler()
window.push_handlers(keys)

# ブロックの頂点データ (立方体)
# OpenGLの頂点データは、通常、頂点の座標、色、法線、テクスチャ座標などを含む
# ここでは簡易的に、色付きの立方体を直接描画する
def draw_cube():
    glBegin(GL_QUADS)

    # 前面 (Z+)
    glColor3f(1.0, 0.0, 0.0) # 赤
    glVertex3f(-0.5, -0.5, 0.5)
    glVertex3f( 0.5, -0.5, 0.5)
    glVertex3f( 0.5,  0.5, 0.5)
    glVertex3f(-0.5,  0.5, 0.5)

    # 後面 (Z-)
    glColor3f(0.0, 1.0, 0.0) # 緑
    glVertex3f(-0.5, -0.5, -0.5)
    glVertex3f(-0.5,  0.5, -0.5)
    glVertex3f( 0.5,  0.5, -0.5)
    glVertex3f( 0.5, -0.5, -0.5)

    # 上面 (Y+)
    glColor3f(0.0, 0.0, 1.0) # 青
    glVertex3f(-0.5,  0.5, -0.5)
    glVertex3f(-0.5,  0.5,  0.5)
    glVertex3f( 0.5,  0.5,  0.5)
    glVertex3f( 0.5,  0.5, -0.5)

    # 下面 (Y-)
    glColor3f(1.0, 1.0, 0.0) # 黄
    glVertex3f(-0.5, -0.5, -0.5)
    glVertex3f( 0.5, -0.5, -0.5)
    glVertex3f( 0.5, -0.5,  0.5)
    glVertex3f(-0.5, -0.5,  0.5)

    # 右面 (X+)
    glColor3f(1.0, 0.0, 1.0) # マゼンタ
    glVertex3f( 0.5, -0.5, -0.5)
    glVertex3f( 0.5,  0.5, -0.5)
    glVertex3f( 0.5,  0.5,  0.5)
    glVertex3f( 0.5, -0.5,  0.5)

    # 左面 (X-)
    glColor3f(0.0, 1.0, 1.0) # シアン
    glVertex3f(-0.5, -0.5, -0.5)
    glVertex3f(-0.5, -0.5,  0.5)
    glVertex3f(-0.5,  0.5,  0.5)
    glVertex3f(-0.5,  0.5, -0.5)

    glEnd()

@window.event
def on_draw():
    window.clear() # 画面をクリア

    # モデルビュー行列と射影行列を初期化
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    # 視錐台を設定 (視野角, アスペクト比, 近クリップ面, 遠クリップ面)
    gluPerspective(75, window.width / window.height, 0.1, 100.0)

    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()

    # カメラの回転を適用
    glRotatef(-camera_rot_x, 1, 0, 0) # ピッチ
    glRotatef(-camera_rot_y, 0, 1, 0) # ヨー
    
    # カメラの平行移動を適用 (カメラを動かすのではなく、シーン全体を逆方向に動かす)
    glTranslatef(-camera_x, -camera_y, -camera_z)

    # ここにワールドの描画ロジックを書く
    # 今は原点に単一のブロックを描画
    draw_cube()

@window.event
def on_mouse_motion(x, y, dx, dy):
    global camera_rot_y, camera_rot_x
    # マウスの移動量に応じてカメラの回転を更新
    camera_rot_y += dx * mouse_sensitivity
    camera_rot_x += dy * mouse_sensitivity
    
    # ピッチの制限 (上下を見上げすぎたり見下ろしすぎたりしないように)
    if camera_rot_x > 90: camera_rot_x = 90
    if camera_rot_x < -90: camera_rot_x = -90

# フレームごとの更新（キー入力処理など）
def update(dt):
    global camera_x, camera_y, camera_z, camera_rot_y

    move_speed = 5.0 * dt # 1秒あたり5単位移動

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

# update関数を毎秒60回呼び出すようにスケジュール
pyglet.clock.schedule_interval(update, 1/60.0)

# マウスカーソルを非表示にしてウィンドウの中心に固定
window.set_mouse_visible(False)
window.set_exclusive_mouse(True)

# アプリケーションの実行
pyglet.app.run()
