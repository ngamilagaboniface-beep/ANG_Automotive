import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user

app = Flask(__name__)

# --- CONFIGURATION ---
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'ANG_AUTO_2026_PRO_KEY')

# Database path configuration (Fixed for Linux/Render)
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

class Car(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    model = db.Column(db.String(100), nullable=False)
    price = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(500), nullable=True) # For car photos

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- DATABASE AUTO-CREATION ---
with app.app_context():
    db.create_all()
    # Create default admin for first-time access
    if not User.query.filter_by(username='admin').first():
        admin_user = User(username='admin', password='ANG2026_Admin') 
        db.session.add(admin_user)
        db.session.commit()

# --- ROUTES ---

@app.route('/')
def index():
    cars = Car.query.all()
    return render_template('index.html', cars=cars)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.password == request.form['password']:
            login_user(user)
            return redirect(url_for('admin_dashboard'))
        flash('Invalid Access Code')
    return render_template('login.html')

@app.route('/admin')
@login_required
def admin_dashboard():
    cars = Car.query.all()
    return render_template('admin.html', cars=cars)

@app.route('/add_car', methods=['POST'])
@login_required
def add_car():
    new_car = Car(
        model=request.form['model'], 
        price=request.form['price'], 
        description=request.form['description'],
        image_url=request.form.get('image_url')
    )
    db.session.add(new_car)
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/delete_car/<int:id>')
@login_required
def delete_car(id):
    car = Car.query.get(id)
    db.session.delete(car)
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
