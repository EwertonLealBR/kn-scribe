import os
import tempfile
import whisper
import jwt
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import subprocess
import time

# Configuração da aplicação
app = Flask(__name__, static_folder='static', static_url_path='')
app.config['SECRET_KEY'] = 'kn-scribe-secret-key-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/kn_scribe.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size

# Configurar CORS
CORS(app, origins="*")

# Inicializar banco de dados
db = SQLAlchemy(app)

# Modelos
class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class Transcription(db.Model):
    __tablename__ = 'transcriptions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(50), nullable=False)  # audio, video
    file_format = db.Column(db.String(10), nullable=False)  # mp3, wav, ogg, mp4, etc
    file_size = db.Column(db.Integer)  # em bytes
    duration = db.Column(db.Float)  # em segundos
    transcription_text = db.Column(db.Text, nullable=False)
    language = db.Column(db.String(10), default='pt')
    confidence_score = db.Column(db.Float)
    processing_time = db.Column(db.Float)  # tempo de processamento em segundos
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relacionamento com usuário
    user = db.relationship('User', backref=db.backref('transcriptions', lazy=True))
    
    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.original_filename,
            'file_type': self.file_type,
            'file_format': self.file_format,
            'file_size': self.file_size,
            'duration': self.get_formatted_duration(),
            'transcription': self.transcription_text,
            'language': self.language,
            'confidence_score': self.confidence_score,
            'processing_time': self.processing_time,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def get_formatted_duration(self):
        """Retorna a duração formatada em MM:SS"""
        if not self.duration:
            return "N/A"
        
        minutes = int(self.duration // 60)
        seconds = int(self.duration % 60)
        return f"{minutes:02d}:{seconds:02d}"

# Usuários pré-definidos
PREDEFINED_USERS = [
    {
        'username': 'admin',
        'email': 'contato@ewertonleal.com.br',
        'password': '!342125377AsDfGhJkL'
    },
    {
        'username': 'user',
        'email': 'admin@kndigital.com.br',
        'password': 'admin123'
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

# Inicializar banco de dados
init_database()

# Carregar modelo Whisper
print("Carregando modelo Whisper...")
model = whisper.load_model("base")
print("Modelo Whisper carregado com sucesso!")

# Formatos suportados
ALLOWED_AUDIO_EXTENSIONS = {'mp3', 'wav', 'm4a', 'flac', 'ogg', 'aac', 'wma'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'wmv', 'flv', 'webm'}
ALL_ALLOWED_EXTENSIONS = ALLOWED_AUDIO_EXTENSIONS | ALLOWED_VIDEO_EXTENSIONS

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALL_ALLOWED_EXTENSIONS

def get_file_type(filename):
    ext = filename.rsplit('.', 1)[1].lower()
    if ext in ALLOWED_AUDIO_EXTENSIONS:
        return 'audio'
    elif ext in ALLOWED_VIDEO_EXTENSIONS:
        return 'video'
    return 'unknown'

def extract_audio_from_video(video_path, output_path):
    """Extrai áudio de um arquivo de vídeo usando ffmpeg"""
    try:
        cmd = [
            'ffmpeg', '-i', video_path,
            '-vn', '-acodec', 'pcm_s16le',
            '-ar', '16000', '-ac', '1',
            output_path, '-y'
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Erro ao extrair áudio: {e}")
        return False

def get_audio_duration(file_path):
    """Obtém a duração do arquivo de áudio usando ffmpeg"""
    try:
        cmd = [
            'ffprobe', '-v', 'quiet', '-show_entries',
            'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1',
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return float(result.stdout.strip())
    except:
        return None

# Função para gerar token JWT
def generate_token(user_id):
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(hours=24)
    }
    return jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')

# Função para verificar token JWT
def verify_token(token):
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        return payload['user_id']
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

# Rotas de autenticação
@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        email_or_username = data.get('email_or_username')
        password = data.get('password')
        
        if not email_or_username or not password:
            return jsonify({'success': False, 'message': 'Email/usuário e senha são obrigatórios'}), 400
        
        # Buscar usuário por email ou username
        user = User.query.filter(
            (User.email == email_or_username) | (User.username == email_or_username)
        ).first()
        
        if not user or not user.check_password(password):
            return jsonify({'success': False, 'message': 'Credenciais inválidas'}), 401
        
        # Gerar token
        token = generate_token(user.id)
        
        return jsonify({
            'success': True,
            'token': token,
            'user': user.to_dict()
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro interno: {str(e)}'}), 500

@app.route('/api/verify-token', methods=['GET'])
def verify_token_route():
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'message': 'Token não fornecido'}), 401
        
        token = auth_header.split(' ')[1]
        user_id = verify_token(token)
        
        if not user_id:
            return jsonify({'success': False, 'message': 'Token inválido'}), 401
        
        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'message': 'Usuário não encontrado'}), 404
        
        return jsonify({
            'success': True,
            'user': user.to_dict()
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro interno: {str(e)}'}), 500

# Rota de transcrição
@app.route('/api/transcribe', methods=['POST'])
def transcribe():
    try:
        # Verificar autenticação
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'message': 'Token não fornecido'}), 401
        
        token = auth_header.split(' ')[1]
        user_id = verify_token(token)
        
        if not user_id:
            return jsonify({'success': False, 'message': 'Token inválido'}), 401
        
        # Verificar se há arquivo
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': 'Nenhum arquivo enviado'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': 'Nenhum arquivo selecionado'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'success': False, 'message': 'Formato de arquivo não suportado'}), 400
        
        # Salvar arquivo temporário
        filename = secure_filename(file.filename)
        file_extension = filename.rsplit('.', 1)[1].lower()
        file_type = get_file_type(filename)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_extension}') as temp_file:
            file.save(temp_file.name)
            temp_path = temp_file.name
            file_size = os.path.getsize(temp_path)
        
        try:
            start_time = time.time()
            
            # Se for vídeo, extrair áudio primeiro
            if file_type == 'video':
                audio_temp_path = tempfile.mktemp(suffix='.wav')
                if not extract_audio_from_video(temp_path, audio_temp_path):
                    return jsonify({'success': False, 'message': 'Erro ao extrair áudio do vídeo'}), 500
                
                # Usar o arquivo de áudio extraído
                os.unlink(temp_path)
                temp_path = audio_temp_path
            
            # Obter duração do áudio
            duration = get_audio_duration(temp_path)
            
            # Realizar transcrição
            result = model.transcribe(temp_path, language='pt')
            transcription_text = result['text'].strip()
            
            processing_time = time.time() - start_time
            
            # Salvar no banco de dados
            transcription = Transcription(
                user_id=user_id,
                filename=f"transcription_{int(time.time())}.{file_extension}",
                original_filename=filename,
                file_type=file_type,
                file_format=file_extension,
                file_size=file_size,
                duration=duration,
                transcription_text=transcription_text,
                language='pt',
                processing_time=processing_time
            )
            
            db.session.add(transcription)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'transcription': transcription_text,
                'duration': transcription.get_formatted_duration(),
                'processing_time': round(processing_time, 2),
                'file_type': file_type,
                'file_format': file_extension
            })
            
        finally:
            # Limpar arquivo temporário
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro na transcrição: {str(e)}'}), 500

