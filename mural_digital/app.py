from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
from cryptography.fernet import Fernet
from markupsafe import escape
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
import logging
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import base64

app = Flask(__name__, template_folder='templates')

# Configurações FIXAS
app.config['SECRET_KEY'] = 'sua_chave_secreta_32_caracteres_aqui'  # Pode manter assim ou gerar uma nova
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://mural_db_rkkn_user:aDbHbTqwyIoe8qCaD6hLwNi3ZhVm833t@dpg-d1absdmmcj7s73fck580-a.oregon-postgres.render.com/mural_db_rkkn'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
    'pool_timeout': 30,
    'max_overflow': 60,
    'pool_size': 10
}

# Proteção CSRF
csrf = CSRFProtect(app)

# Configuração do Flask-Login
login_manager = LoginManager(app)
login_manager.login_view = 'login'

db = SQLAlchemy(app)

# Configuração de logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Modelos (mantive todos os seus modelos originais)
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    nome = db.Column(db.String(100), nullable=False)
    comunicados = db.relationship('Comunicado', backref='autor', lazy=True, cascade="all, delete-orphan")

class Reacao(db.Model):
    __tablename__ = 'reacoes'
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20), nullable=False)
    comunicado_id = db.Column(db.Integer, db.ForeignKey('comunicados.id', ondelete="CASCADE"))
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete="CASCADE"))
    comunicado = db.relationship('Comunicado', backref='reacoes')
    usuario = db.relationship('User')

class Comentario(db.Model):
    __tablename__ = 'comentarios'
    id = db.Column(db.Integer, primary_key=True)
    texto = db.Column(db.Text, nullable=False)
    data = db.Column(db.DateTime, default=datetime.utcnow)
    comunicado_id = db.Column(db.Integer, db.ForeignKey('comunicados.id', ondelete="CASCADE"))
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete="CASCADE"))
    comunicado = db.relationship('Comunicado', backref='comentarios')
    usuario = db.relationship('User')

class Comunicado(db.Model):
    __tablename__ = 'comunicados'
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(100), nullable=False)
    conteudo = db.Column(db.Text, nullable=False)
    data_publicacao = db.Column(db.DateTime, default=datetime.utcnow)
    prioridade = db.Column(db.String(20), default='normal')
    categoria = db.Column(db.String(50), default='comunicado')
    usuario_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete="CASCADE"), nullable=False)

# Configuração do Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Funções auxiliares
def verificar_conexao_banco():
    try:
        with db.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Erro na conexão com o banco: {str(e)}")
        return False

def contar_reacoes(comunicado_id, tipo):
    return Reacao.query.filter_by(comunicado_id=comunicado_id, tipo=tipo).count()

