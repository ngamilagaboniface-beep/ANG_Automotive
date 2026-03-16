import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename

basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__, static_folder='Static')
app.config['SECRET_KEY'] = 'ang_premium_2026_clean'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'ang_auto.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Image Upload Config
UPLOAD_FOLDER = os.path.join(basedir, 'Static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- MODELS ---
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    type = db.Column(db.String(20), nullable=False) # 'Car' or 'Part'
    category = db.Column(db.String(100))
    price = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text)
    image_file = db.Column(db.String(100), default='default.jpg')

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    date_ordered = db.Column(db.DateTime, default=datetime.utcnow)
    product = db.relationship('Product', backref='orders')

class User(UserMixin):
    def __init__(self, id): self.id = id

@login_manager.user_loader
def load_user(user_id): return User(user_id)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- ROUTES ---
@app.route('/')
def home():
    search = request.args.get('q')
    category = request.args.get('cat')
    max_price = request.args.get('price_max')
    item_type = request.args.get('type')

    query = Product.query
    if search: query = query.filter(Product.name.ilike(f"%{search}%"))
    if category: query = query.filter(Product.category == category)
    if item_type: query = query.filter(Product.type == item_type)
    if max_price and max_price.isdigit(): query = query.filter(Product.price <= int(max_price))

    return render_template('index.html', products=query.all())

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('password') == 'ANG2026':
            login_user(User(1))
            flash('Logged in successfully.', 'success')
            return redirect(url_for('admin_dashboard'))
        flash('Access Denied', 'danger')
    return render_template('login.html')

@app.route('/admin')
@login_required
def admin_dashboard():
    orders = Order.query.order_by(Order.date_ordered.desc()).all()
    products = Product.query.all()
    total_rev = sum([o.product.price for o in orders if o.product])
    return render_template('admin.html', orders=orders, products=products, total_rev=total_rev)

@app.route('/admin/add', methods=['POST'])
@login_required
def add_item():
    name = request.form.get('name')
    item_type = request.form.get('type')
    category = request.form.get('category')
    price_str = request.form.get('price')
    desc = request.form.get('desc')
    
    if not name or not item_type or not price_str:
        flash('Name, type, and price are required.', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    try:
        price = int(price_str)
    except ValueError:
        flash('Price must be a valid number.', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    file = request.files.get('image_file')
    filename = 'default.jpg'
    
    if file and allowed_file(file.filename):
        filename = secure_filename(f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    new_item = Product(
        name=name,
        type=item_type,
        category=category,
        price=price,
        description=desc,
        image_file=filename
    )
    try:
        db.session.add(new_item)
        db.session.commit()
        flash('Product added successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error adding product.', 'danger')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete/<int:product_id>', methods=['POST'])
@login_required
def delete_item(product_id):
    item = Product.query.get_or_404(product_id)
    if item.image_file != 'default.jpg':
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], item.image_file))
        except OSError:
            pass  # File might not exist or permission issue
    try:
        db.session.delete(item)
        db.session.commit()
        flash('Product deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting product.', 'danger')
    return redirect(url_for('admin_dashboard'))

@app.route('/order/<int:product_id>', methods=['POST'])
def place_order(product_id):
    name = request.form.get('name')
    phone = request.form.get('phone')
    
    if not name or not phone:
        flash('Name and phone are required.', 'danger')
        return redirect(url_for('home'))
    
    new_order = Order(
        customer_name=name, 
        phone=phone, 
        product_id=product_id
    )
    try:
        db.session.add(new_order)
        db.session.commit()
        flash("Order sent to ANG Automotive!", "success")
    except Exception as e:
        db.session.rollback()
        flash('Error placing order.', 'danger')
    return redirect(url_for('home'))

if __name__ == '__main__':
    with app.app_context(): db.create_all()
    app.run(debug=True)