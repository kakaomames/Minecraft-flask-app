from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
import hashlib
import json
import os
import uuid
import requests
import base64
from dotenv import load_dotenv
import random # オフラインプレイヤー名生成用
import string # オフラインプレイヤー名生成用

# .envファイルをロード
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

# --- GitHub API 設定 ---
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_OWNER = os.getenv('GITHUB_OWNER')
GITHUB_REPO = os.getenv('GITHUB_REPO')

# GitHub設定を起動時にチェックする関数
def check_github_config():
    """
    GitHubトークン、オーナー、リポジトリの設定をチェックし、
    APIへのアクセスが可能か検証する。
    問題があればエラーメッセージを出力し、Falseを返す。
    """
    print("\n--- GitHub設定の初期チェックを開始します ---")

    if not GITHUB_TOKEN:
        print("エラー: GITHUB_TOKEN が .env ファイルに設定されていません。")
        print("GitHub Personal Access Tokenを生成し、.envファイルに 'GITHUB_TOKEN=\"YOUR_TOKEN_HERE\"' の形式で設定してください。")
        return False
    if not GITHUB_OWNER or not GITHUB_REPO:
        print("エラー: GITHUB_OWNER または GITHUB_REPO が .env ファイルに設定されていません。")
        print(".envファイルに 'GITHUB_OWNER=\"あなたのGitHubユーザー名\"' と 'GITHUB_REPO=\"あなたのリポジトリ名\"' を設定してください。")
        return False

    api_base_url = f'https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents'
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.com.v3+json',
        'User-Agent': 'Flask-Minecraft-App-Startup-Check'
    }

    test_file_path = 'player_data.json'
    url = f'{api_base_url}/{test_file_path}'

    print(f"DEBUG: GitHub APIアクセスをテスト中: {url}")
    print(f"DEBUG: GITHUB_OWNER: {GITHUB_OWNER}")
    print(f"DEBUG: GITHUB_REPO: {GITHUB_REPO}")
    print(f"DEBUG: GITHUB_TOKEN (最初の5文字): {GITHUB_TOKEN[:5]}*****")

    try:
        response = requests.get(url, headers=headers)

        print(f"DEBUG: レスポンスステータスコード: {response.status_code}")
        # print(f"DEBUG: レスポンスボディ: {response.text}") # 長いのでコメントアウト

        if response.status_code == 200 or response.status_code == 404:
            print("成功: GitHub APIへのアクセスが確認できました。トークンとリポジトリ設定は有効です。")
            print("--- GitHub設定の初期チェックを完了しました ---\n")
            return True
        elif response.status_code == 401:
            print("\nエラー: 401 Unauthorized - 認証情報が無効です（Bad credentials）。")
            print("GitHubトークンが間違っているか、期限切れか、権限が不足しています。")
            print("GitHubで新しいトークンを生成し、'repo'スコープ（または'Contents'の'Read and write'）を付与して、.envファイルを更新してください。")
            return False
        elif response.status_code == 403:
            print("\nエラー: 403 Forbidden - アクセスが拒否されました。")
            print("トークンにリポジトリへのアクセス権限がありません（例: プライベートリポジトリへのアクセス）。")
            print("GitHubトークンの権限（スコープ）が不足している可能性があります。'repo'スコープが付与されているか確認してください。")
            return False
        else:
            print(f"\n予期せぬエラー: Status {response.status_code}")
            print(f"GitHub APIからの応答: {response.text}")
            print("GitHub APIへのアクセス中に問題が発生しました。")
            return False

    except requests.exceptions.RequestException as e:
        print(f"\nネットワークエラーが発生しました: {e}")
        print("GitHub APIに接続できませんでした。インターネット接続を確認するか、GitHubのステータスを確認してください。")
        return False

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
        try:
            json_response = response.json()
            content_b64 = json_response.get('content')
            
            if content_b64:
                decoded_content = base64.b64decode(content_b64).decode('utf-8')
                if decoded_content.strip():
                    return json.loads(decoded_content)
                else:
                    print(f"DEBUG: Decoded content for {path} is empty or whitespace only.")
                    return None
            else:
                print(f"DEBUG: 'content' key not found in GitHub API response for {path}.")
                return None
        except json.JSONDecodeError as e:
            print(f"ERROR: JSONDecodeError when parsing GitHub API response for {path}: {e}")
            print(f"Response text: {response.text[:200]}...")
            return None
        except Exception as e:
            print(f"ERROR: Unexpected error in get_github_file_content for {path}: {e}")
            return None
    elif response.status_code == 404:
        print(f"DEBUG: File not found on GitHub: {path}. Status: 404.")
        return None
    else:
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

