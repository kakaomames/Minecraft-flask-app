from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, stream_with_context, jsonify
import hashlib
import json
import os
import uuid
import requests
import base64
from dotenv import load_dotenv
import random
import string
from werkzeug.utils import secure_filename
import zipfile
import tempfile
import shutil
import traceback
import subprocess
import threading
import time

app = Flask(__name__)

# .envファイルをロード
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY') # SECRET_KEYを環境変数から読み込む

# --- GitHub API 設定 ---
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_OWNER = os.getenv('GITHUB_OWNER')
GITHUB_REPO = os.getenv('GITHUB_REPO')

# GitHub設定とシークレットキーを起動時にチェックする関数
def check_config():
    print("\n--- アプリケーション設定の初期チェックを開始します ---")

    config_ok = True

    if not GITHUB_TOKEN:
        print("エラー: GITHUB_TOKEN が .env ファイルに設定されていません。")
        print("GitHub Personal Access Tokenを生成し、.envファイルに 'GITHUB_TOKEN=\"YOUR_TOKEN_HERE\"' の形式で設定してください。")
        config_ok = False
    if not GITHUB_OWNER or not GITHUB_REPO:
        print("エラー: GITHUB_OWNER または GITHUB_REPO が .env ファイルに設定されていません。")
        print(".envファイルに 'GITHUB_OWNER=\"あなたのGitHubユーザー名\"' と 'GITHUB_REPO=\"あなたのリポジトリ名\"' を設定してください。")
        config_ok = False
    
    if not app.secret_key:
        print("エラー: SECRET_KEY が .env ファイルに設定されていません。")
        print("セッションの永続化のために、.envファイルに 'SECRET_KEY=\"あなたの非常に長いランダムな秘密鍵\"' を設定してください。")
        print("例: SECRET_KEY=\"supersecretkeythatisverylongandrandomandhardtoguessthisisforproductionuse\"")
        config_ok = False

    if not config_ok:
        print("--- アプリケーション設定の初期チェックを完了しました (エラーあり) ---\n")
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

        if response.status_code == 200 or response.status_code == 404:
            print("成功: GitHub APIへのアクセスが確認できました。トークンとリポジトリ設定は有効です。")
            print("--- アプリケーション設定の初期チェックを完了しました ---\n")
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

def upload_directory_to_github(local_dir_path, github_base_path, commit_message):
    success_count = 0
    fail_count = 0
    
    print(f"DEBUG: Starting directory upload from '{local_dir_path}' to GitHub path '{github_base_path}'")
    for root, _, files in os.walk(local_dir_path):
        for file_name in files:
            local_file_path = os.path.join(root, file_name)
            relative_path = os.path.relpath(local_file_path, local_dir_path)
            github_path = os.path.join(github_base_path, relative_path).replace(os.sep, '/')

            # GitHubのファイルサイズ制限（1MB）を考慮して、大きすぎるファイルはスキップ
            if os.path.getsize(local_file_path) > 1024 * 1024: # 1MB
                print(f"WARNING: Skipping large file (>{1}MB): {local_file_path}. GitHub API has a 1MB file size limit for direct content uploads.")
                continue

            try:
                with open(local_file_path, 'rb') as f:
                    file_content_bytes = f.read()
                
                existing_file_info = get_github_file_info(github_path)
                sha = existing_file_info['sha'] if existing_file_info else None
                
                file_success, file_response = put_github_file_content(
                    github_path,
                    file_content_bytes,
                    f"{commit_message}: {relative_path}",
                    sha
                )
                if file_success:
                    success_count += 1
                else:
                    fail_count += 1
                    print(f"ERROR: Failed to upload/update {github_path}. Response: {file_response}")

            except Exception as e:
                fail_count += 1
                print(f"ERROR: Error processing local file {local_file_path} for upload: {e}")
    
    print(f"INFO: Directory upload finished. Success: {success_count}, Failed: {fail_count}")
    return fail_count == 0

