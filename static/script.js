// static/script.js

document.addEventListener('DOMContentLoaded', () => {
    // === Seleksi Semua Elemen DOM di Satu Tempat ===
    const promptForm = document.getElementById('prompt-form');
    const promptInput = document.getElementById('prompt-input');
    const chatArea = document.getElementById('chat-area');
    const newChatBtn = document.getElementById('new-chat-btn');
    const historyBtn = document.getElementById('history-btn');
    const historySidebar = document.getElementById('history-sidebar');
    const closeHistoryBtn = document.getElementById('close-history-btn');
    const historyList = document.getElementById('history-list');
    const sidebarOverlay = document.getElementById('sidebar-overlay');
    const profileBtn = document.getElementById('profile-icon-btn');
    const profileDropdown = document.getElementById('profile-dropdown');

    // === State Aplikasi ===
    const API_BASE_URL = ''; 
    let currentConversationId = null;
    let isLoading = false;

    // === Fungsi-fungsi Inti ===

    /** Menampilkan pesan di UI, dengan parsing Markdown untuk AI. */
    const appendMessage = (text, sender) => {
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('chat-message', `${sender}-message`);
        
        // Hapus indikator loading jika ada sebelum menambahkan pesan baru
        const typingIndicator = chatArea.querySelector('.typing');
        if (typingIndicator) {
            typingIndicator.parentElement.remove();
        }

        if (sender === 'ai' && window.marked) {
            messageDiv.innerHTML = marked.parse(text, { sanitize: true });
        } else {
            messageDiv.textContent = text;
        }
        
        chatArea.appendChild(messageDiv);
        scrollToBottom();
    };
    
    /** Menampilkan indikator "mengetik...". */
    const showTypingIndicator = () => {
        const typingDiv = document.createElement('div');
        typingDiv.classList.add('chat-message', 'ai-message', 'typing');
        typingDiv.innerHTML = `
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>`;
        chatArea.appendChild(typingDiv);
        scrollToBottom();
    };

    /** Fungsi untuk auto-scroll ke bawah */
    const scrollToBottom = () => {
        chatArea.scrollTop = chatArea.scrollHeight;
    };

    /** Mengambil dan menampilkan daftar history di sidebar. */
    const fetchAndRenderHistory = async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/history`);
            if (!response.ok) throw new Error('Gagal mengambil riwayat.');
            
            const conversations = await response.json();
            historyList.innerHTML = '';
            
            if (conversations.length === 0) {
                historyList.innerHTML = '<li class="empty-history">Belum ada riwayat.</li>';
                return;
            }

            conversations.forEach(conv => {
                const li = document.createElement('li');
                li.dataset.id = conv.id;
                li.innerHTML = `
                    <span class="history-title">${conv.title}</span>
                    <button class="delete-chat-btn" data-id="${conv.id}">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
                    </button>
                `;
                historyList.appendChild(li);
            });
        } catch (error) {
            console.error('Error fetching history:', error);
            historyList.innerHTML = '<li class="empty-history">Gagal memuat.</li>';
        }
    };
    
    /** Memulai sesi chat baru dari awal. */
    const startNewChat = async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/new_chat`, { method: 'POST' });
            if (!response.ok) throw new Error('Gagal membuat chat baru di server.');

            const data = await response.json();
            currentConversationId = data.conversation_id;
            
            chatArea.innerHTML = ''; 
            appendMessage("Percakapan baru dimulai. Silakan ajukan pertanyaan Anda.", 'ai-system');
            promptInput.focus();
            
            await fetchAndRenderHistory(); // Muat ulang history untuk menampilkan "Percakapan Baru"
        } catch (error) {
            console.error('Error starting new chat:', error);
            appendMessage(`Gagal memulai percakapan baru.`, 'ai-system');
        }
    };

    /** Memuat konten dari chat yang dipilih di history. */
    const loadConversation = async (id) => {
        currentConversationId = id;
        chatArea.innerHTML = '';
        showTypingIndicator(); // Tampilkan loading saat memuat

        try {
            const response = await fetch(`${API_BASE_URL}/conversation/${id}`);
            if (!response.ok) throw new Error('Gagal memuat percakapan.');
            
            const messages = await response.json();
            chatArea.innerHTML = ''; // Hapus loading lagi
            
            messages.forEach(msg => {
                appendMessage(msg.content, msg.role === 'assistant' ? 'ai' : 'user');
            });
            promptInput.focus();
        } catch (error) {
            chatArea.innerHTML = '';
            appendMessage(`Gagal memuat percakapan. ${error.message}`, 'ai-system');
            console.error('Error loading conversation:', error);
        }
    };

    /** Menghapus percakapan */
    const handleDelete = async (id, listItemElement) => {
        if (!confirm('Anda yakin ingin menghapus percakapan ini?')) return;
        try {
            await fetch(`${API_BASE_URL}/delete_conversation/${id}`, { method: 'DELETE' });
            listItemElement.remove();
            if (historyList.children.length === 0) {
                historyList.innerHTML = '<li class="empty-history">Belum ada riwayat.</li>';
            }
            if (currentConversationId === id) {
                currentConversationId = null;
                chatArea.innerHTML = '';
                appendMessage('Pilih percakapan dari history atau buat yang baru.', 'ai-system');
            }
        } catch (error) {
            console.error('Error deleting conversation:', error);
        }
    };

    /** Mengatur buka/tutup sidebar di mobile. */
    const toggleSidebar = (forceClose = false) => {
        if (forceClose) {
            document.body.classList.remove('sidebar-open');
            sidebarOverlay.classList.remove('active');
        } else {
            document.body.classList.toggle('sidebar-open');
            sidebarOverlay.classList.toggle('active');
        }
    };
    
    // === Event Listeners (Pengatur Fungsi Klik) ===

    // Listener untuk form utama saat mengirim pesan
    promptForm.addEventListener('submit', async (e) => {
        e.preventDefault(); 
        const userText = promptInput.value.trim();
        if (userText === '' || isLoading) return;

        if (!currentConversationId) {
            await startNewChat();
        }
        
        isLoading = true;
        appendMessage(userText, 'user'); 
        promptInput.value = '';
        showTypingIndicator();

        try {
            const response = await fetch(`${API_BASE_URL}/ask`, { 
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt: userText, conversation_id: currentConversationId }),
            });

            if (!response.ok) throw new Error('Respons server tidak baik.');
            const data = await response.json();
            appendMessage(data.answer, 'ai');

            // Jika judulnya "Percakapan Baru", perbarui dengan prompt pertama
            const activeHistoryItem = historyList.querySelector(`li[data-id="${currentConversationId}"] .history-title`);
            if (activeHistoryItem && activeHistoryItem.textContent === "Percakapan Baru") {
                activeHistoryItem.textContent = userText.substring(0, 25) + (userText.length > 25 ? '...' : '');
            }

        } catch (error) {
            appendMessage(`Maaf, terjadi kesalahan: ${error.message}`, 'ai-system');
            console.error('Fetch Error:', error); 
        } finally {
            isLoading = false;
        }
    });

    // Listener untuk tombol-tombol
    newChatBtn.addEventListener('click', startNewChat);
    historyBtn.addEventListener('click', fetchAndRenderHistory);
    closeHistoryBtn.addEventListener('click', () => toggleSidebar(true));
    sidebarOverlay.addEventListener('click', () => toggleSidebar(true));

    // Listener untuk daftar history (memuat dan menghapus)
    historyList.addEventListener('click', (e) => {
        const targetListItem = e.target.closest('li[data-id]');
        if (!targetListItem) return;

        const convId = targetListItem.dataset.id;
        if (e.target.closest('.delete-chat-btn')) {
            e.stopPropagation();
            handleDelete(convId, targetListItem);
        } else {
            loadConversation(convId);
            toggleSidebar(true);
        }
    });
    
    // Listener untuk dropdown profil
    if (profileBtn && profileDropdown) {
        profileBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            profileDropdown.classList.toggle('active');
        });
        window.addEventListener('click', (e) => {
            if (!profileBtn.contains(e.target) && !profileDropdown.contains(e.target)) {
                profileDropdown.classList.remove('active');
            }
        });
    }

    // === Inisialisasi Aplikasi ===
    fetchAndRenderHistory();
    appendMessage('Selamat datang! Pilih percakapan dari history atau klik "New +" untuk memulai.', 'ai-system');
});