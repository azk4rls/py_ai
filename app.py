import os
from flask import Flask

app = Flask(__name__)

# Rute ini akan menangkap SEMUA permintaan
@app.route('/')
@app.route('/<path:path>')
def diagnostic_route(path=''):
    
    # --- BLOK DIAGNOSTIK UTAMA ---
    print("--- MEMULAI INSPEKSI ENVIRONMENT VARIABLES VERCEL ---")
    
    google_key = os.getenv("GOOGLE_API_KEY")
    postgres_url = os.getenv("POSTGRES_URL")
    
    print(f"GOOGLE_API_KEY DITEMUKAN: {'YA' if google_key else 'TIDAK'}")
    if google_key:
        # Hanya tampilkan beberapa karakter awal demi keamanan
        print(f"Nilai Awal GOOGLE_API_KEY: {google_key[:4]}... (disensor)")
    
    print("-" * 20)
    
    print(f"POSTGRES_URL DITEMUKAN: {'YA' if postgres_url else 'TIDAK'}")
    if postgres_url:
        # Tampilkan nilai mentahnya agar kita bisa lihat formatnya
        print(f"NILAI MENTAH POSTGRES_URL: {postgres_url}")
        
    print("--- SELESAI INSPEKSI ---")
    
    return "<h1>Proses Diagnostik Berjalan. Silakan cek tab 'Logs' di dashboard Vercel Anda.</h1>"