# --- プレイヤーデータ管理のリファクタリング ---
PLAYERS_DIR_PATH = 'players'

def load_all_player_data():
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

# --- パックレジストリ管理 ---
PACK_REGISTRY_PATH = 'pack_registry.json'
PACKS_EXTRACTED_BASE_PATH = 'packs_extracted'

def load_pack_registry():
    registry = get_github_file_content(PACK_REGISTRY_PATH)
    return registry if registry is not None else []

def save_pack_registry(registry_data):
    path = PACK_REGISTRY_PATH
    current_file_info = get_github_file_info(path)
    sha = current_file_info['sha'] if current_file_info else None
    
    message = 'Update pack registry'
    success, response = put_github_file_content(path, registry_data, message, sha)
    if not success:
        print(f"ERROR: save_pack_registry failed for {path}. Response: {response}")
    return success, response

def parse_mc_pack(pack_file_path):
    pack_info = None
    temp_dir = None
    print(f"DEBUG: Starting parse_mc_pack for: {pack_file_path}")
    try:
        temp_dir = tempfile.mkdtemp()
        print(f"DEBUG: Created temporary extraction directory: {temp_dir}")
        
        if not zipfile.is_zipfile(pack_file_path):
            print(f"ERROR: File is not a valid ZIP file: {pack_file_path}")
            return None, None

        with zipfile.ZipFile(pack_file_path, 'r') as zip_ref:
            print(f"DEBUG: Contents of zip file {pack_file_path}:")
            zip_contents = zip_ref.namelist()
            for name in zip_contents:
                print(f"  - {name}")

            manifest_in_zip_path = None
            for name in zip_contents:
                if name.endswith('manifest.json') and 'manifest.json' in name:
                    manifest_in_zip_path = name
                    break
            
            if manifest_in_zip_path:
                print(f"DEBUG: Found manifest.json inside zip at: {manifest_in_zip_path}")
                with zip_ref.open(manifest_in_zip_path) as manifest_file:
                    manifest = json.load(manifest_file)
                
                print(f"DEBUG: manifest.json found and loaded. Content: {json.dumps(manifest, indent=2)}")
                
                header = manifest.get('header', {})
                modules = manifest.get('modules', [])

                pack_id = header.get('uuid')
                pack_name = header.get('name')
                pack_version = header.get('version')
                pack_type = "unknown"

                for module in modules:
                    if module.get('type') == 'resources':
                        pack_type = 'resource'
                        break
                    elif module.get('type') == 'data':
                        pack_type = 'behavior'
                        break
                    elif module.get('type') == 'script':
                        pack_type = 'behavior'
                        break
                    elif module.get('type') == 'client_data':
                        pack_type = 'resource'
                        break
                    elif module.get('type') == 'skin_pack':
                        pack_type = 'skin'
                        break
                
                if pack_id and pack_name and pack_version:
                    sanitized_pack_name = secure_filename(pack_name)
                    pack_info = {
                        'id': pack_id,
                        'name': pack_name,
                        'version': pack_version,
                        'type': pack_type,
                        'filename': os.path.basename(pack_file_path),
                        'sanitized_name': sanitized_pack_name,
                        'extracted_path': f'{PACKS_EXTRACTED_BASE_PATH}/{pack_type}/{sanitized_pack_name}'
                    }
                    print(f"DEBUG: Parsed pack info successfully: {pack_info}")

                    zip_ref.extractall(temp_dir)
                    print(f"DEBUG: Full pack extracted to: {temp_dir}")

                else:
                    print(f"WARNING: manifest.json missing essential header info (uuid, name, or version): {manifest_in_zip_path}")
            else:
                print(f"WARNING: manifest.json not found anywhere in pack: {pack_file_path}")
                
    except zipfile.BadZipFile:
        print(f"ERROR: Not a valid zip file (BadZipFile): {pack_file_path}")
        traceback.print_exc()
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid manifest.json format in {pack_file_path}: {e}")
        traceback.print_exc()
    except Exception as e:
        print(f"ERROR: Error processing pack {pack_file_path}: {e}")
        traceback.print_exc()
    finally:
        pass 
    return pack_info, temp_dir

