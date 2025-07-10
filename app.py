# app.py (Versi Final dengan Ingat Saya & Lupa Password)

import os
import uuid
import psycopg2
import psycopg2.extras
import logging
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
from flask_cors import CORS
from dotenv import load_dotenv
import google.generativeai as genai
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
import bcrypt
# --- TAMBAHAN UNTUK LUPA PASSWORD ---
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer as Serializer
# ------------------------------------

# --- Konfigurasi Awal & Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
load_dotenv()

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'kunci-rahasia-wajib-diisi')

# --- TAMBAHAN UNTUK LUPA PASSWORD ---
# Konfigurasi email, ambil dari file .env
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
mail = Mail(app)
# ------------------------------------

# --- Koneksi Database ---
DATABASE_URL = os.getenv("POSTGRES_URL")
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        return conn
    except Exception as e:
        logging.exception("Gagal terhubung ke database Postgres.")
        raise

# --- Konfigurasi Flask-Login ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, email):
        self.id = id
        self.email = email

    # --- TAMBAHAN UNTUK LUPA PASSWORD ---
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
        
        # Ambil data user dari DB untuk verifikasi
        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT id, email FROM users WHERE id = %s", (user_id,))
                user_data = cur.fetchone()
                if user_data:
                    return User(id=user_data[0], email=user_data[1])
            return None
        finally:
            if conn: conn.close()
    # ------------------------------------

@login_manager.user_loader
def load_user(user_id):
    # ... (kode ini tidak berubah) ...
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT id, email FROM users WHERE id = %s", (user_id,))
            user_data = cur.fetchone()
            if user_data:
                return User(id=user_data[0], email=user_data[1])
        return None
    finally:
        if conn: conn.close()


# --- Konfigurasi AI Gemini (tidak berubah) ---
# ... (kode AI Gemini Anda di sini) ...
try:
    api_key = os.getenv("GOOGLE_API_KEY")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
    logging.info("Model AI Google Gemini berhasil dikonfigurasi.")
except Exception as e:
    model = None
    logging.exception(f"Error saat konfigurasi AI Google Gemini: {e}")

briefing_user = """... (Isi briefing Anda di sini, sama seperti sebelumnya) ..."""
briefing_model = "Siap, saya mengerti. Nama saya Richatz.AI v1.0 SPRO..."


# === ROUTES APLIKASI ===

@app.route('/')
@login_required
def home():
    return render_template('index.html')

# --- ROUTES AUTENTIKASI (DENGAN PENAMBAHAN LUPA PASSWORD) ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        # PERBAIKAN UNTUK "INGAT SAYA"
        remember = True if request.form.get('remember') else False
        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT id, email, password_hash FROM users WHERE email = %s", (email,))
                user_data = cur.fetchone()

            if user_data and bcrypt.checkpw(password.encode('utf-8'), user_data[2].encode('utf-8')):
                user = User(id=user_data[0], email=user_data[1])
                # PERBAIKAN UNTUK "INGAT SAYA"
                login_user(user, remember=remember)
                logging.info(f"User {email} berhasil login.")
                # Arahkan ke halaman selanjutnya jika ada
                next_page = request.form.get('next')
                return redirect(next_page or url_for('home'))
            else:
                logging.warning(f"Gagal login untuk user {email}.")
                flash('Email atau password salah.', 'danger')
        finally:
            if conn: conn.close()

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    # ... (kode register tidak berubah) ...
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cur:
                cur.execute("INSERT INTO users (email, password_hash) VALUES (%s, %s)", (email, hashed_password.decode('utf-8')))
            conn.commit()
            logging.info(f"User baru terdaftar: {email}")
            flash('Registrasi berhasil! Silakan login.', 'success')
            return redirect(url_for('login'))
        except psycopg2.IntegrityError:
            flash('Email sudah terdaftar.', 'warning')
        finally:
            if conn: conn.close()
    
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- TAMBAHAN UNTUK LUPA PASSWORD ---
def send_reset_email(user):
    token = user.get_reset_token()
    msg = Message('Permintaan Reset Password - Richatz.AI',
                  sender=('Richatz.AI', app.config['MAIL_USERNAME']),
                  recipients=[user.email])
    msg.body = f'''Untuk mereset password Anda, kunjungi link berikut (valid selama 30 menit):
{url_for('reset_token', token=token, _external=True)}

Jika Anda tidak merasa meminta ini, abaikan saja email ini.
'''
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
            flash('Jika email terdaftar, instruksi reset password telah dikirim.', 'info')
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
        flash('Token tidak valid atau sudah kedaluwarsa.', 'warning')
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
            flash('Password Anda telah diubah! Silakan login.', 'success')
            return redirect(url_for('login'))
        finally:
            if conn: conn.close()
    return render_template('reset_token.html')
# ------------------------------------

