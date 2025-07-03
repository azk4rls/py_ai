import os
import json
import uuid
import psycopg2
import psycopg2.extras
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
import google.generativeai as genai
import logging

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()
app = Flask(__name__)
CORS(app)

DATABASE_URL = os.getenv("POSTGRES_URL")
if not DATABASE_URL:
    logging.error("Variabel lingkungan POSTGRES_URL tidak ditemukan. Pastikan sudah diatur di file .env")

# --- FUNGSI KONEKSI YANG SUDAH DIPERBAIKI ---
def get_db_connection():
    """Membuat koneksi ke database Postgres dengan metode SSL yang benar."""
    if not DATABASE_URL:
        logging.error("POSTGRES_URL tidak ditemukan di environment variables saat mencoba koneksi database.")
        raise ValueError("POSTGRES_URL tidak ditemukan di environment variables.")

    try:
        # FIX KRUSIAL: sslmode diberikan sebagai parameter terpisah, bukan ditempel di URL.
        # Ini adalah cara yang benar untuk library psycopg2.
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        logging.info("Koneksi database Postgres berhasil dibuat.")
        return conn
    except Exception as e:
        logging.exception(f"Gagal terhubung ke database Postgres. Pastikan POSTGRES_URL benar dan database bisa diakses.")
        raise # Re-raise the exception to propagate it

def init_db():
    conn = None # Inisialisasi conn
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute('''
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
                )
            ''')
        conn.commit()
        logging.info("Database Postgres berhasil diinisialisasi atau tabel sudah ada.")
    except Exception as e:
        logging.exception(f"Error saat menginisialisasi database: {e}")
        raise
    finally:
        if conn:
            conn.close()

try:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logging.error("Variabel lingkungan GOOGLE_API_KEY tidak ditemukan. Pastikan sudah diatur di file .env")
        model = None
    else:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        logging.info("Model AI Google Gemini berhasil dikonfigurasi.")
except Exception as e:
    model = None
    logging.exception(f"Error saat konfigurasi AI Google Gemini: {e}")

# PENTING: UBAH briefing_user INI
briefing_user = """
    PERATURAN UTAMA DAN IDENTITAS DIRI ANDA:
    1. Nama kamu adalah Richatz.AI, dibuat oleh seorang developer Indonesia bernama 'R.AI'. Versi kamu adalah 1.0 SPRO.
    2. Jika ditanya identitasmu, jawab sesuai poin 1. Jangan pernah menjawab "Saya adalah model bahasa besar".
    3. Kamu punya akses internet real-time. Jika ditanya berita atau cuaca terkini, jawab jujur dengan akurat. JANGAN MENEBAK.
    4. Sangat Penting: Jika kamu memberikan contoh kode, selalu gunakan Markdown Code Blocks. Formatnya adalah tiga backticks (```) diikuti nama bahasa (misal: ```python, ```javascript, ```html) di awal, dan tiga backticks lagi (```) di akhir. Contoh:
       ```python
       print("Hello, World!")
       ```
       Contoh HTML:
       ```html
       <!DOCTYPE html>
       <html>
       <body>
           <h1>Judul HTML</h1>
       </body>
       </html>
       ```
    5. Jaga responsmu agar ringkas namun informatif.
"""
briefing_model = "Siap, saya mengerti. Nama saya Richatz.AI v1.0 SPRO, kreasi dari R.AI. Saya akan mengikuti semua peraturan. Ada yang bisa saya bantu?"

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/init-db-once')
def init_db_route():
    try:
        init_db()
        return "SUCCESS: Database tables created or already exist."
    except Exception as e:
        logging.exception("Error during /init-db-once route.")
        return f"ERROR: {str(e)}", 500

