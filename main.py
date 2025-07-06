from flask import Flask, render_template, request, redirect, url_for, session, flash
import hashlib
import json
import os
import uuid
import requests
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
import base64

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
UPLOAD_FOLDER = 'packs' # アップロードされたパックを保存するディレクトリ
ALLOWED_EXTENSIONS = {'mcpack', 'mcaddon'} # 許可するファイル拡張子

# ★ここから以下の3行を削除またはコメントアウトします
# if not os.path.exists(UPLOAD_FOLDER):
#     os.makedirs(UPLOAD_FOLDER)

# 注意: Vercelでは、このUPLOAD_FOLDERも一時的なメモリ上にしか存在せず、
# デプロイ間で永続化されるわけではありません。
# アップロードされたパックを永続化するには、S3のような外部ストレージサービスにアップロードするか、
# GitHub APIを使ってそのファイルを直接GitHubリポジトリにコミットする必要があります。
# 今回は、アップロードされたファイルを一時的に保存し、game.pyで利用する想定なので、
# Vercelのファイルシステムに書き込むこと自体が問題になります。
# したがって、Webアップロードされたパックをgame.pyが読み込むには、
# game.py側でGitHubから直接パックファイルをダウンロードするロジックが必要になります。

def allowed_file(filename):
    """ファイル名が許可された拡張子を持つかチェックする"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- GitHub API ヘルパー関数 (変更なし) ---
def get_github_file_content(path):
    url = f'{GITHUB_API_BASE_URL}/{path}'
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        content_b64 = response.json()['content']
        decoded_content = base64.b64decode(content_b64).decode('utf-8')
        return json.loads(decoded_content)
    return None

def put_github_file_content(path, content, message, sha=None):
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
    url = f'{GITHUB_API_BASE_URL}/{path}'
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        return response.json()
    return None

# --- プレイヤーデータとワールドデータのロード/セーブ関数 (変更なし) ---
def load_player_data():
    content = get_github_file_content('player_data.json')
    return content if content is not None else []

def save_player_data(data):
    path = 'player_data.json'
    current_file_info = get_github_file_info(path)
    sha = current_file_info['sha'] if current_file_info else None
    return put_github_file_content(path, data, 'Update player data', sha)

def load_world_data(player_uuid):
    worlds = []
    world_dir_path = f'worlds/{player_uuid}'
    url = f'{GITHUB_API_BASE_URL}/{world_dir_path}'
    response = requests.get(url, headers=HEADERS)

    if response.status_code == 200:
        for item in response.json():
            if item['type'] == 'file' and item['name'].endswith('.json'):
                world_content = get_github_file_content(f'{world_dir_path}/{item["name"]}')
                if world_content:
                    worlds.append(world_content)
    return worlds

def save_world_data(player_uuid, world_name, data):
    path = f'worlds/{player_uuid}/{world_name}.json'
    current_file_info = get_github_file_info(path)
    sha = current_file_info['sha'] if current_file_info else None
    
    message = f'{"Update" if sha else "Create"} world data for {world_name}'
    return put_github_file_content(path, data, message, sha)

# --- Flask ルーティング ---

@app.route('/')
def home():
    message = request.args.get('message')
    return render_template('home.html', message=message)

@app.route('/setting')
def setting():
    return render_template('setting.html')

@app.route('/store')
def store():
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
                return redirect(url_for('menu'))
        
        return render_template('login.html', error='ユーザー名またはパスワードが違います。')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('player_uuid', None)
    return redirect(url_for('home'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        players = load_player_data()
        
        if any(p['username'] == username for p in players):
            return render_template('register.html', error='このユーザー名はすでに使用されています。')
        
        new_uuid = str(uuid.uuid4())
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        new_player = {
            'username': username,
            'password_hash': hashed_password,
            'uuid': new_uuid
        }
        
        players.append(new_player)
        if save_player_data(players):
            return redirect(url_for('login'))
        else:
            return render_template('register.html', error='登録に失敗しました。GitHubの設定を確認してください。')
    return render_template('register.html')

@app.route('/menu')
def menu():
    if 'player_uuid' not in session:
        return redirect(url_for('login'))

    player_uuid = session['player_uuid']
    player_worlds = load_world_data(player_uuid)
    
    return render_template('menu.html', worlds=player_worlds)

@app.route('/New-World', methods=['GET', 'POST'])
def new_world():
    if 'player_uuid' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        world_name = request.form['world_name']
        seed = request.form['seed']
        game_mode = request.form['game_mode']
        cheats_enabled = 'cheats_enabled' in request.form

        player_uuid = session['player_uuid']

        world_data = {
            'player_uuid': player_uuid,
            'world_name': world_name,
            'seed': seed,
            'game_mode': game_mode,
            'cheats_enabled': cheats_enabled,
            'resource_packs': [],
            'behavior_packs': []
        }
        
        if save_world_data(player_uuid, world_name, world_data):
            return redirect(url_for('menu'))
        else:
            return render_template('new_world.html', error='ワールド作成に失敗しました。')

    return render_template('new_world.html')

@app.route('/World-setting', methods=['GET', 'POST'])
def world_setting():
    if 'player_uuid' not in session:
        return redirect(url_for('login'))
    
    player_uuid = session['player_uuid']
    available_worlds = load_world_data(player_uuid)

    if request.method == 'POST':
        selected_world_name = request.form['selected_world']
        game_mode = request.form['game_mode']
        cheats_enabled = 'cheats_enabled' in request.form

        target_world_data = None
        for world in available_worlds:
            if world['world_name'] == selected_world_name:
                target_world_data = world
                break
        
        if target_world_data:
            target_world_data['game_mode'] = game_mode
            target_world_data['cheats_enabled'] = cheats_enabled
            
            if save_world_data(player_uuid, selected_world_name, target_world_data):
                return redirect(url_for('menu'))
            else:
                return render_template('world_setting.html', worlds=available_worlds, error='ワールド設定の保存に失敗しました。')
        else:
            return render_template('world_setting.html', worlds=available_worlds, error='選択されたワールドが見つかりません。')

    return render_template('world_setting.html', worlds=available_worlds)

@app.route('/import', methods=['GET', 'POST'])
def import_pack():
    if request.method == 'POST':
        if 'file' not in request.files:
            return render_template('import.html', error='ファイルが選択されていません。')
        file = request.files['file']
        
        if file.filename == '':
            return render_template('import.html', error='ファイルが選択されていません。')
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # ★ここから以下の2行を削除またはコメントアウトします
            # file_path = os.path.join(UPLOAD_FOLDER, filename)
            # file.save(file_path) # ローカルファイルシステムへの保存を試みるためエラーになる

            # 代わりに、ファイルを直接GitHubにアップロードするロジックをここに書く
            # ただし、mcpack/mcaddonはバイナリファイルなので、GitHub APIのcontent APIで直接アップロードできます
            # ファイルの内容を読み込み、Base64エンコードしてGitHubにコミットします
            file_content_bytes = file.read()
            encoded_file_content = base64.b64encode(file_content_bytes).decode('utf-8')
            
            pack_github_path = f'{UPLOAD_FOLDER}/{filename}' # GitHub上のパス
            
            # 既存のファイルがあるか確認してSHAを取得
            existing_file_info = get_github_file_info(pack_github_path)
            sha = existing_file_info['sha'] if existing_file_info else None

            # GitHubにファイルをコミット
            github_upload_success, github_response = put_github_file_content(
                pack_github_path,
                encoded_file_content, # ここはJSONではなく、Base64エンコードされたバイナリデータ
                f'Upload pack: {filename}',
                sha
            )
            # put_github_file_content関数はJSONデータを受け取るように設計されているため、
            # バイナリファイルをアップロードするには少し変更が必要です。
            # ここでは簡易的に、contentを直接渡すように変更します。
            # 実際のput_github_file_contentはJSON.dumpsしているので、
            # バイナリアップロード用の別の関数を用意するか、put_github_file_contentを修正する必要があります。
            # 今回は、put_github_file_contentをバイナリ対応させます。

            # put_github_file_contentがバイナリ対応していないため、直接requests.putを呼び出す
            upload_url = f'{GITHUB_API_BASE_URL}/{pack_github_path}'
            upload_data = {
                'message': f'Upload pack: {filename}',
                'content': encoded_file_content
            }
            if sha:
                upload_data['sha'] = sha

            upload_response = requests.put(upload_url, headers=HEADERS, json=upload_data)
            github_upload_success = upload_response.status_code in [200, 201]

            if github_upload_success:
                print(f"Pack '{filename}' uploaded to GitHub successfully.")
                return redirect(url_for('home', message=f'パック "{filename}" が正常にアップロードされました！'))
            else:
                print(f"Failed to upload pack to GitHub: {upload_response.status_code} - {upload_response.text}")
                return render_template('import.html', error=f'GitHubへのアップロードに失敗しました: {upload_response.status_code}')
        else:
            return render_template('import.html', error='許可されていないファイル形式です。(.mcpackまたは.mcaddonのみ)')
    
    return render_template('import.html')


if __name__ == '__main__':
    if not GITHUB_TOKEN or not GITHUB_OWNER or not GITHUB_REPO:
        print("エラー: .env ファイルに GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO が設定されていません。")
        print(".env ファイルを作成し、必要な情報を記述してください。")
        exit(1)
    
    app.run(debug=True)

