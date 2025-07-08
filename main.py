from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
import hashlib
import json
import os
import uuid
import requests
import base64
from dotenv import load_dotenv
from werkzeug.utils import secure_filename # 忘れずにインポート

# .envファイルをロード
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- GitHub API 設定 ---
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_OWNER = os.getenv('GITHUB_OWNER')
GITHUB_REPO = os.getenv('GITHUB_REPO')

if not GITHUB_TOKEN or not GITHUB_OWNER or not GITHUB_REPO:
    print("エラー: .env ファイルに GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO が設定されていません。")
    print(".env ファイルを作成し、必要な情報を記述してください。")
    exit(1)

GITHUB_API_BASE_URL = f'https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents'
HEADERS = {
    'Authorization': f'token {GITHUB_TOKEN}',
    'Accept': 'application/vnd.github.com.v3+json',
    'User-Agent': 'Flask-Minecraft-App'
}

# --- ファイルアップロード設定 ---
UPLOAD_FOLDER = 'packs'
ALLOWED_EXTENSIONS = {'mcpack', 'mcaddon'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- GitHub API ヘルパー関数 ---
def get_github_file_content(path):
    url = f'{GITHUB_API_BASE_URL}/{path}'
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        content_b64 = response.json()['content']
        decoded_content = base64.b64decode(content_b64).decode('utf-8')
        return json.loads(decoded_content)
    print(f"DEBUG: Failed to get content for {path}. Status: {response.status_code}, Response: {response.text}")
    return None

def put_github_file_content(path, content, message, sha=None):
    url = f'{GITHUB_API_BASE_URL}/{path}'
    
    if isinstance(content, bytes):
        encoded_content = base64.b64encode(content).decode('utf-8')
    elif isinstance(content, str) and content.startswith(('ey', 'PD94bWwgdmVyc2lvbj', 'UEs')):
        encoded_content = content
    else:
        encoded_content = base64.b64encode(json.dumps(content, indent=4).encode('utf-8')).decode('utf-8')

    data = {
        'message': message,
        'content': encoded_content
    }
    if sha:
        data['sha'] = sha

    response = requests.put(url, headers=HEADERS, json=data)
    
    if not response.status_code in [200, 201]:
        print(f"ERROR: GitHub PUT failed for {path}. Status: {response.status_code}, Response: {response.text}")
        try:
            error_json = response.json()
            print(f"GitHub API Error Details: {json.dumps(error_json, indent=2)}")
        except json.JSONDecodeError:
            pass

    return response.status_code in [200, 201], response.json()

def get_github_file_info(path):
    url = f'{GITHUB_API_BASE_URL}/{path}'
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        return response.json()
    if response.status_code not in [404]:
        print(f"DEBUG: Failed to get file info for {path}. Status: {response.status_code}, Response: {response.text}")
    return None

# --- プレイヤーデータとワールドデータのロード/セーブ関数 ---
def load_player_data():
    content = get_github_file_content('player_data.json')
    return content if content is not None else []

def save_player_data(data):
    path = 'player_data.json'
    current_file_info = get_github_file_info(path)
    sha = current_file_info['sha'] if current_file_info else None
    
    success, response = put_github_file_content(path, data, 'Update player data', sha)
    if not success:
        print(f"ERROR: save_player_data failed for {path}. Response: {response}")
    return success

def load_world_data(player_uuid):
    worlds = []
    world_dir_path = f'worlds/{player_uuid}'
    url = f'{GITHUB_API_BASE_URL}/{world_dir_path}'
    response = requests.get(url, headers=HEADERS)

    if response.status_code == 200:
        for item in response.json():
            if item['type'] == 'file' and item['name'].endswith('-block-.json'):
                parts = item['name'].split('-')
                if len(parts) >= 5:
                    world_name = '-'.join(parts[:-4])
                    world_uuid = parts[-2]
                    
                    worlds.append({
                        'world_name': world_name,
                        'world_uuid': world_uuid,
                        'player_uuid': player_uuid
                    })
    else:
        print(f"DEBUG: Failed to load world data for {player_uuid}. Status: {response.status_code}, Response: {response.text}")
    return worlds

def save_world_data(player_uuid, world_name, data):
    world_uuid_for_path = data.get('world_uuid', str(uuid.uuid4()))
    path = f'worlds/{player_uuid}/{world_name}-metadata-{player_uuid}-{world_uuid_for_path}.json'
    
    current_file_info = get_github_file_info(path)
    sha = current_file_info['sha'] if current_file_info else None
    
    message = f'{"Update" if sha else "Create"} world metadata for {world_name}'
    success, response = put_github_file_content(path, data, message, sha)
    if not success:
        print(f"ERROR: save_world_data failed for {path}. Response: {response}")
    return success

# --- Flask ルーティング ---

@app.route('/')
def index(): # ★関数名を'index'に変更 (home関数と重複するため)
    print("indexページを表示しました") # ★print文を移動
    message = request.args.get('message')
    return render_template('index.html', message=message)
    

@app.route('/home')
def home():
    print("ホームページを表示しました") # ★print文を移動
    message = request.args.get('message')
    return render_template('home.html', message=message)
    

@app.route('/setting')
def setting():
    print("設定ページを表示しました") # ★print文を移動
    return render_template('setting.html')
    

@app.route('/store')
def store():
    print("ストアページを表示しました") # ★print文を移動
    return render_template('store.html')
    

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        players = load_player_data()
        
        for player in players:
            if player['username'] == username and player['password_hash'] == hashlib.sha256(password.encode()).hexdigest():
                session['username'] = username
                session['player_uuid'] = player['uuid']
                flash(f"ようこそ、{username}さん！", "success")
                print(f"DEBUG: ユーザー '{username}' がログインしました。") # 追加
                return redirect(url_for('menu'))
        
        flash('ユーザー名またはパスワードが違います。', "error")
        print(f"DEBUG: ログイン失敗 - ユーザー名: {username}") # 追加
        return render_template('login.html')

    print("ログインページを表示しました") # ★print文を移動
    return render_template('login.html')
    

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('player_uuid', None)
    flash("ログアウトしました。", "info")
    print("DEBUG: ユーザーがログアウトしました。") # 追加
    return redirect(url_for('home'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        players = load_player_data()
        
        if any(p['username'] == username for p in players):
            flash('このユーザー名はすでに使用されています。', "error")
            print(f"DEBUG: 登録失敗 - ユーザー名 '{username}' は既に存在します。") # 追加
            return render_template('register.html')
        
        new_uuid = str(uuid.uuid4())
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        new_player = {
            'username': username,
            'password_hash': hashed_password,
            'uuid': new_uuid
        }
        
        players.append(new_player)
        print(f"DEBUG: 新規プレイヤーデータ: {new_player}") # 追加
        if save_player_data(players):
            flash('アカウントが正常に作成されました！ログインしてください。', "success")
            print(f"DEBUG: ユーザー '{username}' のアカウントが正常に作成されました。") # 追加
            return redirect(url_for('login'))
        else:
            flash('アカウント作成に失敗しました。GitHubのトークン権限、リポジトリ名、オーナー名を確認してください。', "error")
            print(f"DEBUG: ユーザー '{username}' のアカウント作成がGitHubへの保存失敗により失敗しました。") # 追加
            return render_template('register.html')
    print("アカウント生成ページを表示しました") # ★print文を移動
    return render_template('register.html')
    

@app.route('/menu')
def menu():
    print("メニューページを表示しました") # ★print文を移動
    player_worlds = []
    if 'player_uuid' in session:
        player_uuid = session['player_uuid']
        player_worlds = load_world_data(player_uuid)
    
    return render_template('menu.html', worlds=player_worlds)
    

@app.route('/New-World', methods=['GET', 'POST'])
def new_world():
    if 'player_uuid' not in session:
        flash("ワールドを作成するにはログインしてください。", "warning")
        print("DEBUG: ワールド作成試行 - 未ログインユーザー。") # 追加
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        world_name = request.form['world_name']
        seed = request.form['seed']
        game_mode = request.form['game_mode']
        cheats_enabled = 'cheats_enabled' in request.form

        player_uuid = session['player_uuid']
        new_world_uuid = str(uuid.uuid4())

        world_metadata = {
            'player_uuid': player_uuid,
            'world_name': world_name,
            'world_uuid': new_world_uuid,
            'seed': seed,
            'game_mode': game_mode,
            'cheats_enabled': cheats_enabled,
            'resource_packs': [],
            'behavior_packs': []
        }
        
        print(f"DEBUG: 新規ワールドメタデータ: {world_metadata}") # 追加
        success = save_world_data(player_uuid, world_name, world_metadata)

        if success:
            flash(f'ワールド "{world_name}" が正常に作成されました！', "success")
            print(f"DEBUG: ワールド '{world_name}' が正常に作成されました。") # 追加
            return redirect(url_for('menu'))
        else:
            flash('ワールド作成に失敗しました。GitHubのトークン権限、リポジトリ名、オーナー名を確認してください。', "error")
            print(f"DEBUG: ワールド '{world_name}' の作成がGitHubへの保存失敗により失敗しました。") # 追加
            return render_template('new_world.html')

    print("ワールド生成ページを表示しました") # ★print文を移動
    return render_template('new_world.html')
    

@app.route('/World-setting', methods=['GET', 'POST'])
def world_setting():
    if 'player_uuid' not in session:
        flash("ワールド設定を変更するにはログインしてください。", "warning")
        print("DEBUG: ワールド設定試行 - 未ログインユーザー。") # 追加
        return redirect(url_for('login'))
    
    player_uuid = session['player_uuid']
    available_worlds = load_world_data(player_uuid)

    if request.method == 'POST':
        selected_world_name = request.form['selected_world']
        game_mode = request.form['game_mode']
        cheats_enabled = 'cheats_enabled' in request.form

        flash("ワールド設定の更新は現在サポートされていません。", "warning")
        print("DEBUG: ワールド設定の更新は現在サポートされていません。") # 追加
        return redirect(url_for('menu'))

    print("ワールド設定ページを表示しました") # ★print文を移動
    return render_template('world_setting.html', worlds=available_worlds)
    

@app.route('/import', methods=['GET', 'POST'])
def import_pack():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('ファイルが選択されていません。', "error")
            print("DEBUG: パックインポート失敗 - ファイルが選択されていません。") # 追加
            return render_template('import.html')
        file = request.files['file']
        
        if file.filename == '':
            flash('ファイルが選択されていません。', "error")
            print("DEBUG: パックインポート失敗 - ファイル名が空です。") # 追加
            return render_template('import.html')
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_content_bytes = file.read()
            
            pack_github_path = f'packs/{filename}'
            
            existing_file_info = get_github_file_info(pack_github_path)
            sha = existing_file_info['sha'] if existing_file_info else None

            github_upload_success, github_response = put_github_file_content(
                pack_github_path,
                file_content_bytes,
                f'Upload pack: {filename}',
                sha
            )

            if github_upload_success:
                print(f"Pack '{filename}' uploaded to GitHub successfully.")
                flash(f'パック "{filename}" が正常にアップロードされました！', "success")
                return redirect(url_for('home'))
            else:
                error_message = github_response.get('message', 'Unknown error')
                print(f"Failed to upload pack to GitHub: {error_message}")
                flash(f'GitHubへのアップロードに失敗しました: {error_message}', "error")
                return render_template('import.html')
        else:
            flash('許可されていないファイル形式です。(.mcpackまたは.mcaddonのみ)', "error")
            print("DEBUG: パックインポート失敗 - 許可されていないファイル形式です。") # 追加
            return render_template('import.html')
    
    print("インポートページを表示しました") # ★print文を移動
    return render_template('import.html')
    

@app.route('/play/<world_name>/<world_uuid>')
def play_game(world_name, world_uuid):
    print(f"プレイページを表示しました: ワールド名={world_name}, ワールドUUID={world_uuid}") # ★print文を移動
    if 'player_uuid' not in session:
        flash("ゲームをプレイするにはログインしてください。", "warning")
        print("DEBUG: プレイ試行 - 未ログインユーザー。") # 追加
        return redirect(url_for('login'))

    player_uuid = session['player_uuid']

    user_agent = request.headers.get('User-Agent', '').lower()
    if 'windows' in user_agent:
        script_content = f"""@echo off
SET WORLD_NAME={world_name}
SET PLAYER_UUID={player_uuid}
SET WORLD_UUID={world_uuid}
python game.py
PAUSE
"""
        filename = f"launch_{world_name}.bat"
        mimetype = "application/x-bat"
    else:
        script_content = f"""#!/bin/bash
export WORLD_NAME="{world_name}"
export PLAYER_UUID="{player_uuid}"
export WORLD_UUID="{world_uuid}"
python3 game.py
echo "Press any key to continue..."
read -n 1 -s
"""
        filename = f"launch_{world_name}.sh"
        mimetype = "application/x-sh"

    response = Response(script_content, mimetype=mimetype)
    response.headers.set("Content-Disposition", "attachment", filename=filename)
    print(f"DEBUG: ランチャースクリプト '{filename}' を生成しました。") # 追加
    return response


if __name__ == '__main__':
    if not GITHUB_TOKEN or not GITHUB_OWNER or not GITHUB_REPO:
        print("エラー: .env ファイルに GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO が設定されていません。")
        print(".env ファイルを作成し、必要な情報を記述してください。")
        exit(1)
    
    app.run(debug=True)

