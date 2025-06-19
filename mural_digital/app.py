# app.py
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
from cryptography.fernet import Fernet

app = Flask(__name__)

# =============================================
# CONFIGURAÇÕES
# =============================================
# Segurança
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-local')
app.config['CHAVE_CRIPTOGRAFIA'] = os.environ.get('CHAVE_CRIPTOGRAFIA', Fernet.generate_key().decode())
cipher_suite = Fernet(app.config['CHAVE_CRIPTOGRAFIA'].encode())

# Banco de Dados - CORREÇÃO: 'SQLALCHEMY_DATABASE_URI' (estava escrito DATABASE_URI)
DATABASE_URL = os.environ.get('DATABASE_URL', '').replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL or 'sqlite:///instance/mural.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# =============================================
# MODELOS (TABELAS) - ADICIONANDO RELACIONAMENTOS
# =============================================
class Reacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20), nullable=False)  # 'like', 'urgente'
    comunicado_id = db.Column(db.Integer, db.ForeignKey('comunicado.id'))
    usuario_ip = db.Column(db.String(50))  # Identificação simplificada
    comunicado = db.relationship('Comunicado', backref='reacoes')  # Relacionamento adicionado

class Comentario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    texto = db.Column(db.Text, nullable=False)
    data = db.Column(db.DateTime, default=datetime.utcnow)
    comunicado_id = db.Column(db.Integer, db.ForeignKey('comunicado.id'))
    autor = db.Column(db.String(100), default='Anônimo')
    comunicado = db.relationship('Comunicado', backref='comentarios')  # Relacionamento adicionado

class Comunicado(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(100), nullable=False)
    conteudo = db.Column(db.Text, nullable=False)
    data_publicacao = db.Column(db.DateTime, default=datetime.utcnow)
    prioridade = db.Column(db.String(20), default='normal')  # alta, normal, baixa
    categoria = db.Column(db.String(50))  # comunicado, atualização, campanha

# =============================================
# ROTAS PRINCIPAIS - COM VALIDAÇÃO MELHORADA
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
        # Validação básica dos dados
        if not request.form['titulo'] or not request.form['conteudo']:
            flash('Preencha todos os campos obrigatórios!', 'danger')
            return redirect(url_for('adicionar_comunicado'))

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
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao adicionar comunicado: {str(e)}', 'danger')
    
    return render_template('adicionar.html')

# =============================================
# ROTAS DE ENGAJAMENTO - COM VALIDAÇÃO
# =============================================
@app.route('/reagir/<int:comunicado_id>/<tipo>')
def reagir(comunicado_id, tipo):
    if tipo not in ['like', 'urgente']:  # Validação do tipo
        flash('Tipo de reação inválido', 'danger')
        return redirect(url_for('ver_comunicado', id=comunicado_id))

    ip_usuario = request.remote_addr
    try:
        # Verifica se já reagiu
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
    texto = request.form.get('texto', '').strip()
    if not texto:
        flash('O comentário não pode estar vazio', 'danger')
        return redirect(url_for('ver_comunicado', id=comunicado_id))

    try:
        novo_comentario = Comentario(
            texto=texto,
            comunicado_id=comunicado_id
        )
        db.session.add(novo_comentario)
        db.session.commit()
        flash('Comentário adicionado!', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Erro ao adicionar comentário', 'danger')
    
    return redirect(url_for('ver_comunicado', id=comunicado_id))

# =============================================
# ROTAS LGPD - COM MELHOR TRATAMENTO
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
        # Criptografa o email
        email_cripto = cipher_suite.encrypt(email.encode()).decode()
        
        # Aqui você implementaria:
        # 1. Busca dos dados relacionados ao email
        # 2. Exclusão ou anonimização
        # 3. Registro em log da solicitação
        
        flash('Solicitação recebida. Seus dados serão processados em até 48h.', 'info')
    except Exception as e:
        flash('Erro ao processar sua solicitação', 'danger')
    
    return redirect(url_for('index'))

# =============================================
# ROTAS AUXILIARES - COM TRY-CATCH
# =============================================
@app.route('/comunicado/<int:id>')
def ver_comunicado(id):
    try:
        comunicado = Comunicado.query.get_or_404(id)
        return render_template('comunicado.html', comunicado=comunicado)
    except Exception as e:
        flash('Comunicado não encontrado', 'danger')
        return redirect(url_for('index'))

@app.route('/deletar/<int:id>')
def deletar_comunicado(id):
    try:
        comunicado = Comunicado.query.get_or_404(id)
        # Remove comentários e reações associadas primeiro
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
# INICIALIZAÇÃO COM VERIFICAÇÃO DE ERROS
# =============================================
def init_db():
    with app.app_context():
        try:
            db.create_all()
            print("Banco de dados inicializado com sucesso!")
        except Exception as e:
            print(f"Erro ao inicializar banco de dados: {str(e)}")

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)