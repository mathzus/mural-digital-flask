# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
from cryptography.fernet import Fernet
from markupsafe import escape
from sqlalchemy import text  # Importação adicionada
from sqlalchemy.exc import OperationalError, SQLAlchemyError  # Exceção mais abrangente

app = Flask(__name__)

# =============================================
# CONFIGURAÇÕES
# =============================================
# Segurança
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-local')
app.config['CHAVE_CRIPTOGRAFIA'] = os.environ.get('CHAVE_CRIPTOGRAFIA', Fernet.generate_key().decode())
cipher_suite = Fernet(app.config['CHAVE_CRIPTOGRAFIA'].encode())

# Banco de Dados - Configuração otimizada para Render
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', '').replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
    'pool_timeout': 30,
    'max_overflow': 10,
    'pool_size': 5
}
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
# VERIFICAÇÃO DE CONEXÃO COM O BANCO (CORRIGIDA)
# =============================================
def verificar_conexao_banco():
    try:
        db.session.execute(text("SELECT 1"))  # Corrigido com text()
        db.session.commit()
        return True
    except Exception as e:  # Captura qualquer erro
        db.session.rollback()
        print(f"ERRO DE CONEXÃO: {str(e)}")  # Log detalhado
        return False

# =============================================
# ROTAS PRINCIPAIS (ATUALIZADAS)
# =============================================
@app.route('/')
def index():
    if not verificar_conexao_banco():
        flash('Erro de conexão com o banco de dados. Tente novamente.', 'danger')
        return render_template('index.html', comunicados=[])
    
    if not session.get('termos_aceitos'):
        return redirect(url_for('termos'))
    
    try:
        comunicados = Comunicado.query.order_by(Comunicado.data_publicacao.desc()).all()
        return render_template('index.html', comunicados=comunicados)
    except Exception as e:
        print(f"ERRO AO CARREGAR COMUNICADOS: {str(e)}")
        flash('Erro ao carregar comunicados', 'danger')
        return render_template('index.html', comunicados=[])