def list_available_packs():
    registry = load_pack_registry()
    print(f"DEBUG: Loaded pack registry: {registry}")
    return registry

def load_world_data(player_uuid):
    worlds = []
    world_dir_path = f'worlds/{player_uuid}'
    url = f'{GITHUB_API_BASE_URL}/{world_dir_path}'
    response = requests.get(url, headers=HEADERS)

    print(f"DEBUG: Attempting to list world directory: {world_dir_path}. Status: {response.status_code}")
    if response.status_code == 200:
        github_items = response.json()
        print(f"DEBUG: Found {len(github_items)} items in {world_dir_path} on GitHub.")

        for item in github_items:
            print(f"DEBUG: Processing item: {item['name']} (Type: {item['type']})")
            if item['type'] == 'file' and item['name'].endswith('.json') and '-metadata-' in item['name']:
                filename_without_ext = item['name'].rsplit('.json', 1)[0]
                
                parts_by_metadata = filename_without_ext.split('-metadata-')
                
                if len(parts_by_metadata) == 2:
                    world_name_from_filename = parts_by_metadata[0]
                    uuid_part = parts_by_metadata[1]
                    
                    if len(uuid_part) == 73 and uuid_part[36] == '-':
                        player_uuid_in_filename = uuid_part[:36]
                        world_uuid_from_filename = uuid_part[37:]
                    else:
                        print(f"DEBUG: Invalid UUID format in filename (length/hyphen check): '{item['name']}'. UUID part: '{uuid_part}'. Skipping.")
                        continue

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
                            'cheats_enabled': metadata_content.get('cheats_enabled', False),
                            'resource_packs': metadata_content.get('resource_packs', []),
                            'behavior_packs': metadata_content.get('behavior_packs', [])
                        })
                        print(f"DEBUG: Successfully added world: {metadata_content.get('world_name', 'N/A')} (UUID: {metadata_content.get('world_uuid', 'N/A')})")
                    else:
                        print(f"DEBUG: Could not load metadata content for {item['name']}. Skipping.")
                else:
                    print(f"DEBUG: Filename format mismatch (no -metadata- separator): '{item['name']}'. Skipping.")
            else:
                print(f"DEBUG: Skipping non-metadata file or non-json: '{item['name']}'.")
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



# Pygletゲームプロセスの管理
game_process = None
game_output_buffer = []
game_output_lock = threading.Lock()

# Pygletゲームの出力をリアルタイムでキャプチャするスレッド
def capture_game_output(pipe):
    global game_output_buffer
    for line in iter(pipe.readline, b''):
        with game_output_lock:
            game_output_buffer.append(line.decode('utf-8'))
    pipe.close()

