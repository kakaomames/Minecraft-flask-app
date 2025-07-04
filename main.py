# app.pyに追記
from flask import Flask, render_template, request, redirect, url_for, session
import hashlib
import json
import os
import uuid
import requests
from dotenv import load_dotenv # 追加
import base64

# .envファイルをロード
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24) # セッションを有効にするための秘密鍵

# --- GitHub API 設定 ---
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN') # 環境変数からPATを読み込む
GITHUB_OWNER = os.getenv('GITHUB_OWNER') # .envから読み込む
GITHUB_REPO = os.getenv('GITHUB_REPO')   # .envから読み込む

GITHUB_API_BASE_URL = f'https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents'
HEADERS = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.v3+json',
    'User-Agent': 'Flask-Minecraft-App'

# 保存先のディレクトリを設定
DATA_DIR = 'data'
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

PLAYER_DATA_FILE = os.path.join(DATA_DIR, 'player_data.json')
WORLD_DATA_DIR = os.path.join(DATA_DIR, 'worlds')
if not os.path.exists(WORLD_DATA_DIR):
    os.makedirs(WORLD_DATA_DIR)

# プレイヤーデータを読み込む関数（初回起動時にファイルがなければ空のリストを返す）
def load_player_data():
    if os.path.exists(PLAYER_DATA_FILE):
        with open(PLAYER_DATA_FILE, 'r') as f:
            return json.load(f)
    return []

# プレイヤーデータを保存する関数
def save_player_data(data):
    with open(PLAYER_DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# ワールドデータを読み込む関数
def load_world_data(player_uuid):
    worlds = []
    for filename in os.listdir(WORLD_DATA_DIR):
        if filename.startswith(f'{player_uuid}-') and filename.endswith('.json'):
            with open(os.path.join(WORLD_DATA_DIR, filename), 'r') as f:
                worlds.append(json.load(f))
    return worlds


@app.route('/New-World', methods=['GET', 'POST'])
def new_world():
    if 'player_uuid' not in session:
        return redirect(url_for('login')) # ログインしていなければログインページへ
    
    if request.method == 'POST':
        world_name = request.form['world_name']
        seed = request.form['seed']
        game_mode = request.form['game_mode']
        cheats_enabled = 'cheats_enabled' in request.form
        # リソース/ビヘイビアパックは今回はダミーとして扱う
        # selected_resource_packs = request.form.getlist('resource_packs')
        # selected_behavior_packs = request.form.getlist('behavior_packs')

        player_uuid = session['player_uuid']

        world_data = {
            'player_uuid': player_uuid,
            'world_name': world_name,
            'seed': seed,
            'game_mode': game_mode,
            'cheats_enabled': cheats_enabled,
            'resource_packs': [], # ダミー
            'behavior_packs': [] # ダミー
        }

        # ファイル名形式: ${プレイヤーのuuid}-${world-name}.json
        world_filename = os.path.join(WORLD_DATA_DIR, f'{player_uuid}-{world_name}.json')
        with open(world_filename, 'w') as f:
            json.dump(world_data, f, indent=4)
        
        return redirect(url_for('menu')) # 作成後メニューに戻る

    return render_template('new_world.html')

@app.route('/World-setting', methods=['GET', 'POST'])
def world_setting():
    if 'player_uuid' not in session:
        return redirect(url_for('login')) # ログインしていなければログインページへ
    
    # ログインしているプレイヤーのワールドリストを取得
    player_uuid = session['player_uuid']
    available_worlds = load_world_data(player_uuid)

    if request.method == 'POST':
        selected_world_name = request.form['selected_world']
        game_mode = request.form['game_mode']
        cheats_enabled = 'cheats_enabled' in request.form
        # リソース/ビヘイビアパックは今回はダミーとして扱う

        # 該当ワールドのファイルを読み込み、更新して保存
        world_filename = os.path.join(WORLD_DATA_DIR, f'{player_uuid}-{selected_world_name}.json')
        if os.path.exists(world_filename):
            with open(world_filename, 'r') as f:
                world_data = json.load(f)
            
            world_data['game_mode'] = game_mode
            world_data['cheats_enabled'] = cheats_enabled
            # リソース/ビヘイビアパックの更新ロジックもここに追加

            with open(world_filename, 'w') as f:
                json.dump(world_data, f, indent=4)
        
        return redirect(url_for('menu')) # 設定保存後メニューに戻る

    return render_template('world_setting.html', worlds=available_worlds)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        players = load_player_data()
        authenticated = False
        
        for player in players:
            # 簡易的なパスワードハッシュ照合（実際はbcryptなどを使う）
            if player['username'] == username and player['password_hash'] == hashlib.sha256(password.encode()).hexdigest():
                # UUIDも確認
                if player['uuid'] == request.form.get('uuid_input', player['uuid']): # uuid_inputは登録時のみ利用、ログイン時はパスワードのみで照合
                    session['username'] = username
                    session['player_uuid'] = player['uuid']
                    authenticated = True
                    return redirect(url_for('menu'))
        
        if not authenticated:
            # ログイン失敗時はエラーメッセージを表示するなど
            return render_template('login.html', error='ユーザー名またはパスワードが違います。')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('player_uuid', None)
    return redirect(url_for('home'))

# app.pyの既存のmenu関数を更新
@app.route('/menu')
def menu():
    if 'player_uuid' not in session:
        return redirect(url_for('login')) # ログインしていなければログインページへ

    player_uuid = session['player_uuid']
    player_worlds = load_world_data(player_uuid)
    
    return render_template('menu.html', worlds=player_worlds)


# 仮のユーザー登録機能（デバッグ用、本番では別の登録フローが必要）
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        players = load_player_data()
        
        # ユーザー名が既に存在しないかチェック
        if any(p['username'] == username for p in players):
            return render_template('register.html', error='このユーザー名はすでに使用されています。')
        
        # 新しいUUIDを生成
        new_uuid = str(uuid.uuid4())
        
        # パスワードをハッシュ化して保存
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        new_player = {
            'username': username,
            'password_hash': hashed_password,
            'uuid': new_uuid
        }
        
        players.append(new_player)
        save_player_data(players)
        
        return redirect(url_for('login')) # 登録後ログインページへ
    return render_template('register.html')

if __name__ == '__main__':
    # GitHubのUser-Agentポリシーに準拠するため、必要な環境変数が設定されているか確認
    if not GITHUB_TOKEN or not GITHUB_OWNER or not GITHUB_REPO:
        print("エラー: .env ファイルに GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO が設定されていません。")
        print(".env ファイルを作成し、必要な情報を記述してください。")
        exit(1)
    
    app.run(debug=True)
