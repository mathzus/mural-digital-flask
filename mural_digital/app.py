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

app = Flask(__name__, template_folder='templates')

# Configurações para produção no Render
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', Fernet.generate_key().decode())
app.config['CHAVE_CRIPTOGRAFIA'] = os.environ.get('CHAVE_CRIPTOGRAFIA', Fernet.generate_key().decode())
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL').replace("postgres://", "postgresql://", 1)
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

db = SQLAlchemy(app)
cipher_suite = Fernet(app.config['CHAVE_CRIPTOGRAFIA'].encode())

# Configuração de logs para produção
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Modelos
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

# Função melhorada para verificar conexão com o banco
def verificar_conexao_banco():
    try:
        with db.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Conexão com o banco de dados estabelecida com sucesso")
        return True
    except Exception as e:
        logger.error(f"Erro na conexão com o banco: {str(e)}")
        return False

# Rotas
@app.route('/')
def index():
    if not verificar_conexao_banco():
        flash('Sistema temporariamente indisponível. Por favor, tente novamente mais tarde.', 'danger')
        return render_template('index.html', comunicados=[])
    
    if not session.get('termos_aceitos'):
        return redirect(url_for('termos'))
    
    try:
        comunicados = Comunicado.query.order_by(Comunicado.data_publicacao.desc()).limit(100).all()
        return render_template('index.html', comunicados=comunicados)
    except Exception as e:
        logger.error(f"Erro ao buscar comunicados: {str(e)}")
        flash('Erro ao carregar comunicados', 'danger')
        return render_template('index.html', comunicados=[])

@app.route('/adicionar', methods=['GET', 'POST'])
def adicionar_comunicado():
    if not session.get('termos_aceitos'):
        return redirect(url_for('termos'))

    if request.method == 'POST':
        titulo = request.form['titulo'].strip()
        conteudo = request.form['conteudo'].strip()
        
        if len(titulo) < 5 or len(conteudo) < 10:
            flash('Título deve ter pelo menos 5 caracteres e conteúdo pelo menos 10 caracteres', 'danger')
            return redirect(url_for('adicionar_comunicado'))
            
        novo_comunicado = Comunicado(
            titulo=titulo,
            conteudo=conteudo,
            prioridade=request.form.get('prioridade', 'normal'),
            categoria=request.form.get('categoria', 'comunicado')
        )
        try:
            db.session.add(novo_comunicado)
            db.session.commit()
            flash('Comunicado adicionado com sucesso!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao adicionar comunicado: {str(e)}")
            flash('Erro ao adicionar comunicado. Por favor, tente novamente.', 'danger')
    
    return render_template('adicionar.html')

@app.route('/comunicado/<int:id>')
def ver_comunicado(id):
    try:
        comunicado = Comunicado.query.get_or_404(id)
        comunicado.conteudo = escape(comunicado.conteudo).replace('\n', '<br>')
        return render_template('comunicado.html', comunicado=comunicado)
    except Exception as e:
        logger.error(f"Erro ao acessar comunicado {id}: {str(e)}")
        flash('Comunicado não encontrado', 'danger')
        return redirect(url_for('index'))

@app.route('/deletar/<int:id>', methods=['POST'])
def deletar_comunicado(id):
    try:
        comunicado = Comunicado.query.get_or_404(id)
        Comentario.query.filter_by(comunicado_id=id).delete()
        Reacao.query.filter_by(comunicado_id=id).delete()
        db.session.delete(comunicado)
        db.session.commit()
        flash('Comunicado deletado com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao deletar comunicado {id}: {str(e)}")
        flash('Erro ao deletar comunicado', 'danger')
    
    return redirect(url_for('index'))

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
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao registrar reação: {str(e)}")
    
    return redirect(url_for('ver_comunicado', id=comunicado_id))

@app.route('/comentar/<int:comunicado_id>', methods=['POST'])
def comentar(comunicado_id):
    texto = request.form.get('texto', '').strip()
    if not texto:
        flash('O comentário não pode estar vazio', 'danger')
        return redirect(url_for('ver_comunicado', id=comunicado_id))

    try:
        novo_comentario = Comentario(
            texto=texto,
            comunicado_id=comunicado_id,
            autor=request.form.get('autor', 'Anônimo').strip() or 'Anônimo'
        )
        db.session.add(novo_comentario)
        db.session.commit()
        flash('Comentário adicionado!', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao adicionar comentário: {str(e)}")
        flash('Erro ao adicionar comentário', 'danger')
    
    return redirect(url_for('ver_comunicado', id=comunicado_id))

@app.route('/termos', methods=['GET', 'POST'])
def termos():
    if request.method == 'POST':
        if request.form.get('concordo'):
            session['termos_aceitos'] = True
            return redirect(url_for('index'))
        else:
            flash('Você precisa aceitar os termos para continuar', 'warning')
    return render_template('termos.html')

@app.route('/solicitar_exclusao', methods=['POST'])
def solicitar_exclusao():
    email = request.form.get('email', '').strip()
    if not email:
        flash('Por favor, forneça um e-mail válido', 'danger')
        return redirect(url_for('termos'))
    
    try:
        # Implementação do envio de e-mail ficaria aqui
        flash('Solicitação de exclusão recebida. Verifique seu e-mail para confirmação.', 'info')
    except Exception as e:
        logger.error(f"Erro ao processar solicitação de exclusão: {str(e)}")
        flash('Erro ao processar sua solicitação', 'danger')
    
    return redirect(url_for('index'))

@app.route('/health')
def health_check():
    try:
        db_ok = verificar_conexao_banco()
        status = {
            'status': 'healthy' if db_ok else 'unhealthy',
            'database': 'connected' if db_ok else 'disconnected',
            'timestamp': datetime.utcnow().isoformat(),
            'service': 'mural-digital-flask'
        }
        return jsonify(status), 200 if db_ok else 503
    except Exception as e:
        logger.error(f"Erro no health check: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Inicialização otimizada para produção
with app.app_context():
    try:
        db.create_all()
        logger.info("Tabelas do banco de dados verificadas/criadas com sucesso")
    except Exception as e:
        logger.error(f"Erro ao inicializar banco de dados: {str(e)}")
        raise e  # Isso fará com que o deploy falhe se não conseguir conectar ao banco

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    debug_mode = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug_mode)