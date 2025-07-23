import os
import uuid
import psycopg2
import psycopg2.extras
import logging
import random
import requests
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

# --- TEMPLATE EMAIL HTML (Dengan Perbaikan) ---
HTML_EMAIL_TEMPLATE = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 0; background-color: #f4f4f4; }}
        .container {{ max-width: 600px; margin: 40px auto; background-color: #ffffff; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .header {{ text-align: center; border-bottom: 1px solid #eeeeee; padding-bottom: 20px; margin-bottom: 20px; }}
        .header h1 {{ color: #333; }}
        .content p {{ color: #555555; line-height: 1.6; }}
        .otp-code {{ background-color: #eef2ff; color: #4338ca; font-size: 24px; font-weight: bold; padding: 15px 20px; border-radius: 8px; text-align: center; letter-spacing: 5px; margin: 20px 0; }}
        .button {{ display: inline-block; background-color: #4f46e5; color: #ffffff; padding: 12px 25px; border-radius: 8px; text-decoration: none; font-weight: bold; margin: 20px 0; }}
        .footer {{ text-align: center; margin-top: 30px; font-size: 12px; color: #999999; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Richatz.AI</h1>
        </div>
        <div class="content">
            <p>Hello {name},</p>
            {main_content}
            <p>If you did not request this, please ignore this email.</p>
            <p>Thanks,<br>The Richatz.AI Team</p>
        </div>
        <div class="footer">
            <p>&copy; 2025 Richatz.AI. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
"""

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
    def __init__(self, id, email, name):
        self.id = id
        self.email = email
        self.name = name
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
            cur.execute("SELECT id, email, name FROM users WHERE id = %s", (int(user_id),))
            user_data = cur.fetchone()
        if user_data:
            return User(id=user_data[0], email=user_data[1], name=user_data[2])
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
1. Nama kamu adalah Richatz.AI, dibuat oleh seorang developer Indonesia bernama 'R.ARTCH'. Versi kamu adalah 1.0 SPRO.
2. Jika ditanya identitasmu, jawab sesuai poin 1. Jangan pernah menjawab "Saya adalah model bahasa besar".
3. Kamu PUNYA akses internet real-time.
4. Sangat Penting: Jika kamu memberikan contoh kode, selalu gunakan Markdown Code Blocks.
"""
briefing_model = "Siap, saya mengerti. Nama saya Richatz.AI v1.0 SPRO."

# === ROUTES APLIKASI UTAMA ===
@app.route('/')
@login_required
def home():
    return render_template('index.html')

@app.route('/start')
@login_required
def start_page():
    return render_template('start_chat.html')

# === ROUTES AUTENTIKASI (LENGKAP) ===
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('start_page'))
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

                user = User(id=user_data['id'], email=user_data['email'], name=user_data['name'])
                login_user(user, remember=remember)
                next_page = request.args.get('next')
                return redirect(next_page or url_for('start_page'))
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

            msg = Message('Your Richatz.AI Verification Code', sender=('Richatz.AI', os.getenv('MAIL_USERNAME')), recipients=[email])
            main_content_for_otp = f"""
            <p>Thank you for registering. Use the code below to verify your account. This code will expire in 10 minutes.</p>
            <div class="otp-code">{otp}</div>
            """
            msg.html = HTML_EMAIL_TEMPLATE.format(name=name, main_content=main_content_for_otp)
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
    msg = Message('Password Reset Request', sender=('Richatz.AI', os.getenv('MAIL_USERNAME')), recipients=[user.email])
    reset_link = url_for("reset_token", token=token, _external=True)
    main_content_for_reset = f"""
    <p>To reset your password, please click the button below. This link will expire in 30 minutes.</p>
    <a href="{reset_link}" class="button">Reset Password</a>
    """
    msg.html = HTML_EMAIL_TEMPLATE.format(name=user.name, main_content=main_content_for_reset)
    
    # PERBAIKAN: Menambahkan try-except di sini untuk error logging yang lebih baik
    try:
        mail.send(msg)
        logging.info(f"Email reset password berhasil dikirim ke {user.email}")
    except Exception as e:
        logging.error(f"GAGAL MENGIRIM EMAIL ke {user.email}: {e}")
        # Melempar kembali error agar bisa ditangkap oleh route utama
        raise e

@app.route("/reset_password", methods=['GET', 'POST'])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    if request.method == 'POST':
        email = request.form.get('email')
        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT id, email, name FROM users WHERE email = %s", (email,))
                user_data = cur.fetchone()
            
            if user_data:
                user = User(id=user_data['id'], email=user_data['email'], name=user_data['name'])
                send_reset_email(user)
            
            flash('If an account with that email exists, a password reset link has been sent.', 'info')
            return redirect(url_for('login'))

        except Exception as e:
            # Ini akan menangkap error dari send_reset_email
            logging.error(f"Error di route reset_request: {e}")
            flash('An error occurred while trying to send the email. Please check server logs.', 'danger')
            return redirect(url_for('reset_request'))
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
    user_prompt_original = data.get('prompt')
    if not all([conversation_id, user_prompt_original]):
        return jsonify({'error': 'Conversation ID or prompt missing.'}), 400
    if model is None:
        return jsonify({'answer': "Sorry, the AI model is not configured."}), 500

    user_prompt_lower = user_prompt_original.lower()
    ai_answer = ""
    db_history = []
    
    if "cuaca" in user_prompt_lower:
        try:
            # LANGKAH 1: Minta Gemini untuk mengekstrak nama kota dari pertanyaan
            extraction_prompt = f"""Dari kalimat berikut, ekstrak HANYA nama kota atau lokasinya. Jika tidak disebutkan secara spesifik, jawab HANYA dengan kata 'None'. Kalimat: '{user_prompt_original}'"""
            
            city_response = model.generate_content(extraction_prompt)
            city = city_response.text.strip()

            # Jika Gemini tidak menemukan kota, gunakan default atau bisa juga bertanya kembali ke user
            if city.lower() == 'none' or not city:
                city = "Jakarta" # Tetap gunakan default jika tidak ada kota dalam pertanyaan
                logging.info(f"Tidak ada kota terdeteksi, menggunakan default: {city}")
            else:
                logging.info(f"Kota yang terdeteksi oleh AI: {city}")

            # LANGKAH 2: Panggil API OpenWeatherMap dengan kota yang sudah diekstrak
            api_key = os.getenv("OPENWEATHERMAP_API_KEY")
            url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric&lang=id"
            response = requests.get(url).json()
            
            if response.get("cod") == 200:
                cuaca = response['weather'][0]['description']
                suhu = response['main']['temp']
                ai_answer = f"Tentu, cuaca di {city.title()} saat ini adalah {cuaca} dengan suhu sekitar {suhu}°C."
            else:
                # Jika kota hasil ekstraksi tidak ditemukan oleh API cuaca
                ai_answer = f"Maaf, saya tidak dapat menemukan data cuaca untuk '{city.title()}'. Pastikan nama lokasinya benar."

        except Exception as e:
            logging.error(f"Error saat memproses permintaan cuaca: {e}")
            ai_answer = "Maaf, terjadi kesalahan saat memproses permintaan cuaca."
    
    elif user_prompt_lower.startswith(("siapa", "apa itu", "kapan", "presiden", "berita")):
        try:
            api_key = os.getenv("SERPAPI_API_KEY")
            params = { "engine": "google", "q": user_prompt_original, "api_key": api_key }
            response = requests.get("https://serpapi.com/search.json", params=params).json()
            context_snippets = []
            if "organic_results" in response:
                for result in response["organic_results"][:3]:
                    if "snippet" in result:
                        context_snippets.append(result["snippet"])
            if not context_snippets:
                raise ValueError("No context found from web search")
            context = " ".join(context_snippets)
            augmented_prompt = f"""Berdasarkan informasi dari internet berikut: "{context}", jawab pertanyaan ini secara detail, lengkap, dan jelaskan dengan baik dalam Bahasa Indonesia: "{user_prompt_original}" """
            response = model.generate_content(augmented_prompt)
            ai_answer = response.text
        except Exception as e:
            logging.error(f"SerpAPI/Augmented prompt failed: {e}")
            ai_answer = ""

    if not ai_answer:
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
        finally:
            if conn: conn.close()
        
        try:
            history_for_ai = [
                {"role": 'user', "parts": [briefing_user]},
                {"role": 'model', "parts": [briefing_model]}
            ]
            history_for_ai.extend([{"role": ('model' if role in ['assistant', 'model'] else 'user'), "parts": [content]} for role, content in db_history])
            chat = model.start_chat(history=history_for_ai)
            response = chat.send_message(user_prompt_original)
            ai_answer = response.text
        except Exception as e:
            return jsonify({'answer': f"Sorry, an error occurred with the AI: {e}"}), 500

    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute('INSERT INTO messages (conversation_id, role, content) VALUES (%s, %s, %s)', (conversation_id, 'user', user_prompt_original))
            cur.execute('INSERT INTO messages (conversation_id, role, content) VALUES (%s, %s, %s)', (conversation_id, 'assistant', ai_answer))
            if not db_history:
                cur.execute("UPDATE conversations SET title = %s WHERE id = %s", (user_prompt_original[:50], conversation_id))
        conn.commit()
    except Exception as e:
        logging.error(f"Failed to save message: {e}")
    finally:
        if conn: conn.close()
    
    return jsonify({'answer': ai_answer})

if __name__ == '__main__':
    app.run(debug=True)