# Rota do histórico
@app.route('/api/history', methods=['GET'])
def get_history():
    try:
        # Verificar autenticação
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'message': 'Token não fornecido'}), 401
        
        token = auth_header.split(' ')[1]
        user_id = verify_token(token)
        
        if not user_id:
            return jsonify({'success': False, 'message': 'Token inválido'}), 401
        
        # Buscar transcrições do usuário
        transcriptions = Transcription.query.filter_by(user_id=user_id).order_by(Transcription.created_at.desc()).all()
        
        history = [t.to_dict() for t in transcriptions]
        
        return jsonify({
            'success': True,
            'history': history
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro ao buscar histórico: {str(e)}'}), 500

# Rota para deletar transcrição
@app.route('/api/history/<int:transcription_id>', methods=['DELETE'])
def delete_transcription(transcription_id):
    try:
        # Verificar autenticação
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'message': 'Token não fornecido'}), 401
        
        token = auth_header.split(' ')[1]
        user_id = verify_token(token)
        
        if not user_id:
            return jsonify({'success': False, 'message': 'Token inválido'}), 401
        
        # Buscar transcrição
        transcription = Transcription.query.filter_by(id=transcription_id, user_id=user_id).first()
        
        if not transcription:
            return jsonify({'success': False, 'message': 'Transcrição não encontrada'}), 404
        
        # Deletar transcrição
        db.session.delete(transcription)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Transcrição deletada com sucesso'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Erro ao deletar transcrição: {str(e)}'}), 500

# Rota principal
@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

# Rota para arquivos estáticos
@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory(app.static_folder, filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