# GitHubからmanifest.jsonをダウンロードする関数
def get_manifest_from_github(repo_path):
    if not GITHUB_TOKEN or not GITHUB_OWNER or not GITHUB_REPO:
        print("GitHub認証情報が設定されていません。manifest.jsonをダウンロードできません。")
        return None

    url = f'https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{repo_path}/manifest.json'
    headers = {
        'Authorization': f'token {GITHUB_TOKEN}',
        'Accept': 'application/vnd.github.com.v3.raw', # 生のファイルコンテンツを取得
        'User-Agent': 'Flask-Minecraft-Server'
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status() # HTTPエラーがあれば例外を発生させる
        return json.loads(response.text)
    except requests.exceptions.RequestException as e:
        print(f"manifest.jsonのダウンロード中にエラーが発生しました: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"manifest.jsonのデコード中にエラーが発生しました: {e}")
        return None






# --- Flask ルーティング ---

@app.route('/')
def index():
    print("indexページを表示しました")
    message = request.args.get('message')
    return render_template('index.html', message=message)
@app.route('/a')
def index():
    # 利用可能なパックのリストを取得 (例として固定値を返す)
    # 実際にはGitHub APIを叩いてリポジトリ内のパックを列挙するロジックが必要
    available_packs = [
        {'name': 'Vanilla Server Pack', 'path': 'resource_packs/vanilla_server', 'type': 'resource'},
        {'name': 'My Custom Behavior Pack', 'path': 'behavior_packs/my_custom_pack', 'type': 'behavior'},
        # ... 他のパック
    ]
    
    # 各パックのmanifest.jsonから詳細情報を取得
    for pack in available_packs:
        manifest = get_manifest_from_github(pack['path'])
        if manifest:
            pack['description'] = manifest['header'].get('description', 'No description')
            pack['version'] = '.'.join(map(str, manifest['header'].get('version', [0, 0, 0])))
        else:
            pack['description'] = 'Failed to load manifest.'
            pack['version'] = 'N/A'

    return render_template('indexs.html', available_packs=available_packs)
    
@app.route('/launch_game', methods=['POST'])
def launch_game():
    global game_process

    if game_process and game_process.poll() is None:
        return jsonify({'status': 'error', 'message': 'ゲームはすでに実行中です。'}), 409

    data = request.get_json()
    world_name = data.get('worldName', 'Default World')
    resource_pack_paths = data.get('resourcePacks', [])
    behavior_pack_paths = data.get('behaviorPacks', [])
    world_seed = data.get('worldSeed', '') # ★追加: ワールドシードを取得

    # 環境変数を設定
    env = os.environ.copy()
    env['WORLD_NAME'] = world_name
    env['PLAYER_UUID'] = 'player-123' # 仮のUUID
    env['WORLD_UUID'] = 'world-456' # 仮のUUID
    env['RESOURCE_PACK_PATHS'] = ','.join(resource_pack_paths)
    env['BEHAVIOR_PACKS_PATHS'] = ','.join(behavior_pack_paths)
    env['GITHUB_TOKEN'] = GITHUB_TOKEN # game.pyにGitHubトークンを渡す
    env['GITHUB_OWNER'] = GITHUB_OWNER
    env['GITHUB_REPO'] = GITHUB_REPO
    env['WORLD_SEED'] = world_seed # ★追加: ワールドシードを環境変数として渡す

    command = ['python', 'game.py']
    
    try:
        # Popenでゲームを非同期で起動
        game_process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, # エラーもstdoutにリダイレクト
            env=env
        )
        print(f"ゲームプロセスを起動しました: PID {game_process.pid}")

        # ゲームの出力をキャプチャするスレッドを起動
        global game_output_buffer
        game_output_buffer = [] # バッファをクリア
        threading.Thread(target=capture_game_output, args=(game_process.stdout,), daemon=True).start()

        return jsonify({'status': 'success', 'message': 'ゲームを起動しました。'})
    except Exception as e:
        print(f"ゲームの起動中にエラーが発生しました: {e}")
        return jsonify({'status': 'error', 'message': f'ゲームの起動に失敗しました: {e}'}), 500
@app.route('/game_output')
def game_output():
    def generate():
        last_index = 0
        while True:
            with game_output_lock:
                if len(game_output_buffer) > last_index:
                    for i in range(last_index, len(game_output_buffer)):
                        yield game_output_buffer[i]
                    last_index = len(game_output_buffer)
            # ゲームプロセスが終了しているかチェック
            if game_process and game_process.poll() is not None:
                print("ゲームプロセスが終了しました。出力を停止します。")
                break
            time.sleep(0.1) # ポーリング間隔

    return Response(stream_with_context(generate()), mimetype='text/plain')

@app.route('/stop_game', methods=['POST'])
def stop_game():
    global game_process
    if game_process and game_process.poll() is None:
        print(f"ゲームプロセスを終了します: PID {game_process.pid}")
        game_process.terminate() # プロセスを終了
        game_process.wait() # 終了を待つ
        game_process = None
        return jsonify({'status': 'success', 'message': 'ゲームを停止しました。'})
    else:
        return jsonify({'status': 'info', 'message': 'ゲームは実行されていません。'}), 200
        
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

    try:
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
    except Exception as e:
        flash(f'オフラインプレイの準備中に予期せぬエラーが発生しました: {e}', "error")
        print(f"CRITICAL ERROR: Unhandled exception in offline_play: {e}")
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
    
    available_packs = list_available_packs()

    if request.method == 'POST':
        world_name = request.form['world_name']
        seed = request.form['seed']
        game_mode = request.form['game_mode']
        cheats_enabled = 'cheats_enabled' in request.form
        resource_packs = request.form.getlist('resource_packs')
        behavior_packs = request.form.getlist('behavior_packs')


        player_uuid = session['player_uuid']
        new_world_uuid = str(uuid.uuid4())

        world_metadata = {
            'player_uuid': player_uuid,
            'world_name': world_name,
            'world_uuid': new_world_uuid,
            'seed': seed,
            'game_mode': game_mode,
            'cheats_enabled': cheats_enabled,
            'resource_packs': resource_packs,
            'behavior_packs': behavior_packs
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
            return render_template('new_world.html', available_packs=available_packs)

    print("ワールド生成ページを表示しました")
    return render_template('new_world.html', available_packs=available_packs)
    

@app.route('/World-setting/<world_name>/<world_uuid>', methods=['GET', 'POST'])
def world_setting(world_name, world_uuid):
    if 'player_uuid' not in session:
        flash("ワールド設定を変更するにはログインしてください。", "warning")
        return redirect(url_for('login'))
    
    player_uuid = session['player_uuid']
    
    world_metadata_filename = f'{world_name}-metadata-{player_uuid}-{world_uuid}.json'
    world_metadata_path = f'worlds/{player_uuid}/{world_metadata_filename}'
    
    world_data = get_github_file_content(world_metadata_path)

    if not world_data:
        flash(f"ワールド '{world_name}' ({world_uuid}) の設定が見つかりませんでした。", "error")
        print(f"ERROR: World metadata not found for {world_metadata_path}")
        return redirect(url_for('menu'))

    available_packs = list_available_packs()

    if request.method == 'POST':
        updated_game_mode = request.form['game_mode']
        updated_cheats_enabled = 'cheats_enabled' in request.form
        updated_resource_packs = request.form.getlist('resource_packs')
        updated_behavior_packs = request.form.getlist('behavior_packs')

        world_data['game_mode'] = updated_game_mode
        world_data['cheats_enabled'] = updated_cheats_enabled
        world_data['resource_packs'] = updated_resource_packs
        world_data['behavior_packs'] = updated_behavior_packs
        
        success = save_world_data(player_uuid, world_name, world_data)

        if success:
            flash(f'ワールド "{world_name}" の設定が更新されました！', "success")
            print(f"DEBUG: ワールド '{world_name}' ({world_uuid}) の設定が正常に更新されました。")
            return redirect(url_for('menu'))
        else:
            flash('ワールド設定の更新に失敗しました。GitHubの設定を確認してください。', "error")
            print(f"ERROR: ワールド '{world_name}' ({world_uuid}) の設定更新がGitHubへの保存失敗により失敗しました。")
            return render_template('world_setting.html', world=world_data, available_packs=available_packs)

    print(f"ワールド設定ページを表示しました: ワールド名={world_name}, ワールドUUID={world_uuid}")
    return render_template('world_setting.html', world=world_data, available_packs=available_packs)
    

@app.route('/import', methods=['GET', 'POST'])
def import_pack():
    if request.method == 'POST':
        print("DEBUG: Pack import POST request received.")
        if 'file' not in request.files:
            flash('ファイルが選択されていません。', "error")
            print("DEBUG: パックインポート失敗 - ファイルが選択されていません。")
            return render_template('import.html')
        file = request.files['file']
        
        if file.filename == '':
            flash('ファイルが選択されていません。', "error")
            print("DEBUG: パックインポート失敗 - ファイル名が空です。")
            return render_template('import.html')
        
        if not allowed_file(file.filename):
            flash('許可されていないファイル形式です。(.mcpackまたは.mcaddonのみ)', "error")
            print("DEBUG: パックインポート失敗 - 許可されていないファイル形式です。")
            return render_template('import.html')
        
        temp_file_path = None
        temp_extract_dir = None

        try:
            temp_dir_for_file = tempfile.mkdtemp()
            temp_file_path = os.path.join(temp_dir_for_file, secure_filename(file.filename))
            file.save(temp_file_path)
            print(f"DEBUG: Uploaded pack saved temporarily to: {temp_file_path}")

            if not os.path.exists(temp_file_path):
                raise FileNotFoundError(f"Temporary pack file not found after saving: {temp_file_path}")

            pack_metadata, temp_extract_dir = parse_mc_pack(temp_file_path)
            
            if pack_metadata and temp_extract_dir:
                github_extracted_pack_path = pack_metadata['extracted_path']
                print(f"DEBUG: Pack metadata parsed. ID: {pack_metadata['id']}, Extracted Dir: {temp_extract_dir}, GitHub Target Path: {github_extracted_pack_path}")

                print(f"DEBUG: Attempting to upload extracted pack contents from {temp_extract_dir} to GitHub path {github_extracted_pack_path}...")
                upload_success = upload_directory_to_github(
                    temp_extract_dir,
                    github_extracted_pack_path,
                    f"Upload extracted pack: {pack_metadata['name']} ({pack_metadata['id']})"
                )

                if not upload_success:
                    flash(f'パック "{pack_metadata["name"]}" のコンテンツのGitHubへのアップロードに失敗しました。', "error")
                    print(f"ERROR: Failed to upload extracted pack contents for {pack_metadata['name']}.")
                    return render_template('import.html')
                print(f"DEBUG: Extracted pack contents uploaded to GitHub successfully.")

                pack_registry = load_pack_registry()
                
                existing_pack_index = next((i for i, p in enumerate(pack_registry) if p.get('id') == pack_metadata['id']), -1)
                
                if existing_pack_index != -1:
                    pack_registry[existing_pack_index] = pack_metadata
                    print(f"DEBUG: Updated existing pack in registry: {pack_metadata['name']}")
                else:
                    pack_registry.append(pack_metadata)
                    print(f"DEBUG: Added new pack to registry: {pack_metadata['name']}")
                
                print(f"DEBUG: Attempting to save pack registry to GitHub.")
                success, response = save_pack_registry(pack_registry)

                if success:
                    flash(f'パック "{pack_metadata["name"]}" が正常にインポートされました！', "success")
                    print(f"DEBUG: Pack '{pack_metadata['name']}' metadata saved to GitHub successfully.")
                    return redirect(url_for('home'))
                else:
                    error_message = response.get('message', 'Unknown error')
                    print(f"Failed to save pack metadata to GitHub: {error_message}")
                    flash(f'パック "{pack_metadata["name"]}" のメタデータのGitHubへの保存に失敗しました: {error_message}', "error")
                    return render_template('import.html')
            else:
                flash('パックの解析に失敗しました。有効なMinecraftパックファイルか確認してください。', "error")
                print(f"ERROR: Failed to parse pack file: {file.filename}. pack_metadata: {pack_metadata}, temp_extract_dir: {temp_extract_dir}")
                return render_template('import.html')

        except Exception as e:
            flash(f'ファイルの処理中にエラーが発生しました: {e}', "error")
            print(f"ERROR: Error during pack import process: {e}")
            traceback.print_exc()
            return render_template('import.html')
        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                os.remove(temp_file_path)
                print(f"DEBUG: Cleaned up temporary pack file: {temp_file_path}")
            if temp_extract_dir and os.path.exists(temp_extract_dir):
                shutil.rmtree(temp_extract_dir)
                print(f"DEBUG: Cleaned up temporary extraction directory: {temp_extract_dir}")
            if temp_dir_for_file and os.path.exists(temp_dir_for_file):
                shutil.rmtree(temp_dir_for_file)
                print(f"DEBUG: Cleaned up temporary file directory: {temp_dir_for_file}")
    
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

    world_metadata_filename = f'{world_name}-metadata-{player_uuid}-{world_uuid}.json'
    world_metadata_path = f'worlds/{player_uuid}/{world_metadata_filename}'
    world_data = get_github_file_content(world_metadata_path)

    resource_packs_paths_str = ""
    behavior_packs_paths_str = ""

    if world_data:
        selected_resource_pack_filenames = world_data.get('resource_packs', [])
        selected_behavior_pack_filenames = world_data.get('behavior_packs', [])
        
        all_available_packs = load_pack_registry()
        
        resource_pack_paths = []
        for filename in selected_resource_pack_filenames:
            pack_info = next((p for p in all_available_packs if p.get('filename') == filename), None)
            if pack_info and pack_info.get('extracted_path'):
                resource_pack_paths.append(pack_info['extracted_path'])
            else:
                print(f"WARNING: Resource pack '{filename}' not found in registry or missing extracted_path.")
        
        behavior_pack_paths = []
        for filename in selected_behavior_pack_filenames:
            pack_info = next((p for p in all_available_packs if p.get('filename') == filename), None)
            if pack_info and pack_info.get('extracted_path'):
                behavior_pack_paths.append(pack_info['extracted_path'])
            else:
                print(f"WARNING: Behavior pack '{filename}' not found in registry or missing extracted_path.")

        resource_packs_paths_str = ",".join(resource_pack_paths)
        behavior_packs_paths_str = ",".join(behavior_pack_paths)
        
        print(f"DEBUG: 選択されたリソースパック展開パス: {resource_packs_paths_str}")
        print(f"DEBUG: 選択されたビヘイビアパック展開パス: {behavior_packs_paths_str}")
    else:
        print(f"WARNING: ワールド '{world_name}' のメタデータが見つかりませんでした。パック情報は渡されません。")


    user_agent = request.headers.get('User-Agent', '').lower()
    # ★追加: GitHub認証情報を環境変数として渡す
    github_token_env = f"GITHUB_TOKEN={GITHUB_TOKEN}"
    github_owner_env = f"GITHUB_OWNER={GITHUB_OWNER}"
    github_repo_env = f"GITHUB_REPO={GITHUB_REPO}"

    if 'windows' in user_agent:
        script_content = f"""@echo off
SET WORLD_NAME={world_name}
SET PLAYER_UUID={player_uuid}
SET WORLD_UUID={world_uuid}
SET RESOURCE_PACK_PATHS={resource_packs_paths_str}
SET BEHAVIOR_PACK_PATHS={behavior_pack_paths_str}
SET {github_token_env}
SET {github_owner_env}
SET {github_repo_env}
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
export RESOURCE_PACK_PATHS="{resource_packs_paths_str}"
export BEHAVIOR_PACK_PATHS="{behavior_pack_paths_str}"
export {github_token_env}
export {github_owner_env}
export {github_repo_env}
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

@app.route('/server')
def server_page():
    print("サーバーページを表示しました")
    return render_template('server.html')


if __name__ == '__main__':
    # Flaskアプリを起動
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False) # use_reloader=False でPygletが二重起動するのを防ぐ