# --- プレイヤーデータ管理のリファクタリング ---
PLAYERS_DIR_PATH = 'players' # プレイヤーデータを格納するGitHub上のディレクトリ

def load_all_player_data():
    """GitHubの'players/'ディレクトリからすべてのプレイヤーデータをロードする"""
    all_players = []
    url = f'{GITHUB_API_BASE_URL}/{PLAYERS_DIR_PATH}'
    response = requests.get(url, headers=HEADERS)

    if response.status_code == 200:
        print(f"DEBUG: Listing contents of {PLAYERS_DIR_PATH}. Items found: {len(response.json())}")
        for item in response.json():
            if item['type'] == 'file' and item['name'].endswith('.json'):
                player_file_path = f'{PLAYERS_DIR_PATH}/{item["name"]}'
                print(f"DEBUG: Attempting to load player data from: {player_file_path}")
                player_content = get_github_file_content(player_file_path)
                if player_content:
                    all_players.append(player_content)
                    print(f"DEBUG: Successfully loaded player: {player_content.get('username', 'N/A')}")
                else:
                    print(f"DEBUG: Could not load player data from {player_file_path}. Skipping.")
    elif response.status_code == 404:
        print(f"DEBUG: Players directory '{PLAYERS_DIR_PATH}' not found on GitHub. Assuming no players yet.")
    else:
        print(f"DEBUG: Failed to list players directory {PLAYERS_DIR_PATH}. Status: {response.status_code}, Response: {response.text}")
    return all_players

def save_single_player_data(player_data):
    """単一のプレイヤーデータをGitHubに保存する (players/{uuid}.json)"""
    player_uuid = player_data.get('uuid')
    if not player_uuid:
        print("ERROR: Player data has no UUID. Cannot save.")
        return False, {"message": "Player data missing UUID"}

    path = f'{PLAYERS_DIR_PATH}/{player_uuid}.json'
    current_file_info = get_github_file_info(path)
    sha = current_file_info['sha'] if current_file_info else None
    
    message = f'{"Update" if sha else "Create"} player data for {player_data.get("username", "unknown")}'
    success, response = put_github_file_content(path, player_data, message, sha)
    if not success:
        print(f"ERROR: save_single_player_data failed for {path}. Response: {response}")
    return success, response


def load_world_data(player_uuid):
    worlds = []
    world_dir_path = f'worlds/{player_uuid}'
    url = f'{GITHUB_API_BASE_URL}/{world_dir_path}'
    response = requests.get(url, headers=HEADERS)

    if response.status_code == 200:
        print(f"DEBUG: Listing contents of {world_dir_path}. Items found: {len(response.json())}")
        for item in response.json():
            # ★ここを修正: -metadata-.json ファイルを探し、ファイル名からワールド名とUUIDを正確に抽出
            if item['type'] == 'file' and item['name'].endswith('.json') and '-metadata-' in item['name']:
                filename_without_ext = item['name'].rsplit('.json', 1)[0]
                
                parts_by_metadata = filename_without_ext.split('-metadata-')
                
                if len(parts_by_metadata) == 2:
                    world_name_from_filename = parts_by_metadata[0]
                    uuid_part = parts_by_metadata[1]
                    
                    # UUID部分を最後のハイフンで分割してplayer_uuidとworld_uuidを取得
                    # UUIDは36文字の固定長なので、厳密にチェック
                    if len(uuid_part) >= 73 and uuid_part[36] == '-': # player_uuid (36) + '-' (1) + world_uuid (36)
                        player_uuid_in_filename = uuid_part[:36]
                        world_uuid_from_filename = uuid_part[37:]
                    else:
                        print(f"DEBUG: Invalid UUID format in filename (length/hyphen check): {item['name']}. Skipping.")
                        continue # 不正な形式の場合はスキップ

                    # ファイル名中のplayer_uuidが現在のプレイヤーと一致するか確認
                    if player_uuid_in_filename != player_uuid:
                        print(f"DEBUG: Skipping world '{item['name']}' as player UUID in filename ({player_uuid_in_filename}) does not match current user ({player_uuid}).")
                        continue

                    print(f"DEBUG: Loading metadata for world: {item['name']}")
                    metadata_content = get_github_file_content(f'{world_dir_path}/{item["name"]}')
                    if metadata_content:
                        worlds.append({
                            'world_name': metadata_content.get('world_name', world_name_from_filename),
                            'world_uuid': metadata_content.get('world_uuid', world_uuid_from_filename),
                            'player_uuid': metadata_content.get('player_uuid', player_uuid),
                            'seed': metadata_content.get('seed', 'N/A'),
                            'game_mode': metadata_content.get('game_mode', 'survival'),
                            'cheats_enabled': metadata_content.get('cheats_enabled', False)
                        })
                        print(f"DEBUG: Successfully added world: {metadata_content.get('world_name', 'N/A')}")
                    else:
                        print(f"DEBUG: Could not load metadata content for {item['name']}. Skipping.")
                else:
                    print(f"DEBUG: Filename format mismatch (no -metadata- separator): {item['name']}. Skipping.")
            else:
                print(f"DEBUG: Skipping non-metadata file or non-json: {item['name']}")
    elif response.status_code == 404:
        print(f"DEBUG: World directory '{world_dir_path}' not found on GitHub. Assuming no worlds for this player.")
    else:
        print(f"DEBUG: Failed to load world directory {world_dir_path}. Status: {response.status_code}, Response: {response.text}")
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
def index():
    print("indexページを表示しました")
    message = request.args.get('message')
    return render_template('index.html', message=message)
    

