from datetime import datetime
from src.database import db

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
            'duration': self.duration,
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
    
    def get_formatted_file_size(self):
        """Retorna o tamanho do arquivo formatado"""
        if not self.file_size:
            return "N/A"
        
        if self.file_size < 1024:
            return f"{self.file_size} B"
        elif self.file_size < 1024 * 1024:
            return f"{self.file_size / 1024:.1f} KB"
        else:
            return f"{self.file_size / (1024 * 1024):.1f} MB"

