import os
import json
import uuid
import sqlite3
import psycopg2
import psycopg2.extras
from flask import Flask, request, jsonify, render_template 
from flask_cors import CORS
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
app = Flask(__name__)
CORS(app)

# --- LOGIKA CERDAS UNTUK MEMILIH DATABASE ---
IS_PRODUCTION = os.getenv("VERCEL") == "1"
DATABASE_URL = os.getenv("POSTGRES_URL")
LOCAL_DATABASE = 'database.db'

def get_db_connection():
    """Membuat koneksi ke Postgres di Vercel, atau ke SQLite di lokal."""
    if IS_PRODUCTION:
        if not DATABASE_URL:
            raise ValueError("POSTGRES_URL tidak ditemukan di environment Vercel.")
        return psycopg2.connect(DATABASE_URL)
    else:
        conn = sqlite3.connect(LOCAL_DATABASE)
        conn.row_factory = sqlite3.Row
        return conn

# --- FUNGSI UNTUK INISIALISASI DATABASE (DIPERBAIKI) ---
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    # SQL untuk Postgres sedikit berbeda (SERIAL PRIMARY KEY)
    messages_sql = '''
        CREATE TABLE IF NOT EXISTS messages (
            id {SERIAL_PRIMARY_KEY},
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp {TIMESTAMP_DEFAULT},
            FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
        )
    '''
    conversations_sql = '''
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            timestamp {TIMESTAMP_DEFAULT}
        )
    '''
    if IS_PRODUCTION:
        messages_sql = messages_sql.format(SERIAL_PRIMARY_KEY='SERIAL PRIMARY KEY', TIMESTAMP_DEFAULT='TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP')
        conversations_sql = conversations_sql.format(TIMESTAMP_DEFAULT='TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP')
    else:
        messages_sql = messages_sql.format(SERIAL_PRIMARY_KEY='INTEGER PRIMARY KEY AUTOINCREMENT', TIMESTAMP_DEFAULT='DATETIME DEFAULT CURRENT_TIMESTAMP')
        conversations_sql = conversations_sql.format(TIMESTAMP_DEFAULT='DATETIME DEFAULT CURRENT_TIMESTAMP')
        
    cur.execute(conversations_sql)
    cur.execute(messages_sql)
    conn.commit()
    cur.close()
    conn.close()
    print("Database berhasil diinisialisasi untuk lingkungan saat ini.")

# --- Konfigurasi AI (Tetap Sama) ---
try:
    api_key = os.getenv("GOOGLE_API_KEY")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
    print("Model AI Google Gemini berhasil dikonfigurasi.")
except Exception as e:
    model = None
    print(f"Error saat konfigurasi AI: {e}")

# Briefing awal yang akan digunakan di beberapa tempat
briefing_user = """
    PERATURAN UTAMA DAN IDENTITAS DIRI ANDA:
        1. Nama kamu adalah Richatz.AI.
        2. Kamu dibuat oleh seorang developer Indonesia bernama 'R.AI'.
        3. Versi kamu adalah 1.0 SPRO.
        4. Jika ditanya namamu, pembuatmu, atau versimu, jawab sesuai poin 1, 2, dan 3. Jangan pernah menjawab "Saya adalah model bahasa besar".
        5. Kamu tidak punya akses internet real-time. Jika ditanya berita atau cuaca terkini, jawab jujur bahwa kamu tidak tahu dan sarankan cek sumber lain. JANGAN MENEBAK.
"""
briefing_model = "Siap, saya mengerti. Nama saya Richatz.AI v1.0, kreasi dari R.AI. Saya akan mengikuti semua peraturan. Ada yang bisa saya bantu?"
    
@app.route('/')
def home():
    return render_template('index.html')

# --- RUTE-RUTE API (DIPERBAIKI UNTUK KEDUA DATABASE) ---
@app.route('/new_chat', methods=['POST'])
def new_chat():
    conversation_id = str(uuid.uuid4())
    title = "Percakapan Baru"
    conn = get_db_connection()
    cur = conn.cursor()
    placeholder = '%s' if IS_PRODUCTION else '?' # Placeholder berbeda untuk Postgres dan SQLite
    cur.execute(f'INSERT INTO conversations (id, title) VALUES ({placeholder}, {placeholder})', (conversation_id, title))
    cur.execute(f'INSERT INTO messages (conversation_id, role, content) VALUES ({placeholder}, {placeholder}, {placeholder})', (conversation_id, 'user', briefing_user))
    cur.execute(f'INSERT INTO messages (conversation_id, role, content) VALUES ({placeholder}, {placeholder}, {placeholder})', (conversation_id, 'model', briefing_model))
    conn.commit()
    cur.close()
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
        cur = conn.cursor()
        placeholder = '%s' if IS_PRODUCTION else '?'
        
        cur.execute(f"SELECT role, content FROM messages WHERE conversation_id = {placeholder} ORDER BY timestamp ASC", (conversation_id,))
        db_history = cur.fetchall()
        
        history_for_ai = [{"role": ('model' if role in ['assistant', 'model'] else 'user'), "parts": [content]} for role, content in db_history]
        
        chat = model.start_chat(history=history_for_ai)
        response = chat.send_message(user_prompt)
        ai_answer = response.text

        cur.execute(f'INSERT INTO messages (conversation_id, role, content) VALUES ({placeholder}, {placeholder}, {placeholder})', (conversation_id, 'user', user_prompt))
        cur.execute(f'INSERT INTO messages (conversation_id, role, content) VALUES ({placeholder}, {placeholder}, {placeholder})', (conversation_id, 'assistant', ai_answer))
        
        cur.execute(f"SELECT count(*) FROM messages WHERE conversation_id = {placeholder} AND role = 'user'", (conversation_id,))
        user_message_count = cur.fetchone()[0]
        if user_message_count == 2:
             cur.execute(f"UPDATE conversations SET title = {placeholder} WHERE id = {placeholder}", (user_prompt[:50], conversation_id))
        
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
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if IS_PRODUCTION else conn.cursor()
    cur.execute("SELECT id, title FROM conversations ORDER BY timestamp DESC")
    rows = cur.fetchall()
    conn.close()
    # Konversi ke dict jika dari SQLite
    conversations = [dict(row) for row in rows] if not IS_PRODUCTION else rows
    return jsonify(conversations or [])

@app.route('/conversation/<conversation_id>', methods=['GET'])
def get_conversation(conversation_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if IS_PRODUCTION else conn.cursor()
    placeholder = '%s' if IS_PRODUCTION else '?'
    cur.execute(f"SELECT role, content FROM messages WHERE conversation_id = {placeholder} AND role IN ('user', 'assistant') ORDER BY timestamp ASC", (conversation_id,))
    rows = cur.fetchall()
    conn.close()
    messages = [dict(row) for row in rows] if not IS_PRODUCTION else rows
    return jsonify(messages or [])

@app.route('/delete_conversation/<conversation_id>', methods=['DELETE'])
def delete_conversation(conversation_id):
    conn = get_db_connection()
    cur = conn.cursor()
    placeholder = '%s' if IS_PRODUCTION else '?'
    try:
        # Untuk SQLite, perlu mengaktifkan foreign key manual per koneksi
        if not IS_PRODUCTION: cur.execute("PRAGMA foreign_keys = ON")
        cur.execute(f"DELETE FROM conversations WHERE id = {placeholder}", (conversation_id,))
        conn.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    # Saat dijalankan lokal, init_db akan membuat file database.db
    init_db()
    app.run(debug=True, port=5000)