import sys
import os

# Adicionar o diretório raiz ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.main import app

# Exportar a aplicação Flask para o Vercel
app = app

