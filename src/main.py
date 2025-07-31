import os
import sys
import tempfile
import subprocess
import json
from datetime import datetime, timedelta
import jwt
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# DON'T CHANGE THIS !!!
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flask import Flask, send_from_directory, request, jsonify, session
from flask_cors import CORS
from src.models.user import db, User
from src.routes.user import user_bp

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), 'static'))
app.config['SECRET_KEY'] = 'asdf#FGSgvasgf$5$WGT'
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')

# Configurar CORS
CORS(app, origins="*", supports_credentials=True)

# Criar diretório de uploads se não existir
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

app.register_blueprint(user_bp, url_prefix='/api')

# Configuração do banco de dados
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(os.path.dirname(__file__), 'database', 'app.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Usuários pré-definidos
PREDEFINED_USERS = [
    {
        'username': 'admin',
        'email': 'contato@ewertonleal.com.br',
        'password': '!342125377AsDfGhJkL'
    },
    {
        'username': 'user',
        'email': 'user@knscribe.com',
        'password': 'senha123'
    }
]

def init_database():
    """Inicializa o banco de dados com usuários pré-definidos"""
    with app.app_context():
        db.create_all()
        
        # Verificar se os usuários já existem
        for user_data in PREDEFINED_USERS:
            existing_user = User.query.filter_by(email=user_data['email']).first()
            if not existing_user:
                new_user = User(
                    username=user_data['username'],
                    email=user_data['email'],
                    password_hash=generate_password_hash(user_data['password'])
                )
                db.session.add(new_user)
        
        db.session.commit()

# Rotas de autenticação
@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        email_or_username = data.get('email_or_username')
        password = data.get('password')
        
        if not email_or_username or not password:
            return jsonify({'error': 'Email/usuário e senha são obrigatórios'}), 400
        
        # Buscar usuário por email ou username
        user = User.query.filter(
            (User.email == email_or_username) | (User.username == email_or_username)
        ).first()
        
        if user and check_password_hash(user.password_hash, password):
            # Gerar token JWT
            token = jwt.encode({
                'user_id': user.id,
                'username': user.username,
                'exp': datetime.utcnow() + timedelta(hours=24)
            }, app.config['SECRET_KEY'], algorithm='HS256')
            
            return jsonify({
                'success': True,
                'token': token,
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email
                }
            })
        else:
            return jsonify({'error': 'Credenciais inválidas'}), 401
            
    except Exception as e:
        return jsonify({'error': f'Erro interno: {str(e)}'}), 500

@app.route('/api/auth/verify', methods=['GET'])
def verify_token():
    try:
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Token não fornecido'}), 401
        
        if token.startswith('Bearer '):
            token = token[7:]
        
        data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        user = User.query.get(data['user_id'])
        
        if user:
            return jsonify({
                'success': True,
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email
                }
            })
        else:
            return jsonify({'error': 'Usuário não encontrado'}), 404
            
    except jwt.ExpiredSignatureError:
        return jsonify({'error': 'Token expirado'}), 401
    except jwt.InvalidTokenError:
        return jsonify({'error': 'Token inválido'}), 401
    except Exception as e:
        return jsonify({'error': f'Erro interno: {str(e)}'}), 500

# Rotas de transcrição
@app.route('/api/transcribe', methods=['POST'])
def transcribe_audio():
    try:
        # Verificar token
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Token não fornecido'}), 401
        
        if token.startswith('Bearer '):
            token = token[7:]
        
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            user = User.query.get(data['user_id'])
            if not user:
                return jsonify({'error': 'Usuário não encontrado'}), 404
        except:
            return jsonify({'error': 'Token inválido'}), 401
        
        # Verificar se há arquivo
        if 'audio' not in request.files:
            return jsonify({'error': 'Nenhum arquivo de áudio fornecido'}), 400
        
        file = request.files['audio']
        if file.filename == '':
            return jsonify({'error': 'Nenhum arquivo selecionado'}), 400
        
        # Salvar arquivo temporariamente
        filename = secure_filename(file.filename)
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(temp_path)
        
        try:
            # Usar OpenAI Whisper para transcrição
            result = subprocess.run([
                'whisper', temp_path, '--model', 'base', '--language', 'pt', '--output_format', 'json'
            ], capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                # Ler o arquivo JSON gerado
                json_file = temp_path.replace(os.path.splitext(temp_path)[1], '.json')
                if os.path.exists(json_file):
                    with open(json_file, 'r', encoding='utf-8') as f:
                        transcription_data = json.load(f)
                    
                    transcription_text = transcription_data.get('text', '')
                    
                    # Limpar arquivos temporários
                    os.remove(temp_path)
                    os.remove(json_file)
                    
                    return jsonify({
                        'success': True,
                        'transcription': transcription_text,
                        'timestamp': datetime.now().isoformat()
                    })
                else:
                    return jsonify({'error': 'Arquivo de transcrição não encontrado'}), 500
            else:
                return jsonify({'error': f'Erro na transcrição: {result.stderr}'}), 500
                
        except subprocess.TimeoutExpired:
            return jsonify({'error': 'Timeout na transcrição'}), 500
        except Exception as e:
            return jsonify({'error': f'Erro na transcrição: {str(e)}'}), 500
        finally:
            # Limpar arquivo temporário se ainda existir
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    except Exception as e:
        return jsonify({'error': f'Erro interno: {str(e)}'}), 500

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    static_folder_path = app.static_folder
    if static_folder_path is None:
        return "Static folder not configured", 404

    if path != "" and os.path.exists(os.path.join(static_folder_path, path)):
        return send_from_directory(static_folder_path, path)
    else:
        index_path = os.path.join(static_folder_path, 'index.html')
        if os.path.exists(index_path):
            return send_from_directory(static_folder_path, 'index.html')
        else:
            return "index.html not found", 404

if __name__ == '__main__':
    init_database()
    app.run(host='0.0.0.0', port=5000, debug=True)

