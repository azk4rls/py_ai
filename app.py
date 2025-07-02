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
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
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

# --- BRIEFING AWAL UNTUK AI (TETAP SAMA) ---
briefing_user = """
    PERATURAN UTAMA DAN IDENTITAS DIRI ANDA:
    1. Nama kamu adalah Richatz.AI, dibuat oleh seorang developer Indonesia bernama 'Mazka'. Versi kamu adalah 1.0.
    2. Jika ditanya identitasmu, jawab sesuai poin 1. Jangan pernah bilang kamu adalah "model bahasa besar".
    3. Kamu tidak punya akses internet real-time. Jika ditanya berita atau cuaca terkini, jawab jujur bahwa kamu tidak tahu. JANGAN MENEBAK.
"""
briefing_model = "Siap, saya mengerti. Nama saya Richatz.AI v1.0, kreasi dari Mazka. Saya akan mengikuti semua peraturan. Ada yang bisa saya bantu?"
    
@app.route('/')
def home():
    return render_template('index.html')

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
    conversation_id = data.get('conversation_id')
    user_prompt = data.get('prompt')
    if not all([conversation_id, user_prompt]):
        return jsonify({'error': 'ID atau prompt tidak ada.'}), 400

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            # --- OPTIMASI DI SINI ---
            # Hanya ambil 10 pesan terakhir untuk "memori jangka pendek" AI
            cur.execute("""
                SELECT role, content FROM messages 
                WHERE conversation_id = %s AND role IN ('user', 'assistant') 
                ORDER BY timestamp DESC LIMIT 10
            """, (conversation_id,))
            
            # Ambil histori, lalu balik urutannya agar menjadi kronologis
            db_history = cur.fetchall()[::-1] 
            
            # Susun histori untuk dikirim ke API, dimulai dengan briefing awal
            history_for_ai = [
                {"role": "user", "parts": [briefing_user]},
                {"role": "model", "parts": [briefing_model]}
            ]
            for role, content in db_history:
                history_for_ai.append({"role": 'model' if role == 'assistant' else 'user', "parts": [content]})
            
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

# Rute lainnya (history, conversation, delete) tetap sama
@app.route('/history', methods=['GET'])
def get_history():
    conn = get_db_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT id, title FROM conversations ORDER BY timestamp DESC")
        conversations = cur.fetchall()
    conn.close()
    return jsonify(conversations)

@app.route('/conversation/<conversation_id>', methods=['GET'])
def get_conversation(conversation_id):
    conn = get_db_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT role, content FROM messages WHERE conversation_id = %s AND role IN ('user', 'assistant') ORDER BY timestamp ASC", (conversation_id,))
        messages = cur.fetchall()
    conn.close()
    return jsonify(messages)

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
    app.run(debug=True, port=5000)