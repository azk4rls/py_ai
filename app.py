# app.py (VERSI FINAL DENGAN PERBAIKAN TIMEOUT)

import os
import uuid
import psycopg2
import psycopg2.extras
import logging
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
    3. Kamu TIDAK punya akses internet real-time. Jika ditanya berita atau cuaca terkini, jawab jujur bahwa kamu tidak tahu. JANGAN MENEBAK.
    4. Sangat Penting: Jika kamu memberikan contoh kode, selalu gunakan Markdown Code Blocks.
"""
briefing_model = "Siap, saya mengerti. Nama saya Richatz.AI v1.0 SPRO."

# === ROUTES APLIKASI ===

@app.route('/')
@login_required
def home():
    return render_template('index.html')

# --- ROUTES AUTENTIKASI ---
# (Register, Login, Logout, Lupa Password) - Tidak ada perubahan di sini
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('home'))
    # ... (kode Anda sebelumnya sudah benar) ...
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('home'))
    # ... (kode Anda sebelumnya sudah benar) ...
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# ... (semua route lupa password Anda sebelumnya sudah benar) ...


# === ROUTES CHAT (DENGAN PERBAIKAN) ===

@app.route('/new_chat', methods=['POST'])
@login_required
def new_chat():
    conn = None
    try:
        conversation_id = str(uuid.uuid4())
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute('INSERT INTO conversations (id, title, user_id) VALUES (%s, %s, %s)', 
                        (conversation_id, "Percakapan Baru", current_user.id))
        conn.commit()
        return jsonify({'conversation_id': conversation_id})
    except Exception as e:
        logging.exception(f"Error saat membuat chat baru: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if conn: conn.close()

# --- 👇 INI ADALAH FUNGSI YANG DIPERBARUI TOTAL 👇 ---
@app.route('/ask', methods=['POST'])
@login_required
def ask_ai():
    data = request.get_json()
    conversation_id = data.get('conversation_id')
    user_prompt = data.get('prompt')

    if not all([conversation_id, user_prompt]):
        return jsonify({'error': 'ID atau prompt tidak ada.'}), 400
    if model is None:
        return jsonify({'answer': "Maaf, model AI belum terkonfigurasi."}), 500

    db_history = []
    conn = None
    
    # LANGKAH 1: Ambil History & Langsung TUTUP KONEKSI
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM conversations WHERE id = %s", (conversation_id,))
            owner_id = cur.fetchone()
            if not owner_id or owner_id[0] != current_user.id:
                return jsonify({'error': 'Akses ditolak'}), 403
            
            cur.execute("SELECT role, content FROM messages WHERE conversation_id = %s ORDER BY timestamp DESC LIMIT 6", (conversation_id,))
            db_history_reversed = cur.fetchall()
            db_history = list(reversed(db_history_reversed))
    except Exception as e:
        logging.exception(f"Error saat mengambil history: {e}")
        return jsonify({'answer': f"Maaf, gagal mengambil riwayat chat: {e}"}), 500
    finally:
        if conn: conn.close()

    # LANGKAH 2: Panggil AI (Tanpa ada koneksi DB yang terbuka)
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
        logging.exception(f"Error saat memanggil AI: {e}")
        return jsonify({'answer': f"Maaf, terjadi kesalahan pada AI: {e}"}), 500

    # LANGKAH 3: BUKA KONEKSI BARU & Simpan Pesan
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute('INSERT INTO messages (conversation_id, role, content) VALUES (%s, %s, %s)', (conversation_id, 'user', user_prompt))
            cur.execute('INSERT INTO messages (conversation_id, role, content) VALUES (%s, %s, %s)', (conversation_id, 'assistant', ai_answer))
            
            # Update judul hanya jika ini adalah pesan pertama (history kosong)
            if not db_history:
                cur.execute("UPDATE conversations SET title = %s WHERE id = %s", (user_prompt[:50], conversation_id))
        conn.commit()
    except Exception as e:
        logging.exception(f"Error saat menyimpan pesan: {e}")
        return jsonify({'answer': ai_answer, 'warning': 'Gagal menyimpan percakapan.'})
    finally:
        if conn: conn.close()

    return jsonify({'answer': ai_answer})

# ... (Route /history, /conversation/<id>, /delete_conversation/<id> Anda sebelumnya sudah benar) ...

if __name__ == '__main__':
    app.run(debug=True)