from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

# Configuração do Banco de Dados (PostgreSQL no Render ou SQLite local)
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL or 'sqlite:///instance/mural.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class Comunicado(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(100), nullable=False)
    conteudo = db.Column(db.Text, nullable=False)
    data_publicacao = db.Column(db.DateTime, default=datetime.utcnow)
    prioridade = db.Column(db.String(20), default='normal')
    categoria = db.Column(db.String(50))

# Cria o banco de dados
with app.app_context():
    db.create_all()

@app.route('/')
def index():
    comunicados = Comunicado.query.order_by(Comunicado.data_publicacao.desc()).all()
    return render_template('index.html', comunicados=comunicados)

@app.route('/adicionar', methods=['GET', 'POST'])
def adicionar_comunicado():
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)