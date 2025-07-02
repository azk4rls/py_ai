import os
import json
import uuid
import psycopg2 # Library untuk database cloud Postgres
from flask import Flask, request, jsonify, render_template 
from flask_cors import CORS
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

app = Flask(__name__)
CORS(app)

# Ambil alamat database dari Environment Variable Vercel
DATABASE_URL = os.getenv("POSTGRES_URL")

# --- FUNGSI BARU UNTUK KONEKSI KE POSTGRES ---
def get_db_connection():
    """Membuat koneksi ke database Postgres di Vercel."""
    conn = psycopg2.connect(DATABASE_URL)
    return conn

# --- FUNGSI UNTUK INISIALISASI DATABASE ---
def init_db():
    """Membuat tabel jika belum ada (hanya untuk dijalankan lokal sekali)."""
    conn = get_db_connection()
    cur = conn.cursor()
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
    cur.close()
    conn.close()
    print("Database Postgres berhasil diinisialisasi.")

# --- Konfigurasi AI Google Gemini ---
try:
    api_key = os.getenv("GOOGLE_API_KEY")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
    print("Model AI Google Gemini berhasil dikonfigurasi.")
except Exception as e:
    print(f"Error saat konfigurasi AI: {e}")
    model = None

# --- RUTE-RUTE API ---

@app.route('/')
def home():
    return render_template('index.html')

# --- TAMBAHKAN BLOK INI DI SINI ---
@app.route('/init-db-once')
def init_db_route():
    """Rute sementara ini hanya untuk dipanggil satu kali guna membuat tabel di Vercel."""
    try:
        init_db()
        return "SUCCESS: Database tables created or already exist."
    except Exception as e:
        return f"ERROR: {str(e)}", 500
# -----------------------------------

@app.route('/new_chat', methods=['POST'])
def new_chat():
    
    conversation_id = str(uuid.uuid4())
    title = "Percakapan Baru"
    
    # Briefing yang bersih dan konsisten
    briefing_user = """
        PERATURAN UTAMA DAN IDENTITAS DIRI ANDA:
        1. Nama kamu adalah Richatz.AI. Kamu adalah asisten AI yang cerdas dan ramah.
        2. Jika ada yang bertanya siapa namamu, jawab dengan percaya diri bahwa namamu adalah Richatz.AI.
        3. Kamu dibuat oleh seorang developer Indonesia bernama 'Mazka'. Jika ditanya siapa pembuatmu, sebutkan nama Mazka.
        4. Versi kamu adalah 1.0. Jika ditanya, sebutkan kamu adalah Richatz.AI v1.0 yang ditenagai teknologi Google.
        5. Kamu tidak punya akses internet real-time. Jika ditanya berita atau cuaca terkini, jawab dengan jujur bahwa kamu tidak tahu dan sarankan cek sumber lain. JANGAN MENEBAK.
    """
    briefing_model = "Siap, saya mengerti. Nama saya Richatz.AI v1.0, kreasi dari Mazka. Saya akan mengikuti semua peraturan. Ada yang bisa saya bantu?"

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO conversations (id, title) VALUES (%s, %s)', (conversation_id, title))
    cur.execute('INSERT INTO messages (conversation_id, role, content) VALUES (%s, %s, %s)', (conversation_id, 'user', briefing_user))
    cur.execute('INSERT INTO messages (conversation_id, role, content) VALUES (%s, %s, %s)', (conversation_id, 'model', briefing_model))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'conversation_id': conversation_id})

@app.route('/ask', methods=['POST'])
def ask_ai():
    data = request.get_json()
    conversation_id = data.get('conversation_id')
    user_prompt = data.get('prompt')

    if not all([conversation_id, user_prompt]):
        return jsonify({'error': 'ID percakapan dan prompt diperlukan.'}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
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
        return jsonify({'answer': f"Maaf, terjadi kesalahan: {e}"})
    finally:
        cur.close()
        conn.close()

@app.route('/history', methods=['GET'])
def get_history():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, title FROM conversations ORDER BY timestamp DESC")
    conversations = [{"id": row[0], "title": row[1]} for row in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify(conversations)

@app.route('/conversation/<conversation_id>', methods=['GET'])
def get_conversation(conversation_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT role, content FROM messages WHERE conversation_id = %s ORDER BY timestamp ASC LIMIT -1 OFFSET 2", (conversation_id,))
    messages = [{"role": row[0], "content": row[1]} for row in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify(messages)

@app.route('/delete_conversation/<conversation_id>', methods=['DELETE'])
def delete_conversation(conversation_id):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM conversations WHERE id = %s", (conversation_id,))
        conn.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        cur.close()
        conn.close()

# Blok ini hanya untuk menjalankan server di komputer lokal
if __name__ == '__main__':
    app.run(debug=True, port=5000)