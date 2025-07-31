import sys
import os

# Adicionar o diretório raiz ao path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

try:
    from src.main import app
except ImportError as e:
    # Fallback para uma aplicação Flask simples se houver erro de import
    from flask import Flask
    app = Flask(__name__)
    
    @app.route('/')
    def hello():
        return f"<h1>KN Scribe - Import Error</h1><p>Error: {str(e)}</p><p>Current dir: {current_dir}</p><p>Parent dir: {parent_dir}</p><p>Python path: {sys.path}</p>"

# Exportar a aplicação Flask para o Vercel
app = app

