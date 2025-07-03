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

    // UBAH BARIS INI
    const API_BASE_URL = ''; // Jadikan string kosong agar path menjadi relatif
    // Atau bisa juga tidak perlu variabel ini dan langsung panggil '/new_chat', '/ask', dst.

    let currentConversationId = null;

    // --- FUNGSI-FUNGSI UTAMA ---

    // Memulai percakapan baru
    const startNewChat = async () => {
        try {
            // Panggil endpoint relatif.
            // Browser akan otomatis menambahkan domain saat ini (misalnya richatzai.vercel.app)
            const response = await fetch(`${API_BASE_URL}/new_chat`, { method: 'POST' }); // Atau cukup fetch('/new_chat', { method: 'POST' });
            if (!response.ok) {
                // Tangani error HTTP status codes dengan lebih baik
                const errorBody = await response.text(); // Coba ambil teks error dari body respons
                throw new Error(`Gagal membuat chat baru di server. Status: ${response.status}. Pesan: ${errorBody}`);
            }
            const data = await response.json();
            currentConversationId = data.conversation_id;
            chatArea.innerHTML = '';
            appendMessage("Percakapan baru dimulai. Silakan ajukan pertanyaan Anda.", 'ai-system');
        } catch (error) {
            console.error('Error starting new chat:', error);
            appendMessage(`Gagal memulai percakapan baru. Pastikan server berjalan. Detail: ${error.message}`, 'ai-system');
        }
    };
    
    // ... (sisa kode appendMessage, scrollToBottom, dan showHistory)

    // Membuka sidebar history
    const showHistory = async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/history`); // UBAH INI
            if (!response.ok) {
                const errorBody = await response.text();
                throw new Error(`Gagal mengambil riwayat. Status: ${response.status}. Pesan: ${errorBody}`);
            }
            const conversations = await response.json();
            
            historyList.innerHTML = '';
            if (conversations.length === 0) {
                historyList.innerHTML = '<li class="empty-history">Belum ada riwayat.</li>';
            } else {
                conversations.forEach(conv => {
                    const li = document.createElement('li');
                    li.dataset.id = conv.id;

                    const titleSpan = document.createElement('span');
                    titleSpan.className = 'history-title';
                    titleSpan.textContent = conv.title.substring(0, 25) + (conv.title.length > 25 ? '...' : '');
                    
                    const deleteBtn = document.createElement('button');
                    deleteBtn.className = 'delete-chat-btn';
                    deleteBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>';

                    li.addEventListener('click', (e) => {
                        // Pastikan hanya elemen judul yang memuat chat, bukan tombol delete
                        if (e.target.closest('.delete-chat-btn')) return;
                        loadConversation(conv.id);
                        closeSidebar();
                    });

                    deleteBtn.addEventListener('click', (e) => {
                        e.stopPropagation();
                        handleDelete(conv.id, li);
                    });

                    li.appendChild(titleSpan);
                    li.appendChild(deleteBtn);
                    historyList.appendChild(li);
                });
            }
            // Mengaktifkan efek 'push/shrink' dengan menambah kelas ke body
            document.body.classList.add('sidebar-open'); 
            sidebarOverlay.classList.add('active');
        } catch (error) {
            console.error('Error fetching history:', error);
            alert(`Gagal mengambil riwayat percakapan. Detail: ${error.message}`);
        }
    };

    // ... (sisa kode closeSidebar, handleDelete)

    // Menghapus percakapan
    const handleDelete = async (id, listItemElement) => {
        if (!confirm('Anda yakin ingin menghapus percakapan ini secara permanen?')) return;
        try {
            const response = await fetch(`${API_BASE_URL}/delete_conversation/${id}`, { method: 'DELETE' }); // UBAH INI
            if (!response.ok) {
                const errorBody = await response.text();
                throw new Error(`Gagal menghapus di server. Status: ${response.status}. Pesan: ${errorBody}`);
            }
            
            listItemElement.remove();
            if (historyList.children.length === 0) {
                historyList.innerHTML = '<li class="empty-history">Belum ada riwayat.</li>';
            }
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
            const response = await fetch(`${API_BASE_URL}/conversation/${id}`); // UBAH INI
            if (!response.ok) {
                const errorBody = await response.text();
                throw new Error(`Gagal memuat percakapan. Status: ${response.status}. Pesan: ${errorBody}`);
            }
            const messages = await response.json();
            
            currentConversationId = id;
            chatArea.innerHTML = '';
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

    // Listener untuk form utama
    promptForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const userText = promptInput.value.trim();
        if (userText === '' || !currentConversationId) return;

        appendMessage(userText, 'user');
        promptInput.value = '';
        const typingIndicator = appendMessage('', 'ai', true);

        try {
            const response = await fetch(`${API_BASE_URL}/ask`, { // UBAH INI
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt: userText, conversation_id: currentConversationId }),
            });
            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.answer || `Network response was not ok. Status: ${response.status}`);
            }
            const data = await response.json();
            typingIndicator.remove();
            appendMessage(data.answer, 'ai');
        } catch (error) {
            typingIndicator.remove();
            appendMessage(`Maaf, terjadi kesalahan: ${error.message}`, 'ai-system');
            console.error('Fetch Error:', error);
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