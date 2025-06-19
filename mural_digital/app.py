# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
from cryptography.fernet import Fernet

# Configuração inicial do Flask
app = Flask(__name__)

# =============================================
# CONFIGURAÇÕES LGPD (IMPORTANTE!)
# =============================================
# Gere sua chave com Fernet.generate_key() e armazene como variável de ambiente
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-apenas-para-testes')  # Troque em produção!
app.config['CHAVE_CRIPTOGRAFIA'] = os.environ.get('CHAVE_CRIPTOGRAFIA', Fernet.generate_key().decode())

# Configuração para criptografia
cipher_suite = Fernet(app.config['CHAVE_CRIPTOGRAFIA'].encode())

# =============================================
# BANCO DE DADOS
# =============================================
# Configuração do PostgreSQL (Render) ou SQLite (local)
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL or 'sqlite:///instance/mural.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# =============================================
# MODELOS (TABELAS DO BANCO)
# =============================================
class Comunicado(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(100), nullable=False)
    conteudo = db.Column(db.Text, nullable=False)
    data_publicacao = db.Column(db.DateTime, default=datetime.utcnow)
    prioridade = db.Column(db.String(20), default='normal')
    categoria = db.Column(db.String(50))
    # Adicione campos criptografados se necessário (ex: email_responsavel)

# =============================================
# ROTAS PRINCIPAIS
# =============================================
@app.route('/')
def index():
    if not session.get('termos_aceitos'):
        return redirect(url_for('termos'))
    
    comunicados = Comunicado.query.order_by(Comunicado.data_publicacao.desc()).all()
    return render_template('index.html', comunicados=comunicados)

@app.route('/adicionar', methods=['GET', 'POST'])
def adicionar_comunicado():
    if not session.get('termos_aceitos'):
        return redirect(url_for('termos'))

    if request.method == 'POST':
        titulo = request.form['titulo']
        conteudo = request.form['conteudo']
        prioridade = request.form['prioridade']
        categoria = request.form['categoria']
        
        novo_comunicado = Comunicado(
            titulo=titulo,
            conteudo=conteudo,
            prioridade=prioridade,
            categoria=categoria
        )
        
        db.session.add(novo_comunicado)
        db.session.commit()
        
        flash('Comunicado adicionado com sucesso!', 'success')
        return redirect(url_for('index'))
    
    return render_template('adicionar.html')

# =============================================
# ROTAS LGPD
# =============================================
@app.route('/termos', methods=['GET', 'POST'])
def termos():
    if request.method == 'POST' and request.form.get('concordo'):
        session['termos_aceitos'] = True
        return redirect(url_for('index'))
    return render_template('termos.html')

@app.route('/solicitar_exclusao', methods=['POST'])
def solicitar_exclusao():
    email = request.form['email']
    # Exemplo: criptografar o email antes de armazenar
    email_cripto = cipher_suite.encrypt(email.encode()).decode()
    
    # Aqui você deveria:
    # 1. Buscar todos os dados relacionados a esse email
    # 2. Excluir ou anonimizar os dados
    # 3. Registrar a solicitação em um log
    
    flash('Solicitação recebida. Seus dados serão excluídos em até 48h.', 'info')
    return redirect(url_for('index'))

# =============================================
# ROTAS AUXILIARES
# =============================================
@app.route('/comunicado/<int:id>')
def ver_comunicado(id):
    comunicado = Comunicado.query.get_or_404(id)
    return render_template('comunicado.html', comunicado=comunicado)

@app.route('/deletar/<int:id>')
def deletar_comunicado(id):
    comunicado = Comunicado.query.get_or_404(id)
    db.session.delete(comunicado)
    db.session.commit()
    flash('Comunicado removido com sucesso!', 'success')
    return redirect(url_for('index'))

# =============================================
# INICIALIZAÇÃO
# =============================================
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)