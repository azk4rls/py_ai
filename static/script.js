document.addEventListener('DOMContentLoaded', () => {
    // Referensi semua elemen DOM yang kita butuhkan
    const promptForm = document.getElementById('prompt-form');
    const promptInput = document.getElementById('prompt-input');
    const chatArea = document.getElementById('chat-area');
    const newChatBtn = document.getElementById('new-chat-btn');
    const historyBtn = document.getElementById('history-btn');
    const historySidebar = document.getElementById('history-sidebar');
    const closeHistoryBtn = document.getElementById('close-history-btn');
    const historyList = document.getElementById('history-list');
    const sidebarOverlay = document.getElementById('sidebar-overlay');

    // UBAH INI: Pastikan URL dasar API kosong untuk membuatnya relatif terhadap domain Vercel.
    const API_BASE_URL = ''; 
    let currentConversationId = null;

    // --- FUNGSI-FUNGSI UTAMA ---

    // Memulai percakapan baru
    const startNewChat = async () => {
        try {
            // Menggunakan API_BASE_URL yang sekarang kosong, sehingga fetch akan memanggil /new_chat relatif terhadap domain saat ini
            const response = await fetch(`${API_BASE_URL}/new_chat`, { method: 'POST' });
            
            // Tambahkan penanganan untuk respons HTTP yang tidak OK
            if (!response.ok) {
                const errorBody = await response.text(); // Coba ambil teks error dari body respons
                throw new Error(`Gagal membuat chat baru di server. Status: ${response.status}. Pesan: ${errorBody || 'Tidak ada pesan error dari server.'}`);
            }

            const data = await response.json();
            currentConversationId = data.conversation_id;
            chatArea.innerHTML = ''; // Kosongkan area chat untuk percakapan baru
            appendMessage("Percakapan baru dimulai. Silakan ajukan pertanyaan Anda.", 'ai-system');
        } catch (error) {
            console.error('Error starting new chat:', error);
            // Tampilkan pesan error yang lebih informatif ke pengguna
            appendMessage(`Gagal memulai percakapan baru. Pastikan server berjalan. Detail: ${error.message}`, 'ai-system');
        }
    };
    
    // Menampilkan pesan di layar
    const appendMessage = (text, sender, isTyping = false) => {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('chat-message', `${sender}-message`);
        if (isTyping) {
            messageDiv.classList.add('typing');
            messageDiv.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';
        } else {
            // Menggunakan innerHTML agar teks bisa memuat HTML dasar (misal link, bold) jika diperlukan
            // Namun, untuk keamanan, pastikan teks tidak mengandung skrip berbahaya jika sumbernya dari luar
            messageDiv.innerHTML = text; 
        }
        chatArea.appendChild(messageDiv);
        scrollToBottom();
        return messageDiv;
    };
    
    // Fungsi untuk auto-scroll ke bawah
    const scrollToBottom = () => {
        chatArea.scrollTop = chatArea.scrollHeight;
    };

    // Membuka sidebar history
    const showHistory = async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/history`); // Menggunakan API_BASE_URL relatif
            if (!response.ok) {
                const errorBody = await response.text();
                throw new Error(`Gagal mengambil riwayat. Status: ${response.status}. Pesan: ${errorBody || 'Tidak ada pesan error dari server.'}`);
            }
            const conversations = await response.json();
            
            historyList.innerHTML = ''; // Kosongkan daftar riwayat sebelum mengisi ulang
            if (conversations.length === 0) {
                historyList.innerHTML = '<li class="empty-history">Belum ada riwayat.</li>';
            } else {
                conversations.forEach(conv => {
                    const li = document.createElement('li');
                    li.dataset.id = conv.id; // Menyimpan ID percakapan di elemen data

                    const titleSpan = document.createElement('span');
                    titleSpan.className = 'history-title';
                    // Batasi panjang judul agar tidak terlalu panjang di sidebar
                    titleSpan.textContent = conv.title.substring(0, 25) + (conv.title.length > 25 ? '...' : '');
                    
                    const deleteBtn = document.createElement('button');
                    deleteBtn.className = 'delete-chat-btn';
                    // Menggunakan SVG untuk ikon hapus
                    deleteBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>';

                    li.addEventListener('click', (e) => {
                        // Pastikan hanya elemen judul yang memuat chat, bukan tombol delete
                        if (e.target.closest('.delete-chat-btn')) return;
                        loadConversation(conv.id);
                        closeSidebar(); // Tutup sidebar setelah memuat percakapan
                    });

                    deleteBtn.addEventListener('click', (e) => {
                        e.stopPropagation(); // Mencegah event click menyebar ke parent <li>
                        handleDelete(conv.id, li); // Panggil fungsi hapus
                    });

                    li.appendChild(titleSpan);
                    li.appendChild(deleteBtn);
                    historyList.appendChild(li);
                });
            }
            // Mengaktifkan efek 'push/shrink' dengan menambah kelas ke body
            document.body.classList.add('sidebar-open'); 
            sidebarOverlay.classList.add('active'); // Tampilkan overlay
        } catch (error) {
            console.error('Error fetching history:', error);
            alert(`Gagal mengambil riwayat percakapan. Detail: ${error.message}`);
        }
    };

    // Menutup sidebar
    const closeSidebar = () => {
        document.body.classList.remove('sidebar-open'); // Memicu layout untuk kembali normal
        historySidebar.classList.remove('active'); // Pastikan sidebar itu sendiri juga disembunyikan
        sidebarOverlay.classList.remove('active'); // Sembunyikan overlay
    };

    // Menghapus percakapan
    const handleDelete = async (id, listItemElement) => {
        if (!confirm('Anda yakin ingin menghapus percakapan ini secara permanen?')) return;
        try {
            const response = await fetch(`${API_BASE_URL}/delete_conversation/${id}`, { method: 'DELETE' }); // Menggunakan API_BASE_URL relatif
            if (!response.ok) {
                const errorBody = await response.text();
                throw new Error(`Gagal menghapus di server. Status: ${response.status}. Pesan: ${errorBody || 'Tidak ada pesan error dari server.'}`);
            }
            
            listItemElement.remove(); // Hapus elemen dari DOM
            // Jika tidak ada riwayat tersisa, tampilkan pesan kosong
            if (historyList.children.length === 0) {
                historyList.innerHTML = '<li class="empty-history">Belum ada riwayat.</li>';
            }
            // Jika percakapan yang sedang aktif dihapus, mulai chat baru
            if (currentConversationId === id) {
                startNewChat();
            }
        } catch (error) {
            console.error('Error deleting conversation:', error);
            alert(`Gagal menghapus percakapan. Detail: ${error.message}`);
        }
    };

    // Memuat percakapan lama
    const loadConversation = async (id) => {
        try {
            const response = await fetch(`${API_BASE_URL}/conversation/${id}`); // Menggunakan API_BASE_URL relatif
            if (!response.ok) {
                const errorBody = await response.text();
                throw new Error(`Gagal memuat percakapan. Status: ${response.status}. Pesan: ${errorBody || 'Tidak ada pesan error dari server.'}`);
            }
            const messages = await response.json();
            
            currentConversationId = id;
            chatArea.innerHTML = ''; // Kosongkan area chat
            messages.forEach(msg => {
                const role = msg.role === 'assistant' ? 'ai' : msg.role;
                appendMessage(msg.content, role);
            });
            scrollToBottom();
        } catch (error) {
            console.error('Error loading conversation:', error);
            appendMessage(`Gagal memuat percakapan. Detail: ${error.message}`, 'ai-system');
        }
    };

    // --- EVENT LISTENERS ---

    // Listener untuk form utama (saat user submit prompt)
    promptForm.addEventListener('submit', async (e) => {
        e.preventDefault(); // Mencegah pengiriman form default
        const userText = promptInput.value.trim();
        // Jangan lakukan apa-apa jika prompt kosong atau belum ada conversation ID
        if (userText === '' || !currentConversationId) return;

        appendMessage(userText, 'user'); // Tampilkan pesan user
        promptInput.value = ''; // Kosongkan input
        const typingIndicator = appendMessage('', 'ai', true); // Tampilkan indikator mengetik

        try {
            const response = await fetch(`${API_BASE_URL}/ask`, { // Menggunakan API_BASE_URL relatif
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt: userText, conversation_id: currentConversationId }),
            });

            if (!response.ok) {
                const errData = await response.json(); // Coba parsing JSON error
                throw new Error(errData.answer || `Network response was not ok. Status: ${response.status}.`);
            }
            const data = await response.json();
            typingIndicator.remove(); // Hapus indikator mengetik
            appendMessage(data.answer, 'ai'); // Tampilkan respons AI
        } catch (error) {
            typingIndicator.remove(); // Hapus indikator mengetik
            appendMessage(`Maaf, terjadi kesalahan: ${error.message}`, 'ai-system'); // Tampilkan pesan error ke user
            console.error('Fetch Error:', error); // Log error lengkap ke konsol
        }
    });

    // Listener untuk tombol-tombol di navbar dan sidebar
    newChatBtn.addEventListener('click', startNewChat);
    historyBtn.addEventListener('click', showHistory);
    closeHistoryBtn.addEventListener('click', closeSidebar);
    sidebarOverlay.addEventListener('click', closeSidebar);

    // --- INISIALISASI ---
    // Mulai chat baru saat halaman pertama kali dimuat
    startNewChat();
});