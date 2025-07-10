# init_db.py

import os
import psycopg2
from dotenv import load_dotenv

# Memuat semua variabel dari file .env
load_dotenv()

# Ambil URL koneksi dari environment
DATABASE_URL = os.getenv("POSTGRES_URL")

# Perintah SQL yang ingin kita jalankan
SQL_COMMANDS = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE conversations ADD COLUMN IF NOT EXISTS user_id INTEGER;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'fk_user' AND conrelid = 'conversations'::regclass
    ) THEN
        ALTER TABLE conversations 
        ADD CONSTRAINT fk_user 
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
    END IF;
END;
$$;
"""

def initialize_database():
    """Fungsi untuk terhubung ke DB dan menjalankan perintah SQL."""
    conn = None
    if not DATABASE_URL:
        print("ERROR: Variabel POSTGRES_URL tidak ditemukan di file .env Anda.")
        return

    try:
        print("Mencoba terhubung ke database Neon...")
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        cur = conn.cursor()
        
        print("Koneksi berhasil. Menjalankan perintah SQL untuk membuat tabel...")
        cur.execute(SQL_COMMANDS)
        conn.commit()
        
        print("\n==============================================")
        print("SUKSES! Tabel berhasil dibuat atau sudah ada.")
        print("==============================================")
        
        cur.close()
    except Exception as e:
        print("\n======================================")
        print(f"TERJADI ERROR: {e}")
        print("======================================")
    finally:
        if conn is not None:
            conn.close()
            print("Koneksi database ditutup.")

# Jalankan fungsi utama
if __name__ == '__main__':
    initialize_database()