# Rotas (mantive todas as suas rotas originais)
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash('Login realizado com sucesso!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Usuário ou senha incorretos', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você foi desconectado com sucesso', 'info')
    return redirect(url_for('index'))

@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        username = request.form.get('username')
        nome = request.form.get('nome')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            flash('As senhas não coincidem', 'danger')
            return redirect(url_for('cadastro'))
        
        if User.query.filter_by(username=username).first():
            flash('Nome de usuário já existe', 'danger')
            return redirect(url_for('cadastro'))
        
        new_user = User(
            username=username,
            nome=nome,
            password=generate_password_hash(password, method='pbkdf2:sha256'),
            is_admin=False
        )
        
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('Cadastro realizado com sucesso! Faça login', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao cadastrar usuário: {str(e)}")
            flash('Erro ao cadastrar usuário', 'danger')
    return render_template('cadastro.html')

@app.route('/')
def index():
    if not verificar_conexao_banco():
        flash('Erro de conexão com o banco de dados', 'danger')
        return render_template('index.html', comunicados=[])
    comunicados = Comunicado.query.order_by(Comunicado.data_publicacao.desc()).limit(100).all()
    return render_template('index.html', comunicados=comunicados)

@app.route('/adicionar', methods=['GET', 'POST'])
@login_required
def adicionar_comunicado():
    if not current_user.is_admin:
        flash('Apenas administradores podem criar comunicados', 'danger')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        titulo = request.form['titulo'].strip()
        conteudo = request.form['conteudo'].strip()
        if not titulo or not conteudo:
            flash('Título e conteúdo são obrigatórios', 'danger')
            return redirect(url_for('adicionar_comunicado'))
            
        novo_comunicado = Comunicado(
            titulo=titulo,
            conteudo=conteudo,
            prioridade=request.form.get('prioridade', 'normal'),
            categoria=request.form.get('categoria', 'comunicado'),
            usuario_id=current_user.id
        )
        try:
            db.session.add(novo_comunicado)
            db.session.commit()
            flash('Comunicado adicionado com sucesso!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao adicionar comunicado: {str(e)}")
            flash('Erro ao adicionar comunicado', 'danger')
    return render_template('adicionar.html')

@app.route('/comunicado/<int:id>')
def ver_comunicado(id):
    comunicado = Comunicado.query.get_or_404(id)
    comunicado.conteudo = escape(comunicado.conteudo).replace('\n', '<br>')
    reacao_usuario = None
    if current_user.is_authenticated:
        reacao_usuario = Reacao.query.filter_by(comunicado_id=id, usuario_id=current_user.id).first()
    likes = contar_reacoes(id, 'like')
    dislikes = contar_reacoes(id, 'dislike')
    return render_template('comunicado.html', comunicado=comunicado, likes=likes, dislikes=dislikes,
                         reacao_usuario=reacao_usuario.tipo if reacao_usuario else None, autor=comunicado.autor)

@app.route('/deletar/<int:id>', methods=['POST'])
@login_required
def deletar_comunicado(id):
    comunicado = Comunicado.query.get_or_404(id)
    if not current_user.is_admin and comunicado.usuario_id != current_user.id:
        flash('Você não tem permissão para excluir este comunicado', 'danger')
        return redirect(url_for('ver_comunicado', id=id))
    try:
        Comentario.query.filter_by(comunicado_id=id).delete()
        Reacao.query.filter_by(comunicado_id=id).delete()
        db.session.delete(comunicado)
        db.session.commit()
        flash('Comunicado deletado com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao deletar comunicado: {str(e)}")
        flash('Erro ao deletar comunicado', 'danger')
    return redirect(url_for('index'))

@app.route('/reagir/<int:comunicado_id>/<tipo>')
@login_required
def reagir(comunicado_id, tipo):
    if tipo not in ['like', 'dislike']:
        flash('Tipo de reação inválido', 'danger')
        return redirect(url_for('ver_comunicado', id=comunicado_id))
    try:
        reacao_existente = Reacao.query.filter_by(comunicado_id=comunicado_id, usuario_id=current_user.id).first()
        if reacao_existente:
            if reacao_existente.tipo == tipo:
                db.session.delete(reacao_existente)
                flash('Reação removida', 'info')
            else:
                reacao_existente.tipo = tipo
                flash('Reação atualizada', 'success')
        else:
            nova_reacao = Reacao(tipo=tipo, comunicado_id=comunicado_id, usuario_id=current_user.id)
            db.session.add(nova_reacao)
            flash('Reação registrada', 'success')
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao registrar reação: {str(e)}")
        flash('Erro ao registrar reação', 'danger')
    return redirect(url_for('ver_comunicado', id=comunicado_id))

@app.route('/comentar/<int:comunicado_id>', methods=['POST'])
@login_required
def comentar(comunicado_id):
    texto = request.form.get('texto', '').strip()
    if not texto:
        flash('O comentário não pode estar vazio', 'danger')
        return redirect(url_for('ver_comunicado', id=comunicado_id))
    try:
        novo_comentario = Comentario(texto=texto, comunicado_id=comunicado_id, usuario_id=current_user.id)
        db.session.add(novo_comentario)
        db.session.commit()
        flash('Comentário adicionado!', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao adicionar comentário: {str(e)}")
        flash('Erro ao adicionar comentário', 'danger')
    return redirect(url_for('ver_comunicado', id=comunicado_id))

@app.route('/excluir_comentario/<int:id>', methods=['POST'])
@login_required
def excluir_comentario(id):
    comentario = Comentario.query.get_or_404(id)
    if comentario.usuario_id != current_user.id and not current_user.is_admin:
        flash('Você não tem permissão para excluir este comentário', 'danger')
        return redirect(url_for('ver_comunicado', id=comentario.comunicado_id))
    try:
        db.session.delete(comentario)
        db.session.commit()
        flash('Comentário excluído com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao excluir comentário: {str(e)}")
        flash('Erro ao excluir comentário', 'danger')
    return redirect(url_for('ver_comunicado', id=comentario.comunicado_id))

@app.route('/termos', methods=['POST'])
def termos():
    session['termos_aceitos'] = True
    return jsonify({'success': True})

@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy'}), 200

# Inicialização do Banco de Dados
def criar_tabelas():
    with app.app_context():
        try:
            db.create_all()
            if not User.query.filter_by(username='admin').first():
                admin = User(
                    username='admin',
                    nome='Administrador',
                    password=generate_password_hash('admin123'),
                    is_admin=True
                )
                db.session.add(admin)
                db.session.commit()
                logger.info("✅ Tabelas criadas e usuário admin cadastrado!")
        except Exception as e:
            logger.error(f"Erro ao criar tabelas: {str(e)}")

criar_tabelas()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)