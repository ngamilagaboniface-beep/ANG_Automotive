import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime
import cloudinary
import cloudinary.uploader

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'ANG_PREMIUM_2026')

# Cloudinary Setup
cloudinary.config(
  cloud_name = os.environ.get('CLOUDINARY_NAME'),
  api_key = os.environ.get('CLOUDINARY_API_KEY'),
  api_secret = os.environ.get('CLOUDINARY_API_SECRET')
)

# Database Setup
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'ang_auto.db')
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- MODELS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

class Car(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    brand = db.Column(db.String(50)) # Added Brand
    model = db.Column(db.String(100))
    price = db.Column(db.Float)
    specs = db.Column(db.Text)
    image_url = db.Column(db.String(500))

class Part(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    category = db.Column(db.String(50)) # Added Category (e.g., Engine, Suspension)
    price = db.Column(db.Float)
    image_url = db.Column(db.String(500))

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100))
    customer_phone = db.Column(db.String(20))
    item_name = db.Column(db.String(100))
    total_price = db.Column(db.Float)
    date_ordered = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(id): return User.query.get(int(id))

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        db.session.add(User(username='admin', password='ANG2026_Admin'))
        db.session.commit()

# --- ROUTES ---
@app.route('/')
def index():
    search = request.args.get('search')
    brand = request.args.get('brand')
    category = request.args.get('category')

    car_query = Car.query
    part_query = Part.query

    if search:
        car_query = car_query.filter(Car.model.contains(search))
        part_query = part_query.filter(Part.name.contains(search))
    if brand:
        car_query = car_query.filter_by(brand=brand)
    if category:
        part_query = part_query.filter_by(category=category)

    # Get unique lists for the menu filters
    all_brands = db.session.query(Car.brand).distinct().all()
    all_cats = db.session.query(Part.category).distinct().all()

    return render_template('index.html', 
                           cars=car_query.all(), 
                           parts=part_query.all(),
                           brands=[b[0] for b in all_brands if b[0]],
                           categories=[c[0] for c in all_cats if c[0]])

@app.route('/checkout/<type>/<int:id>', methods=['POST'])
def checkout(type, id):
    item = Car.query.get(id) if type == 'car' else Part.query.get(id)
    new_order = Order(
        customer_name=request.form.get('customer_name'),
        customer_phone=request.form.get('customer_phone'),
        item_name=getattr(item, 'model', getattr(item, 'name', 'Item')),
        total_price=item.price
    )
    db.session.add(new_order)
    db.session.commit()
    return render_template('billing.html', order=new_order)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.password == request.form.get('password'):
            login_user(user)
            return redirect(url_for('admin_dashboard'))
    return render_template('login.html')

@app.route('/admin')
@login_required
def admin_dashboard():
    return render_template('admin.html', orders=Order.query.order_by(Order.date_ordered.desc()).all())

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    file = request.files['file']
    item_type = request.form.get('type')
    upload_result = cloudinary.uploader.upload(file)
    img_url = upload_result['secure_url']
    
    if item_type == 'car':
        new_item = Car(brand=request.form.get('brand'), model=request.form.get('name'), 
                       price=float(request.form.get('price')), specs=request.form.get('desc'), image_url=img_url)
    else:
        new_item = Part(name=request.form.get('name'), category=request.form.get('cat'), 
                        price=float(request.form.get('price')), image_url=img_url)
    
    db.session.add(new_item)
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
