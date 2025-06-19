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

# Configurações
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

# Configuração de logs
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

# Rotas
@app.route('/')
def index():
    if not verificar_conexao_banco():
        flash('Erro de conexão com o banco de dados', 'danger')
        return render_template('index.html', comunicados=[])
    
    comunicados = Comunicado.query.order_by(Comunicado.data_publicacao.desc()).limit(100).all()
    return render_template('index.html', comunicados=comunicados)

@app.route('/adicionar', methods=['GET', 'POST'])
def adicionar_comunicado():
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
            flash('Erro ao adicionar comunicado', 'danger')
    
    return render_template('adicionar.html')

@app.route('/comunicado/<int:id>')
def ver_comunicado(id):
    comunicado = Comunicado.query.get_or_404(id)
    comunicado.conteudo = escape(comunicado.conteudo).replace('\n', '<br>')
    
    # Verificar se o usuário já reagiu
    ip_usuario = request.remote_addr
    reacao_usuario = Reacao.query.filter_by(
        comunicado_id=id,
        usuario_ip=ip_usuario
    ).first()
    
    # Contar reações
    likes = contar_reacoes(id, 'like')
    dislikes = contar_reacoes(id, 'dislike')
    
    return render_template(
        'comunicado.html', 
        comunicado=comunicado,
        likes=likes,
        dislikes=dislikes,
        reacao_usuario=reacao_usuario.tipo if reacao_usuario else None
    )

@app.route('/deletar/<int:id>', methods=['POST'])
def deletar_comunicado(id):
    comunicado = Comunicado.query.get_or_404(id)
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
def reagir(comunicado_id, tipo):
    if tipo not in ['like', 'dislike']:
        return redirect(url_for('ver_comunicado', id=comunicado_id))

    ip_usuario = request.remote_addr
    try:
        # Verificar se já existe reação deste usuário
        reacao_existente = Reacao.query.filter_by(
            comunicado_id=comunicado_id,
            usuario_ip=ip_usuario
        ).first()

        if reacao_existente:
            # Se já reagiu, atualiza ou remove a reação
            if reacao_existente.tipo == tipo:
                # Remove se for a mesma reação
                db.session.delete(reacao_existente)
            else:
                # Atualiza se for diferente
                reacao_existente.tipo = tipo
        else:
            # Adiciona nova reação
            nova_reacao = Reacao(
                tipo=tipo,
                comunicado_id=comunicado_id,
                usuario_ip=ip_usuario
            )
            db.session.add(nova_reacao)
        
        db.session.commit()
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

@app.route('/termos', methods=['POST'])
def termos():
    if request.form.get('concordo'):
        session['termos_aceitos'] = True
        return jsonify({'success': True})
    return jsonify({'success': False}), 400

@app.route('/solicitar_exclusao', methods=['POST'])
def solicitar_exclusao():
    email = request.form.get('email', '').strip()
    if not email:
        flash('Por favor, forneça um e-mail válido', 'danger')
        return redirect(url_for('index'))
    
    try:
        # Aqui você implementaria a lógica de envio de e-mail
        flash('Solicitação de exclusão recebida. Verifique seu e-mail para confirmação.', 'info')
    except Exception as e:
        logger.error(f"Erro ao processar solicitação de exclusão: {str(e)}")
        flash('Erro ao processar sua solicitação', 'danger')
    
    return redirect(url_for('index'))

@app.route('/health')
def health_check():
    db_ok = verificar_conexao_banco()
    status = {
        'database': 'online' if db_ok else 'offline',
        'status': 'up' if db_ok else 'down',
        'timestamp': datetime.utcnow().isoformat()
    }
    return jsonify(status), 200 if db_ok else 500

# Inicialização
with app.app_context():
    try:
        db.create_all()
    except Exception as e:
        logger.error(f"Erro ao criar tabelas: {str(e)}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG', 'false').lower() == 'true')