# --- ROUTES CHAT (tidak berubah) ---
# ... (Semua route chat Anda: /new_chat, /ask, /history, dll. tetap sama) ...
# ... (Salin semua route chat Anda dari file lama ke sini) ...
@app.route('/new_chat', methods=['POST'])
@login_required # Tambahkan decorator ini
def new_chat():
    conn = None
    try:
        conversation_id = str(uuid.uuid4())
        title = "Percakapan Baru"
        conn = get_db_connection()
        with conn.cursor() as cur:
            # PENTING: Tambahkan user_id saat membuat percakapan baru
            cur.execute('INSERT INTO conversations (id, title, user_id) VALUES (%s, %s, %s)', 
                        (conversation_id, title, current_user.id))
        conn.commit()
        logging.info(f"Percakapan baru dibuat: {conversation_id} untuk user {current_user.id}")
        return jsonify({'conversation_id': conversation_id})
    except Exception as e:
        logging.exception(f"Error saat membuat chat baru: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if conn: conn.close()

@app.route('/ask', methods=['POST'])
@login_required # Tambahkan decorator ini
def ask_ai():
    data = request.get_json()
    conversation_id, user_prompt = data.get('conversation_id'), data.get('prompt')
    if not all([conversation_id, user_prompt]):
        return jsonify({'error': 'ID atau prompt tidak ada.'}), 400

    if model is None:
        return jsonify({'answer': "Maaf, model AI belum terkonfigurasi."}), 500

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            # VERIFIKASI: Pastikan conversation ini milik user yang sedang login
            cur.execute("SELECT user_id FROM conversations WHERE id = %s", (conversation_id,))
            owner_id = cur.fetchone()
            if not owner_id or owner_id[0] != current_user.id:
                return jsonify({'error': 'Akses ditolak'}), 403
            
            cur.execute("SELECT role, content FROM messages WHERE conversation_id = %s ORDER BY timestamp ASC", (conversation_id,))
            db_history = cur.fetchall()
            history_for_ai = [
                {"role": 'user', "parts": [briefing_user]},
                {"role": 'model', "parts": [briefing_model]}
            ]
            history_for_ai.extend([{"role": ('model' if role in ['assistant', 'model'] else 'user'), "parts": [content]} for role, content in db_history])

            chat = model.start_chat(history=history_for_ai)
            response = chat.send_message(user_prompt)
            ai_answer = response.text

            cur.execute('INSERT INTO messages (conversation_id, role, content) VALUES (%s, %s, %s)', (conversation_id, 'user', user_prompt))
            cur.execute('INSERT INTO messages (conversation_id, role, content) VALUES (%s, %s, %s)', (conversation_id, 'assistant', ai_answer))

            cur.execute("SELECT count(*) FROM messages WHERE conversation_id = %s AND role = 'user'", (conversation_id,))
            user_message_count = cur.fetchone()[0]
            
            if user_message_count == 1: 
                cur.execute("UPDATE conversations SET title = %s WHERE id = %s", (user_prompt[:50], conversation_id))
        conn.commit()
        return jsonify({'answer': ai_answer})
    except Exception as e:
        logging.exception(f"Error di /ask: {e}")
        return jsonify({'answer': f"Maaf, terjadi kesalahan: {e}"}), 500
    finally:
        if conn: conn.close()

@app.route('/history', methods=['GET'])
@login_required # Tambahkan decorator ini
def get_history():
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # PENTING: Ambil history HANYA untuk user yang sedang login
            cur.execute("SELECT id, title FROM conversations WHERE user_id = %s ORDER BY timestamp DESC", (current_user.id,))
            conversations = cur.fetchall()
        logging.info(f"Riwayat percakapan untuk user {current_user.id} berhasil diambil.")
        return jsonify(conversations)
    except Exception as e:
        logging.exception(f"Error saat mengambil riwayat: {e}")
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
            owner_id = cur.fetchone()
            if not owner_id or owner_id['user_id'] != current_user.id:
                return jsonify({'error': 'Akses ditolak'}), 403
            
            cur.execute("SELECT role, content FROM messages WHERE conversation_id = %s AND role IN ('user', 'assistant') ORDER BY timestamp ASC", (conversation_id,))
            messages = cur.fetchall()
        return jsonify(messages or [])
    except Exception as e:
        logging.exception(f"Error mengambil percakapan: {e}")
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
                logging.info(f"Percakapan {conversation_id} berhasil dihapus oleh user {current_user.id}.")
                return jsonify({'status': 'success'})
            else:
                logging.warning(f"User {current_user.id} mencoba menghapus percakapan {conversation_id} yang bukan miliknya.")
                return jsonify({'status': 'error', 'message': 'Percakapan tidak ditemukan atau akses ditolak'}), 404
    except Exception as e:
        logging.exception(f"Error menghapus percakapan: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        if conn: conn.close()

# --- Main Execution ---
if __name__ == '__main__':
    app.run(debug=True, port=5000)