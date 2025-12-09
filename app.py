import os
from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)

# --- Configuración ---
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tienda.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- MODELOS CON BORRADO EN CASCADA ---

class Categoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False, unique=True)
    # cascade="all, delete-orphan": Si borras la Categoría, se borran sus Subcategorías
    subcategorias = db.relationship('SubCategoria', backref='categoria', lazy=True, cascade="all, delete-orphan")

class SubCategoria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria.id'), nullable=False)
    # cascade="all, delete-orphan": Si borras la Subcategoría, se borran sus Productos
    productos = db.relationship('Producto', backref='subcategoria', lazy=True, cascade="all, delete-orphan")

class Producto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    precio = db.Column(db.Float, nullable=False)
    existencia = db.Column(db.Integer, default=0)
    imagen_filename = db.Column(db.String(150), default='default.png')
    subcategoria_id = db.Column(db.Integer, db.ForeignKey('sub_categoria.id'), nullable=False)

# --- RUTAS PRINCIPALES ---

@app.route('/')
def index():
    categorias = Categoria.query.all()
    return render_template('tienda.html', categorias=categorias, es_home=True)

@app.route('/categoria/<int:sub_id>')
def ver_subcategoria(sub_id):
    subcategoria = db.session.get(SubCategoria, sub_id)
    if not subcategoria: return redirect(url_for('index'))
    categorias = Categoria.query.all()
    return render_template('tienda.html', categorias=categorias, productos=subcategoria.productos, sub_actual=subcategoria, es_home=False)

@app.route('/procesar_pedido', methods=['POST'])
def procesar_pedido():
    data = request.get_json()
    cliente = data.get('cliente')
    carrito = data.get('productos')
    total = data.get('total')

    if not carrito: return jsonify({'success': False, 'message': 'Carrito vacío'}), 400

    fecha_hora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ticket = f"--- PEDIDO NUEVO ---\nFECHA: {fecha_hora}\nCLIENTE: {cliente['nombre']} | {cliente['telefono']}\nDIR: {cliente['direccion']}\n--- ITEMS ---\n"

    try:
        for item in carrito:
            producto = db.session.get(Producto, item['id'])
            if not producto or producto.existencia < item['cantidad']:
                return jsonify({'success': False, 'message': f'Stock insuficiente: {item["nombre"]}'}), 400
            
            producto.existencia -= item['cantidad']
            ticket += f"{item['cantidad']}x {producto.nombre} (${item['precio']}) = ${item['precio']*item['cantidad']}\n"

        ticket += f"TOTAL: {total}\n------------------"
        db.session.commit()
        
        if not os.path.exists('pedidos_txt'): os.makedirs('pedidos_txt')
        archivo = f"pedidos_txt/pedido_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        with open(archivo, 'w', encoding='utf-8') as f: f.write(ticket)
        
        return jsonify({'success': True, 'ticket': ticket})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500

# --- RUTAS ADMIN ---

@app.route('/admin', methods=['GET', 'POST'])
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

# --- NUEVAS RUTAS DE BORRADO ---

@app.route('/admin/borrar_categoria/<int:id>')
def borrar_categoria(id):
    cat = db.session.get(Categoria, id)
    if cat:
        db.session.delete(cat)
        db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/borrar_subcategoria/<int:id>')
def borrar_subcategoria(id):
    sub = db.session.get(SubCategoria, id)
    if sub:
        db.session.delete(sub)
        db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/borrar_producto/<int:id>')
def borrar_producto(id):
    p = db.session.get(Producto, id)
    if p:
        if p.imagen_filename != 'default.png':
            ruta = os.path.join(app.config['UPLOAD_FOLDER'], p.imagen_filename)
            if os.path.exists(ruta): 
                try: os.remove(ruta)
                except: pass
        db.session.delete(p)
        db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/actualizar_stock/<int:id>', methods=['POST'])
def actualizar_stock(id):
    p = db.session.get(Producto, id)
    if p:
        p.existencia = int(request.form.get('existencia'))
        db.session.commit()
    return redirect(url_for('admin'))

if __name__ == '__main__':
    with app.app_context():
        if not os.path.exists(UPLOAD_FOLDER): os.makedirs(UPLOAD_FOLDER)
        db.create_all()
    app.run(debug=True, host='0.0.0.0')