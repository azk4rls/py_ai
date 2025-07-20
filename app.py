import os
import uuid
import psycopg2
import psycopg2.extras
import logging
import random
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
from dotenv import load_dotenv
import google.generativeai as genai
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
import bcrypt
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer as Serializer

# --- Konfigurasi Awal & Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

# Konfigurasi Email
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
mail = Mail(app)

# --- Koneksi Database ---
DATABASE_URL = os.getenv("POSTGRES_URL")
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        return conn
    except Exception as e:
        logging.exception("Gagal terhubung ke database Postgres.")
        raise

# --- Konfigurasi Sistem Login ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, email):
        self.id = id
        self.email = email
    def get_reset_token(self):
        s = Serializer(app.config['SECRET_KEY'])
        return s.dumps({'user_id': self.id})
    @staticmethod
    def verify_reset_token(token, expires_sec=1800):
        s = Serializer(app.config['SECRET_KEY'])
        try:
            user_id = s.loads(token, max_age=expires_sec)['user_id']
        except:
            return None
        return load_user(user_id)

@login_manager.user_loader
def load_user(user_id):
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT id, email FROM users WHERE id = %s", (int(user_id),))
            user_data = cur.fetchone()
        if user_data:
            return User(id=user_data[0], email=user_data[1])
        return None
    finally:
        if conn: conn.close()

# --- Konfigurasi AI Gemini ---
try:
    api_key = os.getenv("GOOGLE_API_KEY")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    model = None
    logging.error(f"Error Konfigurasi Gemini: {e}")

briefing_user = """
PERATURAN UTAMA DAN IDENTITAS DIRI ANDA:
1. Nama kamu adalah Richatz.AI, dibuat oleh seorang developer Indonesia bernama 'R.AI'. Versi kamu adalah 1.0 SPRO.
2. Jika ditanya identitasmu, jawab sesuai poin 1. Jangan pernah menjawab "Saya adalah model bahasa besar".
3. Kamu TIDAK punya akses internet real-time.
4. Sangat Penting: Jika kamu memberikan contoh kode, selalu gunakan Markdown Code Blocks.
"""
briefing_model = "Siap, saya mengerti. Nama saya Richatz.AI v1.0 SPRO."

# === ROUTES APLIKASI UTAMA ===
@app.route('/')
@login_required
def home():
    return render_template('index.html')

# === ROUTES AUTENTIKASI (LENGKAP) ===
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        remember = 'remember' in request.form
        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE email = %s", (email,))
                user_data = cur.fetchone()
            
            if user_data and bcrypt.checkpw(password.encode('utf-8'), user_data['password_hash'].encode('utf-8')):
                if not user_data['is_verified']:
                    flash('Your account is not verified. Please check your email for the OTP.', 'warning')
                    return redirect(url_for('verify_otp', email=email))

                user = User(id=user_data['id'], email=user_data['email'])
                login_user(user, remember=remember)
                next_page = request.args.get('next')
                return redirect(next_page or url_for('home'))
            else:
                flash('Incorrect email or password.', 'danger')
        finally:
            if conn: conn.close()
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    if request.method == 'POST':
        email = request.form['email']
        name = request.form['name']
        password = request.form['password']
        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE email = %s", (email,))
                user = cur.fetchone()

                if user and user['is_verified']:
                    flash('Email already registered. Please log in.', 'warning')
                    return redirect(url_for('login'))

                otp = "".join([str(random.randint(0, 9)) for _ in range(6)])
                otp_expiry = datetime.now(timezone.utc) + timedelta(minutes=10)
                hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

                if user and not user['is_verified']:
                    cur.execute(
                        "UPDATE users SET name = %s, password_hash = %s, otp = %s, otp_expires_at = %s WHERE email = %s",
                        (name, hashed_password.decode('utf-8'), otp, otp_expiry, email)
                    )
                else:
                    cur.execute(
                        "INSERT INTO users (name, email, password_hash, otp, otp_expires_at, is_verified) VALUES (%s, %s, %s, %s, %s, %s)",
                        (name, email, hashed_password.decode('utf-8'), otp, otp_expiry, False)
                    )
            conn.commit()

            msg = Message('Your Richatz.AI Verification Code', sender=os.getenv('MAIL_USERNAME'), recipients=[email])
            msg.body = f'Hello {name},\n\nYour OTP code is: {otp}\n\nThis code will expire in 10 minutes.'
            mail.send(msg)

            flash('Registration successful! Please check your email for the OTP code.', 'info')
            return redirect(url_for('verify_otp', email=email))
        except Exception as e:
            logging.error(f"Error during registration: {e}")
            flash('An error occurred during registration.', 'danger')
        finally:
            if conn: conn.close()
    return render_template('register.html')

@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    email = request.args.get('email')
    if not email:
        return redirect(url_for('register'))
    if request.method == 'POST':
        otp_from_form = "".join([request.form.get(f'otp{i}', '') for i in range(1, 7)])
        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE email = %s", (email,))
                user = cur.fetchone()

                if not user:
                    flash('Email not found.', 'danger')
                    return redirect(url_for('register'))
                
                if user['otp'] == otp_from_form and user['otp_expires_at'] > datetime.now(timezone.utc):
                    cur.execute(
                        "UPDATE users SET is_verified = TRUE, otp = NULL, otp_expires_at = NULL WHERE email = %s",
                        (email,)
                    )
                    conn.commit()
                    flash('Verification successful! Please log in.', 'success')
                    return redirect(url_for('login'))
                else:
                    flash('Incorrect or expired OTP code.', 'danger')
        finally:
            if conn: conn.close()
    return render_template('verify_otp.html', email=email)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