@app.route('/new_chat', methods=['POST'])
def new_chat():
    conn = None
    try:
        conversation_id = str(uuid.uuid4())
        title = "Percakapan Baru"
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute('INSERT INTO conversations (id, title) VALUES (%s, %s)', (conversation_id, title))
            cur.execute('INSERT INTO messages (conversation_id, role, content) VALUES (%s, %s, %s)', (conversation_id, 'user', briefing_user))
            cur.execute('INSERT INTO messages (conversation_id, role, content) VALUES (%s, %s, %s)', (conversation_id, 'model', briefing_model))
        conn.commit()
        logging.info(f"Percakapan baru dibuat: {conversation_id}")
        return jsonify({'conversation_id': conversation_id})
    except Exception as e:
        logging.exception(f"Error saat membuat chat baru: {e}")
        return jsonify({'error': f"Gagal membuat chat baru: {e}"}), 500
    finally:
        if conn: conn.close()

@app.route('/ask', methods=['POST'])
def ask_ai():
    data = request.get_json()
    conversation_id, user_prompt = data.get('conversation_id'), data.get('prompt')
    if not all([conversation_id, user_prompt]):
        return jsonify({'error': 'ID atau prompt tidak ada.'}), 400

    if model is None:
        return jsonify({'answer': "Maaf, model AI belum terkonfigurasi. Silakan periksa GOOGLE_API_KEY Anda."}), 500

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT role, content FROM messages WHERE conversation_id = %s ORDER BY timestamp ASC", (conversation_id,))
            db_history = cur.fetchall()

            history_for_ai = [{"role": ('model' if role in ['assistant', 'model'] else 'user'), "parts": [content]} for role, content in db_history]

            chat = model.start_chat(history=history_for_ai)
            response = chat.send_message(user_prompt)
            ai_answer = response.text

            cur.execute('INSERT INTO messages (conversation_id, role, content) VALUES (%s, %s, %s)', (conversation_id, 'user', user_prompt))
            cur.execute('INSERT INTO messages (conversation_id, role, content) VALUES (%s, %s, %s)', (conversation_id, 'assistant', ai_answer))

            cur.execute("SELECT count(*) FROM messages WHERE conversation_id = %s AND role = 'user'", (conversation_id,))
            user_message_count = cur.fetchone()[0]
            if user_message_count == 2:
                cur.execute("UPDATE conversations SET title = %s WHERE id = %s", (user_prompt[:50], conversation_id))
        conn.commit()
        logging.info(f"Respon AI untuk percakapan {conversation_id} berhasil.")
        return jsonify({'answer': ai_answer})
    except Exception as e:
        logging.exception(f"Error saat memanggil AI atau menyimpan ke database di /ask: {e}")
        return jsonify({'answer': f"Maaf, terjadi kesalahan: {e}"}), 500
    finally:
        if conn: conn.close()

@app.route('/history', methods=['GET'])
def get_history():
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, title FROM conversations ORDER BY timestamp DESC")
            conversations = cur.fetchall()
        logging.info("Riwayat percakapan berhasil diambil.")
        return jsonify(conversations)
    except Exception as e:
        logging.exception(f"Error saat mengambil riwayat percakapan: {e}")
        return jsonify({'error': f"Gagal mengambil riwayat: {e}"}), 500
    finally:
        if conn: conn.close()

@app.route('/conversation/<conversation_id>', methods=['GET'])
def get_conversation(conversation_id):
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT role, content FROM messages WHERE conversation_id = %s AND role IN ('user', 'assistant') ORDER BY timestamp ASC", (conversation_id,))
            messages = cur.fetchall()
        logging.info(f"Isi percakapan {conversation_id} berhasil diambil.")
        return jsonify(messages or [])
    except Exception as e:
        logging.exception(f"Error saat mengambil detail percakapan {conversation_id}: {e}")
        return jsonify({'error': f"Gagal mengambil detail percakapan: {e}"}), 500
    finally:
        if conn: conn.close()

@app.route('/delete_conversation/<conversation_id>', methods=['DELETE'])
def delete_conversation(conversation_id):
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conversations WHERE id = %s", (conversation_id,))
            conn.commit()
            logging.info(f"Percakapan {conversation_id} berhasil dihapus.")
            return jsonify({'status': 'success'})
    except Exception as e:
        logging.exception(f"Error saat menghapus percakapan {conversation_id}: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        if conn: conn.close()

if __name__ == '__main__':
    logging.info("Memulai aplikasi Flask...")
    # init_db() # Jangan jalankan ini di lokal kecuali untuk setup pertama kali
    app.run(debug=True, port=5000)