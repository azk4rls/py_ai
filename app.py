import os
import json
import sqlite3
import uuid
from flask import Flask, request, jsonify, render_template 
from flask_cors import CORS
from dotenv import load_dotenv
import google.generativeai as genai

# Muat environment variables dari file .env
load_dotenv()

# Inisialisasi aplikasi Flask
app = Flask(__name__)
CORS(app)
DATABASE = 'database.db'

# --- FUNGSI UNTUK INISIALISASI DATABASE ---
def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    # Tabel untuk metadata percakapan
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Tabel untuk semua pesan
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE
        )
    ''')
    conn.commit()
    conn.close()
    print("Database berhasil diinisialisasi.")

# --- Konfigurasi AI Google Gemini ---
try:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY tidak ditemukan di file .env")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
    print("Model AI Google Gemini berhasil dikonfigurasi.")
except Exception as e:
    print(f"Error saat konfigurasi AI: {e}")
    model = None

# --- RUTE-RUTE API ---

@app.route('/')
def home():
    """Menyajikan halaman utama."""
    return render_template('index.html')

@app.route('/new_chat', methods=['POST'])
def new_chat():
    """Membuat entri percakapan baru di database."""
    conversation_id = str(uuid.uuid4())
    title = "Percakapan Baru"
    
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO conversations (id, title) VALUES (?, ?)', (conversation_id, title))
    
    briefing_user = """
        PERATURAN UTAMA DAN IDENTITAS DIRI ANDA:
        1. Nama kamu adalah Richatz.AI. Kamu adalah asisten AI yang cerdas, ramah, dan membantu.
        2. Jika ada yang bertanya siapa namamu, atau "kamu siapa?", jawab dengan percaya diri bahwa namamu adalah Richatz.AI. Jangan pernah menjawab "Saya adalah model bahasa besar".
        3. Kamu dibuat oleh seorang developer Indonesia bernama 'Shec BMF. Jika ditanya siapa pembuatmu, sebutkan nama Mazka.
        4. Versi kamu adalah 1.0. Jika ditanya, sebutkan kamu adalah Richatz.AI v1.0 SPRO.
        5. Kamu tidak punya akses internet real-time. Jika ditanya berita atau cuaca terkini, jawab dengan jujur bahwa kamu saat ini tidak punya akses ini dan akan ada di update 1.7 SMAX. JANGAN MENEBAK.
    """
    briefing_model = "Siap, saya mengerti. Nama saya Richatz.AI v1.0 SPRO, kreasi dari Shec BWF. Saya akan selalu mengikuti semua peraturan. Ada yang bisa saya bantu?"
    
    cursor.execute('INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)', (conversation_id, 'user', briefing_user))
    cursor.execute('INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)', (conversation_id, 'model', briefing_model))
    
    conn.commit()
    conn.close()
    return jsonify({'conversation_id': conversation_id})

@app.route('/ask', methods=['POST'])
def ask_ai():
    """Menerima prompt, memproses dengan AI, dan menyimpan ke database."""
    data = request.get_json()
    conversation_id = data.get('conversation_id')
    user_prompt = data.get('prompt')

    if not all([conversation_id, user_prompt]):
        return jsonify({'error': 'conversation_id dan prompt diperlukan.'}), 400

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY timestamp ASC", (conversation_id,))
        db_history = cursor.fetchall()

        history_for_ai = []
        for role, content in db_history:
            api_role = 'model' if role in ['assistant', 'model'] else 'user'
            history_for_ai.append({"role": api_role, "parts": [content]})
        
        chat = model.start_chat(history=history_for_ai)
        response = chat.send_message(user_prompt)
        ai_answer = response.text

        cursor.execute('INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)', (conversation_id, 'user', user_prompt))
        cursor.execute('INSERT INTO messages (conversation_id, role, content) VALUES (?, ?, ?)', (conversation_id, 'assistant', ai_answer))
        
        cursor.execute("SELECT count(*) FROM messages WHERE conversation_id = ? AND role = 'user'", (conversation_id,))
        user_message_count = cursor.fetchone()[0]
        if user_message_count == 2: # Jika ini pesan user pertama setelah briefing
             cursor.execute("UPDATE conversations SET title = ? WHERE id = ?", (user_prompt[:50], conversation_id))

        conn.commit()
        return jsonify({'answer': ai_answer})
    except Exception as e:
        print(f"Error saat memanggil API: {e}")
        return jsonify({'answer': f"Maaf, terjadi kesalahan: {e}"})
    finally:
        conn.close()

@app.route('/history', methods=['GET'])
def get_history():
    """Mengambil daftar semua percakapan."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, title FROM conversations ORDER BY timestamp DESC")
    conversations = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(conversations)

@app.route('/conversation/<conversation_id>', methods=['GET'])
def get_conversation(conversation_id):
    """Mengambil semua pesan dari percakapan tertentu."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    # Mengabaikan 2 pesan briefing awal saat menampilkan ke user
    cursor.execute("SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY timestamp ASC LIMIT -1 OFFSET 2", (conversation_id,))
    messages = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(messages)

@app.route('/delete_conversation/<conversation_id>', methods=['DELETE'])
def delete_conversation(conversation_id):
    """Menghapus percakapan dan semua pesannya dari database."""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON") # Aktifkan foreign key constraint untuk delete cascade
        cursor.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        conn.commit()
        return jsonify({'status': 'success', 'message': 'Percakapan berhasil dihapus.'})
    except Exception as e:
        print(f"Error saat menghapus percakapan: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        conn.close()

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)