def send_reset_email(user):
    token = user.get_reset_token()
    msg = Message('Password Reset Request', sender=os.getenv('MAIL_USERNAME'), recipients=[user.email])
    msg.body = f'To reset your password, visit the following link:\n{url_for("reset_token", token=token, _external=True)}'
    mail.send(msg)

@app.route("/reset_password", methods=['GET', 'POST'])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    if request.method == 'POST':
        email = request.form.get('email')
        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT id, email FROM users WHERE email = %s", (email,))
                user_data = cur.fetchone()
            if user_data:
                user = User(id=user_data[0], email=user_data[1])
                send_reset_email(user)
            flash('If the email is registered, password reset instructions have been sent.', 'info')
            return redirect(url_for('login'))
        finally:
            if conn: conn.close()
    return render_template('reset_request.html')

@app.route("/reset_password/<token>", methods=['GET', 'POST'])
def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    user = User.verify_reset_token(token)
    if user is None:
        flash('That is an invalid or expired token.', 'warning')
        return redirect(url_for('reset_request'))
    if request.method == 'POST':
        password = request.form.get('password')
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET password_hash = %s WHERE id = %s", (hashed_password.decode('utf-8'), user.id))
            conn.commit()
            flash('Your password has been updated! You are now able to log in.', 'success')
            return redirect(url_for('login'))
        finally:
            if conn: conn.close()
    return render_template('reset_token.html')


# === ROUTES CHAT API (Lengkap & Aman) ===
@app.route('/history', methods=['GET'])
@login_required
def get_history():
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, title FROM conversations WHERE user_id = %s ORDER BY timestamp DESC", (current_user.id,))
            conversations = cur.fetchall()
        return jsonify(conversations)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/conversation/<conversation_id>', methods=['GET'])
@login_required
def get_conversation(conversation_id):
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT user_id FROM conversations WHERE id = %s", (conversation_id,))
            owner = cur.fetchone()
            if not owner or owner['user_id'] != current_user.id:
                return jsonify({'error': 'Access denied'}), 403
            cur.execute("SELECT role, content FROM messages WHERE conversation_id = %s AND role IN ('user', 'assistant') ORDER BY timestamp ASC", (conversation_id,))
            messages = cur.fetchall()
            return jsonify(messages or [])
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/delete_conversation/<conversation_id>', methods=['DELETE'])
@login_required
def delete_conversation(conversation_id):
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conversations WHERE id = %s AND user_id = %s", (conversation_id, current_user.id))
            conn.commit()
            if cur.rowcount > 0:
                return jsonify({'status': 'success'})
            else:
                return jsonify({'status': 'error', 'message': 'Conversation not found'}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/new_chat', methods=['POST'])
@login_required
def new_chat():
    conn = None
    try:
        conversation_id = str(uuid.uuid4())
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute('INSERT INTO conversations (id, title, user_id) VALUES (%s, %s, %s)', 
                        (conversation_id, "New Conversation", current_user.id))
        conn.commit()
        return jsonify({'conversation_id': conversation_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/ask', methods=['POST'])
@login_required
def ask_ai():
    data = request.get_json()
    conversation_id = data.get('conversation_id')
    user_prompt = data.get('prompt')
    if not all([conversation_id, user_prompt]):
        return jsonify({'error': 'Conversation ID or prompt missing.'}), 400
    if model is None:
        return jsonify({'answer': "Sorry, the AI model is not configured."}), 500
    
    db_history = []
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM conversations WHERE id = %s", (conversation_id,))
            owner = cur.fetchone()
            if not owner or owner[0] != current_user.id:
                return jsonify({'error': 'Access denied'}), 403
            cur.execute("SELECT role, content FROM messages WHERE conversation_id = %s ORDER BY timestamp DESC LIMIT 6", (conversation_id,))
            db_history_reversed = cur.fetchall()
            db_history = list(reversed(db_history_reversed))
    except Exception as e:
        return jsonify({'answer': f"Sorry, failed to retrieve chat history: {e}"}), 500
    finally:
        if conn: conn.close()

    try:
        history_for_ai = [
            {"role": 'user', "parts": [briefing_user]},
            {"role": 'model', "parts": [briefing_model]}
        ]
        history_for_ai.extend([{"role": ('model' if role in ['assistant', 'model'] else 'user'), "parts": [content]} for role, content in db_history])
        chat = model.start_chat(history=history_for_ai)
        response = chat.send_message(user_prompt)
        ai_answer = response.text
    except Exception as e:
        return jsonify({'answer': f"Sorry, an error occurred with the AI: {e}"}), 500

    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute('INSERT INTO messages (conversation_id, role, content) VALUES (%s, %s, %s)', (conversation_id, 'user', user_prompt))
            cur.execute('INSERT INTO messages (conversation_id, role, content) VALUES (%s, %s, %s)', (conversation_id, 'assistant', ai_answer))
            if not db_history:
                cur.execute("UPDATE conversations SET title = %s WHERE id = %s", (user_prompt[:50], conversation_id))
        conn.commit()
    except Exception as e:
        return jsonify({'answer': ai_answer, 'warning': 'Failed to save conversation.'})
    finally:
        if conn: conn.close()

    return jsonify({'answer': ai_answer})

if __name__ == '__main__':
    app.run(debug=True)