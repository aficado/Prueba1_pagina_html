import os
import requests
from random import shuffle
from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)

# --- CONFIGURACIÓN ---
app.secret_key = 'super_secreto_clave_madre'
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tienda.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- CONFIGURACIÓN DE TELEGRAM (vía n8n) ---
N8N_WEBHOOK_URL = 'http://localhost:5678/webhook/nuevo-pedido'

db = SQLAlchemy(app)

# --- FUNCIONES AUXILIARES ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- MODELOS BASE DE DATOS ---
class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

class Categoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False, unique=True)
    subcategorias = db.relationship('SubCategoria', backref='categoria', lazy=True, cascade="all, delete-orphan")

class SubCategoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'), nullable=False)
    productos = db.relationship('Producto', backref='subcategoria', lazy=True, cascade="all, delete-orphan")

class Producto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    precio = db.Column(db.Float, nullable=False)
    existencia = db.Column(db.Integer, default=0)
    imagen_filename = db.Column(db.String(150), default='default.png')
    subcategoria_id = db.Column(db.Integer, db.ForeignKey('sub_categoria.id'), nullable=False)

# --- RUTAS DE CONFIGURACIÓN Y LOGIN ---
@app.route('/setup', methods=['GET', 'POST'])
def setup():
    if Usuario.query.first(): return redirect(url_for('login'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_pw = generate_password_hash(password)
        db.session.add(Usuario(username=username, password_hash=hashed_pw))
        db.session.commit()
        session['user_id'] = 1
        flash('¡Administrador creado con éxito!')
        return redirect(url_for('admin'))
    return render_template('setup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if not Usuario.query.first(): return redirect(url_for('setup'))
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = Usuario.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            return redirect(url_for('admin'))
        else:
            flash('Usuario o contraseña incorrectos')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('index'))

# --- RUTAS DE LA TIENDA (PÚBLICAS) ---
@app.route('/')
def index():
    # Cargar categorías para sidebar
    categorias = Categoria.query.all()
    # Cargar TODOS los productos y MEZCLARLOS (Shuffle)
    todos_productos = Producto.query.all()
    shuffle(todos_productos)
    return render_template('tienda.html', categorias=categorias, productos=todos_productos, es_home=True)

@app.route('/buscar')
def buscar():
    query = request.args.get('q', '')
    if not query: return redirect(url_for('index'))
    productos = Producto.query.filter(Producto.nombre.ilike(f'%{query}%')).all()
    categorias = Categoria.query.all()
    return render_template('tienda.html', categorias=categorias, productos=productos, busqueda=query, es_home=False)

@app.route('/categoria/<int:sub_id>')
def ver_subcategoria(sub_id):
    subcategoria = db.session.get(SubCategoria, sub_id)
    if not subcategoria: return redirect(url_for('index'))
    categorias = Categoria.query.all()
    return render_template('tienda.html', categorias=categorias, productos=subcategoria.productos, sub_actual=subcategoria, es_home=False)

# --- PROCESAMIENTO DE PEDIDOS ---
@app.route('/procesar_pedido', methods=['POST'])
def procesar_pedido():
    data = request.get_json()
    cliente = data.get('cliente')
    carrito = data.get('productos')
    total = data.get('total')

    if not carrito: return jsonify({'success': False, 'message': 'Carrito vacío'}), 400

    fecha_hora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ticket = f"--- PEDIDO NUEVO ---\nFECHA: {fecha_hora}\nCLIENTE: {cliente['nombre']}\n"

    try:
        # Descontar Inventario
        for item in carrito:
            producto = db.session.get(Producto, item['id'])
            if not producto or producto.existencia < item['cantidad']:
                return jsonify({'success': False, 'message': f'Stock insuficiente: {item["nombre"]}'}), 400
            
            producto.existencia -= item['cantidad']
            ticket += f"{item['cantidad']}x {producto.nombre} (${item['precio']})\n"

        ticket += f"TOTAL: {total}\n------------------"
        db.session.commit()
        
        # Enviar a n8n (Telegram)
        try:
            payload_n8n = {
                "cliente": cliente,
                "productos": carrito,
                "total": total,
                "fecha": fecha_hora
            }
            requests.post(N8N_WEBHOOK_URL, json=payload_n8n, timeout=2)
            print(f"✅ Enviado a n8n: {N8N_WEBHOOK_URL}")
        except Exception as e_n8n:
            print(f"⚠️ Falló n8n: {str(e_n8n)}")

        return jsonify({'success': True, 'ticket': ticket})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

# --- RUTAS DE ADMINISTRACIÓN ---
@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    if request.method == 'POST':
        tipo_form = request.form.get('tipo_form')
        if tipo_form == 'categoria':
            nombre = request.form.get('nombre_cat')
            if nombre:
                db.session.add(Categoria(nombre=nombre))
                db.session.commit()
        elif tipo_form == 'subcategoria':
            nombre = request.form.get('nombre_sub')
            cat_id = request.form.get('categoria_id')
            if nombre and cat_id:
                db.session.add(SubCategoria(nombre=nombre, categoria_id=int(cat_id)))
                db.session.commit()
        elif tipo_form == 'producto':
            nombre = request.form.get('nombre')
            precio = float(request.form.get('precio'))
            existencia = int(request.form.get('existencia'))
            sub_id = int(request.form.get('subcategoria_id'))
            filename = 'default.png'
            if 'imagen' in request.files:
                file = request.files['imagen']
                if file and file.filename != '' and allowed_file(file.filename):
                    filename = secure_filename(f"{datetime.now().strftime('%H%M%S')}_{file.filename}")
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            nuevo = Producto(nombre=nombre, precio=precio, existencia=existencia, subcategoria_id=sub_id, imagen_filename=filename)
            db.session.add(nuevo)
            db.session.commit()
        return redirect(url_for('admin'))
    categorias = Categoria.query.all()
    subcategorias = SubCategoria.query.all()
    productos = Producto.query.all()
    return render_template('admin.html', categorias=categorias, subcategorias=subcategorias, productos=productos)

@app.route('/admin/borrar_categoria/<int:id>')
@login_required
def borrar_categoria(id):
    cat = db.session.get(Categoria, id)
    if cat: db.session.delete(cat); db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/borrar_subcategoria/<int:id>')
@login_required
def borrar_subcategoria(id):
    sub = db.session.get(SubCategoria, id)
    if sub: db.session.delete(sub); db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/borrar_producto/<int:id>')
@login_required
def borrar_producto(id):
    p = db.session.get(Producto, id)
    if p:
        if p.imagen_filename != 'default.png':
            ruta = os.path.join(app.config['UPLOAD_FOLDER'], p.imagen_filename)
            if os.path.exists(ruta): 
                try: os.remove(ruta) 
                except: pass
        db.session.delete(p); db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/actualizar_stock/<int:id>', methods=['POST'])
@login_required
def actualizar_stock(id):
    p = db.session.get(Producto, id)
    if p: p.existencia = int(request.form.get('existencia')); db.session.commit()
    return redirect(url_for('admin'))

if __name__ == '__main__':
    with app.app_context():
        if not os.path.exists(UPLOAD_FOLDER): os.makedirs(UPLOAD_FOLDER)
        db.create_all()
    app.run(debug=True, host='0.0.0.0')