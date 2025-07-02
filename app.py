import os
import json
import uuid
import psycopg2
import psycopg2.extras 
from flask import Flask, request, jsonify, render_template 
from flask_cors import CORS
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
app = Flask(__name__)
CORS(app)

DATABASE_URL = os.getenv("POSTGRES_URL")

def get_db_connection():
    if not DATABASE_URL:
        raise ValueError("POSTGRES_URL tidak ditemukan di environment variables.")
    conn_str = DATABASE_URL + "?sslmode=require"
    conn = psycopg2.connect(conn_str)
    return conn

# ... (sisa fungsi Anda dari init_db sampai delete_conversation tetap sama persis) ...
def init_db():
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, title TEXT NOT NULL, timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP)
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS messages (id SERIAL PRIMARY KEY, conversation_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE)
        ''')
    conn.commit()
    conn.close()
    print("Database Postgres berhasil diinisialisasi.")

try:
    api_key = os.getenv("GOOGLE_API_KEY")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
    print("Model AI Google Gemini berhasil dikonfigurasi.")
except Exception as e:
    model = None
    print(f"Error saat konfigurasi AI: {e}")

briefing_user = "..." # briefing Anda
briefing_model = "..." # briefing Anda

# --- RUTE HOME YANG SUDAH DIMODIFIKASI UNTUK DIAGNOSTIK ---
@app.route('/')
def home():
    # Blok ini akan mencetak status variabel Anda ke Vercel Logs
    print("--- MEMULAI PENGECEKAN ENVIRONMENT VARIABLES ---")
    google_key = os.getenv("GOOGLE_API_KEY")
    postgres_url = os.getenv("POSTGRES_URL")

    google_key_status = "ADA & Terisi" if google_key else "TIDAK ADA / KOSONG"
    postgres_url_status = "ADA & Terisi" if postgres_url else "TIDAK ADA / KOSONG"

    print(f"Status GOOGLE_API_KEY: {google_key_status}")
    print(f"Status POSTGRES_URL: {postgres_url_status}")
    print("--- SELESAI PENGECEKAN ---")
    
    return render_template('index.html')
# -----------------------------------------------------------

# ... (sisa rute Anda: /init-db-once, /new_chat, /ask, dll, tetap sama) ...
@app.route('/init-db-once')
def init_db_route():
    try:
        init_db()
        return "SUCCESS: Database tables created."
    except Exception as e:
        return f"ERROR: {str(e)}", 500

@app.route('/new_chat', methods=['POST'])
def new_chat():
    conversation_id = str(uuid.uuid4())
    title = "Percakapan Baru"
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute('INSERT INTO conversations (id, title) VALUES (%s, %s)', (conversation_id, title))
        cur.execute('INSERT INTO messages (conversation_id, role, content) VALUES (%s, %s, %s)', (conversation_id, 'user', briefing_user))
        cur.execute('INSERT INTO messages (conversation_id, role, content) VALUES (%s, %s, %s)', (conversation_id, 'model', briefing_model))
    conn.commit()
    conn.close()
    return jsonify({'conversation_id': conversation_id})

@app.route('/ask', methods=['POST'])
def ask_ai():
    data = request.get_json()
    conversation_id, user_prompt = data.get('conversation_id'), data.get('prompt')
    if not all([conversation_id, user_prompt]):
        return jsonify({'error': 'ID atau prompt tidak ada.'}), 400
    conn = get_db_connection()
    try:
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
        return jsonify({'answer': ai_answer})
    except Exception as e:
        print(f"Error saat memanggil API: {e}")
        return jsonify({'answer': f"Maaf, terjadi kesalahan: {e}"}), 500
    finally:
        if conn: conn.close()

@app.route('/history', methods=['GET'])
def get_history():
    conn = get_db_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT id, title FROM conversations ORDER BY timestamp DESC")
        conversations = cur.fetchall()
    conn.close()
    return jsonify(conversations or [])

@app.route('/conversation/<conversation_id>', methods=['GET'])
def get_conversation(conversation_id):
    conn = get_db_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT role, content FROM messages WHERE conversation_id = %s AND role IN ('user', 'assistant') ORDER BY timestamp ASC", (conversation_id,))
        messages = cur.fetchall()
    conn.close()
    return jsonify(messages or [])

@app.route('/delete_conversation/<conversation_id>', methods=['DELETE'])
def delete_conversation(conversation_id):
    conn = get_db_connection()
    with conn.cursor() as cur:
        try:
            cur.execute("DELETE FROM conversations WHERE id = %s", (conversation_id,))
            conn.commit()
            return jsonify({'status': 'success'})
        except Exception as e:
            return jsonify({'status': 'error', 'message': str(e)}), 500
        finally:
            conn.close()

if __name__ == '__main__':
    # init_db() # Jangan jalankan otomatis di lokal lagi untuk sementara
    app.run(debug=True, port=5000)