@app.route('/home')
def home():
    print("ホームページを表示しました")
    message = request.args.get('message')
    return render_template('home.html', message=message)
    

@app.route('/setting')
def setting():
    print("設定ページを表示しました")
    return render_template('setting.html')
    

@app.route('/store')
def store():
    print("ストアページを表示しました")
    return render_template('store.html')
    

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        players = load_all_player_data()
        
        for player in players:
            if player['username'] == username and player['password_hash'] == hashlib.sha256(password.encode()).hexdigest():
                session['username'] = username
                session['player_uuid'] = player['uuid']
                session.pop('is_offline_player', None) 
                flash(f"ようこそ、{username}さん！", "success")
                print(f"DEBUG: ユーザー '{username}' がログインしました。")
                return redirect(url_for('menu'))
        
        flash('ユーザー名またはパスワードが違います。', "error")
        print(f"DEBUG: ログイン失敗 - ユーザー名: {username}")
        return render_template('login.html')

    print("ログインページを表示しました")
    return render_template('login.html')
    

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('player_uuid', None)
    session.pop('is_offline_player', None)
    flash("ログアウトしました。", "info")
    print("DEBUG: ユーザーがログアウトしました。")
    return redirect(url_for('home'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        players = load_all_player_data()
        
        if any(p['username'] == username for p in players):
            flash('このユーザー名はすでに使用されています。', "error")
            print(f"DEBUG: 登録失敗 - ユーザー名 '{username}' は既に存在します。")
            return render_template('register.html')
        
        new_uuid = str(uuid.uuid4())
        hashed_password = hashlib.sha256(password.encode()).hexdigest()
        
        new_player = {
            'username': username,
            'password_hash': hashed_password,
            'uuid': new_uuid
        }
        
        print(f"DEBUG: 新規プレイヤーデータ: {new_player}")
        success, response = save_single_player_data(new_player)
        if success:
            flash('アカウントが正常に作成されました！ログインしてください。', "success")
            print(f"DEBUG: ユーザー '{username}' のアカウントが正常に作成されました。")
            return redirect(url_for('login'))
        else:
            flash('アカウント作成に失敗しました。GitHubのトークン権限、リポジトリ名、オーナー名を確認してください。', "error")
            print(f"DEBUG: ユーザー '{username}' のアカウント作成がGitHubへの保存失敗により失敗しました。")
            return render_template('register.html')
    print("アカウント生成ページを表示しました")
    return render_template('register.html')
    
@app.route('/offline')
def offline_play():
    if 'player_uuid' in session and session.get('is_offline_player'):
        flash("オフラインプレイヤーとしてログイン済みです。", "info")
        return redirect(url_for('menu'))

    random_digits = ''.join(random.choices(string.digits, k=5))
    temp_username = f"player{random_digits}"
    temp_uuid = str(uuid.uuid4())

    temp_player = {
        'username': temp_username,
        'password_hash': '',
        'uuid': temp_uuid,
        'is_offline_player': True
    }

    success, response = save_single_player_data(temp_player)
    if success:
        session['username'] = temp_username
        session['player_uuid'] = temp_uuid
        session['is_offline_player'] = True
        flash(f"オフラインプレイヤー '{temp_username}' としてログインしました！", "success")
        print(f"DEBUG: オフラインプレイヤー '{temp_username}' のアカウントがGitHubに作成されました。")
        return redirect(url_for('menu'))
    else:
        flash('オフラインプレイの準備に失敗しました。GitHubの設定を確認してください。', "error")
        print(f"ERROR: オフラインプレイヤーの作成がGitHubへの保存失敗により失敗しました。Response: {response}")
        return redirect(url_for('home'))

@app.route('/menu')
def menu():
    print("メニューページを表示しました")
    player_worlds = []
    if 'player_uuid' in session:
        player_uuid = session['player_uuid']
        player_worlds = load_world_data(player_uuid)
    
    return render_template('menu.html', worlds=player_worlds)
    

@app.route('/New-World', methods=['GET', 'POST'])
def new_world():
    if 'player_uuid' not in session:
        flash("ワールドを作成するにはログインしてください。", "warning")
        print("DEBUG: ワールド作成試行 - 未ログインユーザー。")
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
        
        print(f"DEBUG: 新規ワールドメタデータ: {world_metadata}")
        success = save_world_data(player_uuid, world_name, world_metadata)

        if success:
            flash(f'ワールド "{world_name}" が正常に作成されました！', "success")
            print(f"DEBUG: ワールド '{world_name}' が正常に作成されました。")
            return redirect(url_for('menu'))
        else:
            flash('ワールド作成に失敗しました。GitHubのトークン権限、リポジトリ名、オーナー名を確認してください。', "error")
            print(f"DEBUG: ワールド '{world_name}' の作成がGitHubへの保存失敗により失敗しました。")
            return render_template('new_world.html')

    print("ワールド生成ページを表示しました")
    return render_template('new_world.html')
    

@app.route('/World-setting', methods=['GET', 'POST'])
def world_setting():
    if 'player_uuid' not in session:
        flash("ワールド設定を変更するにはログインしてください。", "warning")
        print("DEBUG: ワールド設定試行 - 未ログインユーザー。")
        return redirect(url_for('login'))
    
    player_uuid = session['player_uuid']
    available_worlds = load_world_data(player_uuid)

    if request.method == 'POST':
        selected_world_name = request.form['selected_world']
        game_mode = request.form['game_mode']
        cheats_enabled = 'cheats_enabled' in request.form

        flash("ワールド設定の更新は現在サポートされていません。", "warning")
        print("DEBUG: ワールド設定の更新は現在サポートされていません。")
        return redirect(url_for('menu'))

    print("ワールド設定ページを表示しました")
    return render_template('world_setting.html', worlds=available_worlds)
    

@app.route('/import', methods=['GET', 'POST'])
def import_pack():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('ファイルが選択されていません。', "error")
            print("DEBUG: パックインポート失敗 - ファイルが選択されていません。")
            return render_template('import.html')
        file = request.files['file']
        
        if file.filename == '':
            flash('ファイルが選択されていません。', "error")
            print("DEBUG: パックインポート失敗 - ファイル名が空です。")
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
            print("DEBUG: パックインポート失敗 - 許可されていないファイル形式です。")
            return render_template('import.html')
    
    print("インポートページを表示しました")
    return render_template('import.html')
    

@app.route('/play/<world_name>/<world_uuid>')
def play_game(world_name, world_uuid):
    print(f"プレイページを表示しました: ワールド名={world_name}, ワールドUUID={world_uuid}")
    if 'player_uuid' not in session:
        flash("ゲームをプレイするにはログインしてください。", "warning")
        print("DEBUG: プレイ試行 - 未ログインユーザー。")
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
    print(f"DEBUG: ランチャースクリプト '{filename}' を生成しました。")
    return response

@app.route('/server') # 新しい /server エンドポイント
def server_page():
    print("サーバーページを表示しました")
    return render_template('server.html')


if __name__ == '__main__':
    # アプリケーション起動時にGitHub設定をチェック
    if not check_github_config():
        print("致命的なエラー: GitHub設定が正しくありません。アプリケーションを終了します。")
        exit(1)

    app.run(debug=True)
