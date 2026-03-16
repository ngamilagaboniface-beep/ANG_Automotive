import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'ANG_PRO_2026_KEY')

# Database Config
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'ang_auto.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- MODELS ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

class Part(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Float, nullable=False)
    image_url = db.Column(db.String(500))

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_phone = db.Column(db.String(20), nullable=False)
    item_name = db.Column(db.String(100), nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default="Pending")
    date_ordered = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        db.session.add(User(username='admin', password='ANG2026_Admin'))
        db.session.commit()

# --- ROUTES ---
@app.route('/')
def index():
    parts = Part.query.all()
    categories = db.session.query(Part.category).distinct().all()
    return render_template('index.html', parts=parts, categories=[c[0] for c in categories])

@app.route('/checkout/<int:part_id>', methods=['POST'])
def checkout(part_id):
    part = Part.query.get_or_404(part_id)
    new_order = Order(
        customer_name=request.form.get('customer_name'),
        customer_phone=request.form.get('customer_phone'),
        item_name=part.name,
        total_price=part.price
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
    parts = Part.query.all()
    orders = Order.query.order_by(Order.date_ordered.desc()).all()
    return render_template('admin.html', parts=parts, orders=orders)

@app.route('/add_part', methods=['POST'])
@login_required
def add_part():
    new_part = Part(
        name=request.form.get('name'),
        category=request.form.get('category'),
        price=float(request.form.get('price')),
        image_url=request.form.get('image_url')
    )
    db.session.add(new_part)
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/delete_part/<int:id>')
@login_required
def delete_part(id):
    part = Part.query.get_or_404(id)
    db.session.delete(part)
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
