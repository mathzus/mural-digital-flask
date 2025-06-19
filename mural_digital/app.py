# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
from cryptography.fernet import Fernet
from markupsafe import escape
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

app = Flask(__name__)

# =============================================
# CONFIGURAÇÕES
# =============================================
# Segurança
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-local')
app.config['CHAVE_CRIPTOGRAFIA'] = os.environ.get('CHAVE_CRIPTOGRAFIA', Fernet.generate_key().decode())
cipher_suite = Fernet(app.config['CHAVE_CRIPTOGRAFIA'].encode())

# Banco de Dados
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', '').replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# =============================================
# MODELOS (TABELAS)
# =============================================
class Reacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20), nullable=False)
    comunicado_id = db.Column(db.Integer, db.ForeignKey('comunicado.id'))
    usuario_ip = db.Column(db.String(50))
    comunicado = db.relationship('Comunicado', backref='reacoes')

class Comentario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    texto = db.Column(db.Text, nullable=False)
    data = db.Column(db.DateTime, default=datetime.utcnow)
    comunicado_id = db.Column(db.Integer, db.ForeignKey('comunicado.id'))
    autor = db.Column(db.String(100), nullable=False, default='Anônimo')
    comunicado = db.relationship('Comunicado', backref='comentarios')

class Comunicado(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(100), nullable=False)
    conteudo = db.Column(db.Text, nullable=False)
    data_publicacao = db.Column(db.DateTime, default=datetime.utcnow)
    prioridade = db.Column(db.String(20), default='normal')
    categoria = db.Column(db.String(50), default='comunicado')

# =============================================
# VERIFICAÇÃO DE CONEXÃO COM O BANCO
# =============================================
def verificar_conexao_banco():
    try:
        db.session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

# =============================================
# ROTAS PRINCIPAIS
# =============================================
@app.route('/')
def index():
    if not verificar_conexao_banco():
        flash('Erro de conexão com o banco de dados', 'danger')
        return render_template('index.html', comunicados=[])
    
    if not session.get('termos_aceitos'):
        return redirect(url_for('termos'))
    
    comunicados = Comunicado.query.order_by(Comunicado.data_publicacao.desc()).all()
    return render_template('index.html', comunicados=comunicados)

@app.route('/adicionar', methods=['GET', 'POST'])
def adicionar_comunicado():
    if not session.get('termos_aceitos'):
        return redirect(url_for('termos'))

    if request.method == 'POST':
        novo_comunicado = Comunicado(
            titulo=request.form['titulo'].strip(),
            conteudo=request.form['conteudo'].strip(),
            prioridade=request.form.get('prioridade', 'normal'),
            categoria=request.form.get('categoria', 'comunicado')
        )
        try:
            db.session.add(novo_comunicado)
            db.session.commit()
            flash('Comunicado adicionado com sucesso!', 'success')
            return redirect(url_for('index'))
        except Exception:
            db.session.rollback()
            flash('Erro ao adicionar comunicado', 'danger')
    
    return render_template('adicionar.html')

@app.route('/comunicado/<int:id>')
def ver_comunicado(id):
    comunicado = Comunicado.query.get_or_404(id)
    comunicado.conteudo = escape(comunicado.conteudo).replace('\n', '<br>')
    return render_template('comunicado.html', comunicado=comunicado)

# =============================================
# ROTAS DE ENGAJAMENTO
# =============================================
@app.route('/reagir/<int:comunicado_id>/<tipo>')
def reagir(comunicado_id, tipo):
    if tipo not in ['like', 'urgente']:
        return redirect(url_for('ver_comunicado', id=comunicado_id))

    ip_usuario = request.remote_addr
    try:
        reacao_existente = Reacao.query.filter_by(
            comunicado_id=comunicado_id,
            usuario_ip=ip_usuario
        ).first()

        if not reacao_existente:
            nova_reacao = Reacao(
                tipo=tipo,
                comunicado_id=comunicado_id,
                usuario_ip=ip_usuario
            )
            db.session.add(nova_reacao)
            db.session.commit()
            flash('Reação registrada!', 'success')
    except Exception:
        db.session.rollback()
    
    return redirect(url_for('ver_comunicado', id=comunicado_id))

@app.route('/comentar/<int:comunicado_id>', methods=['POST'])
def comentar(comunicado_id):
    texto = request.form.get('texto', '').strip()
    if not texto:
        return redirect(url_for('ver_comunicado', id=comunicado_id))

    try:
        novo_comentario = Comentario(
            texto=texto,
            comunicado_id=comunicado_id
        )
        db.session.add(novo_comentario)
        db.session.commit()
    except Exception:
        db.session.rollback()
    
    return redirect(url_for('ver_comunicado', id=comunicado_id))

# =============================================
# ROTAS LGPD
# =============================================
@app.route('/termos', methods=['GET', 'POST'])
def termos():
    if request.method == 'POST':
        if request.form.get('concordo'):
            session['termos_aceitos'] = True
            return redirect(url_for('index'))
    return render_template('termos.html')

# =============================================
# INICIALIZAÇÃO
# =============================================
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)