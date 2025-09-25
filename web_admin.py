from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_login import LoginManager, UserMixin, login_required, login_user, logout_user
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Замени на случайный ключ

# Конфигурация
DATABASE = 'neterror_bot.db'
ADMIN_IDS = [1929149706]  # Твои ID админов

# Настройка логина
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


class User(UserMixin):
    def __init__(self, id):
        self.id = id


@login_manager.user_loader
def load_user(user_id):
    return User(int(user_id))


# Проверка доступа
def is_admin(user_id):
    return user_id in ADMIN_IDS


# База данных
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# Маршруты
@app.route('/')
@login_required
def index():
    conn = get_db_connection()

    # Статистика
    stats = conn.execute('''
        SELECT 
            (SELECT COUNT(*) FROM users) as total_users,
            (SELECT SUM(balance) FROM users) as total_balance,
            (SELECT COUNT(*) FROM orders) as total_orders,
            (SELECT COUNT(*) FROM orders WHERE status = "completed") as completed_orders,
            (SELECT COUNT(*) FROM orders WHERE status = "pending") as pending_orders,
            (SELECT COUNT(*) FROM payment_keys WHERE used = 0) as active_keys
    ''').fetchone()

    # Последние заказы
    orders = conn.execute('''
        SELECT o.*, u.username 
        FROM orders o 
        LEFT JOIN users u ON o.user_id = u.user_id 
        ORDER BY o.order_id DESC 
        LIMIT 10
    ''').fetchall()

    conn.close()

    return render_template('index.html', stats=stats, orders=orders)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_id = int(request.form['user_id'])
        if is_admin(user_id):
            user = User(user_id)
            login_user(user)
            return redirect(url_for('index'))
        else:
            return "Access Denied", 403
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/users')
@login_required
def users():
    conn = get_db_connection()
    users = conn.execute('SELECT * FROM users ORDER BY balance DESC').fetchall()
    conn.close()
    return render_template('users.html', users=users)


@app.route('/orders')
@login_required
def orders():
    status = request.args.get('status', 'all')
    conn = get_db_connection()

    if status == 'all':
        orders = conn.execute('''
            SELECT o.*, u.username 
            FROM orders o 
            LEFT JOIN users u ON o.user_id = u.user_id 
            ORDER BY o.order_id DESC
        ''').fetchall()
    else:
        orders = conn.execute('''
            SELECT o.*, u.username 
            FROM orders o 
            LEFT JOIN users u ON o.user_id = u.user_id 
            WHERE o.status = ? 
            ORDER BY o.order_id DESC
        ''', (status,)).fetchall()

    conn.close()
    return render_template('orders.html', orders=orders, status=status)


@app.route('/keys')
@login_required
def keys():
    conn = get_db_connection()
    keys = conn.execute('SELECT * FROM payment_keys ORDER BY used, rowid DESC').fetchall()
    conn.close()
    return render_template('keys.html', keys=keys)


@app.route('/api/complete_order/<int:order_id>', methods=['POST'])
@login_required
def complete_order(order_id):
    conn = get_db_connection()
    conn.execute('UPDATE orders SET status = "completed", admin_id = ? WHERE order_id = ?',
                 (session['user_id'], order_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/generate_key', methods=['POST'])
@login_required
def generate_key():
    amount = int(request.json['amount'])

    import random
    import string
    key = f"AEGIS-{''.join(random.choices(string.ascii_uppercase + string.digits, k=12))}"

    conn = get_db_connection()
    conn.execute('INSERT INTO payment_keys (key, amount, created_by) VALUES (?, ?, ?)',
                 (key, amount, session['user_id']))
    conn.commit()
    conn.close()

    return jsonify({'success': True, 'key': key})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)