@app.route('/adicionar', methods=['GET', 'POST'])
def adicionar_comunicado():
    if not verificar_conexao_banco():
        flash('Erro de conexão com o banco de dados', 'danger')
        return redirect(url_for('index'))
    
    if not session.get('termos_aceitos'):
        return redirect(url_for('termos'))

    if request.method == 'POST':
        titulo = request.form.get('titulo', '').strip()
        conteudo = request.form.get('conteudo', '').strip()
        prioridade = request.form.get('prioridade', 'normal')
        categoria = request.form.get('categoria', 'comunicado')

        if not titulo or not conteudo:
            flash('Preencha todos os campos obrigatórios!', 'danger')
            return redirect(url_for('adicionar_comunicado'))

        # Validações
        prioridades_validas = ['alta', 'normal', 'baixa']
        categorias_validas = ['comunicado', 'atualização', 'campanha']
        
        if prioridade not in prioridades_validas:
            prioridade = 'normal'
        if categoria not in categorias_validas:
            categoria = 'comunicado'

        novo_comunicado = Comunicado(
            titulo=titulo,
            conteudo=conteudo,
            prioridade=prioridade,
            categoria=categoria
        )
        
        try:
            db.session.add(novo_comunicado)
            db.session.commit()
            flash('Comunicado adicionado com sucesso!', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            db.session.rollback()
            print(f"ERRO AO ADICIONAR: {str(e)}")
            flash('Erro ao adicionar comunicado', 'danger')
    
    return render_template('adicionar.html')

@app.route('/comunicado/<int:id>')
def ver_comunicado(id):
    if not verificar_conexao_banco():
        flash('Erro de conexão com o banco de dados', 'danger')
        return redirect(url_for('index'))
    
    try:
        comunicado = Comunicado.query.options(
            db.joinedload(Comunicado.comentarios).order_by(Comentario.data.desc()),
            db.joinedload(Comunicado.reacoes)
        ).get_or_404(id)
        
        comunicado.conteudo = escape(comunicado.conteudo).replace('\n', '<br>')
        return render_template('comunicado.html', comunicado=comunicado)
    except Exception as e:
        print(f"ERRO AO VISUALIZAR: {str(e)}")
        flash('Comunicado não encontrado', 'danger')
        return redirect(url_for('index'))

# =============================================
# ROTAS DE ENGAJAMENTO (MANTIDAS)
# =============================================
@app.route('/reagir/<int:comunicado_id>/<tipo>')
def reagir(comunicado_id, tipo):
    if not verificar_conexao_banco():
        flash('Erro de conexão com o banco de dados', 'danger')
        return redirect(url_for('index'))
    
    if tipo not in ['like', 'urgente']:
        flash('Tipo de reação inválido', 'danger')
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
        else:
            flash('Você já reagiu a este post', 'info')
    except Exception as e:
        db.session.rollback()
        print(f"ERRO AO REAGIR: {str(e)}")
        flash('Erro ao processar sua reação', 'danger')
    
    return redirect(url_for('ver_comunicado', id=comunicado_id))

@app.route('/comentar/<int:comunicado_id>', methods=['POST'])
def comentar(comunicado_id):
    if not verificar_conexao_banco():
        flash('Erro de conexão com o banco de dados', 'danger')
        return redirect(url_for('index'))
    
    texto = request.form.get('texto', '').strip()
    autor = request.form.get('autor', 'Anônimo').strip()[:100]

    if not texto:
        flash('O comentário não pode estar vazio', 'danger')
        return redirect(url_for('ver_comunicado', id=comunicado_id))

    try:
        novo_comentario = Comentario(
            texto=texto,
            autor=autor,
            comunicado_id=comunicado_id
        )
        db.session.add(novo_comentario)
        db.session.commit()
        flash('Comentário adicionado!', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"ERRO AO COMENTAR: {str(e)}")
        flash('Erro ao adicionar comentário', 'danger')
    
    return redirect(url_for('ver_comunicado', id=comunicado_id))

@app.route('/deletar_comentario/<int:id>', methods=['POST'])
def deletar_comentario(id):
    if not verificar_conexao_banco():
        flash('Erro de conexão com o banco de dados', 'danger')
        return redirect(url_for('index'))
    
    try:
        comentario = Comentario.query.get_or_404(id)
        comunicado_id = comentario.comunicado_id
        db.session.delete(comentario)
        db.session.commit()
        flash('Comentário removido!', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"ERRO AO DELETAR: {str(e)}")
        flash('Erro ao excluir comentário', 'danger')
    
    return redirect(url_for('ver_comunicado', id=comunicado_id))

# =============================================
# ROTAS LGPD (MANTIDAS)
# =============================================
@app.route('/termos', methods=['GET', 'POST'])
def termos():
    if request.method == 'POST':
        if request.form.get('concordo'):
            session['termos_aceitos'] = True
            flash('Termos aceitos com sucesso!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Você precisa aceitar os termos para continuar', 'warning')
    return render_template('termos.html')

@app.route('/solicitar_exclusao', methods=['POST'])
def solicitar_exclusao():
    email = request.form.get('email', '').strip()
    if not email:
        flash('Por favor, informe um e-mail válido', 'danger')
        return redirect(url_for('index'))

    try:
        email_cripto = cipher_suite.encrypt(email.encode()).decode()
        flash('Solicitação recebida. Seus dados serão processados em até 48h.', 'info')
    except Exception as e:
        print(f"ERRO CRIPTOGRAFIA: {str(e)}")
        flash('Erro ao processar sua solicitação', 'danger')
    
    return redirect(url_for('index'))

# =============================================
# ROTAS AUXILIARES (ATUALIZADAS)
# =============================================
@app.route('/deletar/<int:id>', methods=['POST'])
def deletar_comunicado(id):
    if not verificar_conexao_banco():
        flash('Erro de conexão com o banco de dados', 'danger')
        return redirect(url_for('index'))
    
    try:
        comunicado = Comunicado.query.get_or_404(id)
        Comentario.query.filter_by(comunicado_id=id).delete()
        Reacao.query.filter_by(comunicado_id=id).delete()
        db.session.delete(comunicado)
        db.session.commit()
        flash('Comunicado e dados relacionados removidos com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        print(f"ERRO AO DELETAR COMUNICADO: {str(e)}")
        flash('Erro ao excluir comunicado', 'danger')
    
    return redirect(url_for('index'))

# =============================================
# INICIALIZAÇÃO DO BANCO DE DADOS (OTIMIZADA)
# =============================================
def inicializar_banco():
    with app.app_context():
        max_tentativas = 3
        tentativa = 0
        
        while tentativa < max_tentativas:
            try:
                db.create_all()
                print("✅ Banco de dados inicializado com sucesso!")
                print(f"📊 Tabelas existentes: {db.engine.table_names()}")
                break
            except Exception as e:
                tentativa += 1
                print(f"❌ Tentativa {tentativa}/{max_tentativas}: {str(e)}")
                db.session.rollback()
                if tentativa == max_tentativas:
                    print("🔥 Falha crítica ao inicializar o banco")
                    raise

inicializar_banco()

# =============================================
# CONFIGURAÇÃO DO SERVIDOR
# =============================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)