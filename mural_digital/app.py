# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
from cryptography.fernet import Fernet
from markupsafe import escape
from sqlalchemy.exc import OperationalError

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
    'pool_pre_ping': True,  # Reconecta automaticamente se a conexão cair
    'pool_recycle': 300,    # Recicla conexões a cada 5 minutos
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
# VERIFICAÇÃO DE CONEXÃO COM O BANCO
# =============================================
def verificar_conexao_banco():
    try:
        db.session.execute("SELECT 1")
        return True
    except OperationalError as e:
        print(f"Erro de conexão com o banco: {str(e)}")
        return False

# =============================================
# ROTAS PRINCIPAIS
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
            flash(f'Erro ao adicionar comunicado: {str(e)}', 'danger')
    
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
        flash(f'Erro ao carregar comunicado: {str(e)}', 'danger')
        return redirect(url_for('index'))

# =============================================
# ROTAS DE ENGAJAMENTO
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
        flash('Erro ao excluir comentário', 'danger')
    
    return redirect(url_for('ver_comunicado', id=comunicado_id))

# =============================================
# ROTAS LGPD
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
        # Aqui você salvaria email_cripto no banco de dados
        flash('Solicitação recebida. Seus dados serão processados em até 48h.', 'info')
    except Exception as e:
        flash('Erro ao processar sua solicitação', 'danger')
    
    return redirect(url_for('index'))

# =============================================
# ROTAS AUXILIARES
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
        flash('Erro ao excluir comunicado', 'danger')
    
    return redirect(url_for('index'))

# =============================================
# INICIALIZAÇÃO DO BANCO DE DADOS
# =============================================
def inicializar_banco():
    with app.app_context():
        try:
            db.create_all()
            print("✅ Banco de dados inicializado com sucesso!")
            
            # Verifica se as tabelas foram criadas corretamente
            tabelas = db.engine.table_names()
            print(f"📊 Tabelas existentes: {tabelas}")
            
        except Exception as e:
            print(f"❌ Erro ao inicializar banco de dados: {str(e)}")
            # Tentativa de reconexão
            try:
                db.session.rollback()
                db.create_all()
                print("✅ Reconexão bem-sucedida!")
            except Exception as e2:
                print(f"❌ Falha na reconexão: {str(e2)}")

inicializar_banco()

# =============================================
# CONFIGURAÇÃO DO SERVIDOR
# =============================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)