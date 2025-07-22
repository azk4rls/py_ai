// static/script.js (FINAL & LENGKAP)

document.addEventListener('DOMContentLoaded', () => {
    // === 1. Seleksi Elemen DOM ===
    const chatContainer = document.getElementById('chat-area');
    const promptForm = document.getElementById('prompt-form');
    const promptInput = document.getElementById('prompt-input');
    const newChatBtn = document.getElementById('new-chat-btn');
    const historyBtn = document.getElementById('history-btn');
    const historyList = document.getElementById('history-list');
    const menuBtn = document.getElementById('menu-btn');
    const closeSidebarBtn = document.getElementById('close-sidebar-btn');
    const sidebarOverlay = document.getElementById('sidebar-overlay');
    const profileBtn = document.getElementById('profile-icon-btn');
    const profileDropdown = document.getElementById('profile-dropdown');

    // === 2. State Aplikasi ===
    let currentConversationId = null;
    let isLoading = false;

    // === 3. Fungsi-fungsi Inti ===

    /** Menampilkan pesan di UI, dengan parsing Markdown untuk AI */
    const appendMessage = (text, sender) => {
        const typingIndicator = chatContainer.querySelector('.typing-indicator');
        if (typingIndicator) typingIndicator.remove();

        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message ${sender}-message`;

        if (sender === 'ai' && window.marked) {
            messageDiv.innerHTML = marked.parse(text, { sanitize: true });
        } else {
            messageDiv.textContent = text;
        }
        
        chatContainer.appendChild(messageDiv);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    };
    
    /** Menampilkan indikator "mengetik..." */
    const showTypingIndicator = () => {
        const indicator = document.createElement('div');
        indicator.className = 'chat-message ai-message typing-indicator';
        indicator.innerHTML = `<div class="typing"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>`;
        chatContainer.appendChild(indicator);
        chatContainer.scrollTop = chatContainer.scrollHeight;
    };

    /** Mengambil dan menampilkan daftar history di sidebar */
    const fetchAndRenderHistory = async () => {
        try {
            const response = await fetch('/history');
            if (!response.ok) throw newError('Gagal mengambil riwayat.');
            
            const conversations = await response.json();
            historyList.innerHTML = '';
            
            if (conversations.length === 0) {
                historyList.innerHTML = '<li class="empty-history">Belum ada riwayat.</li>';
                return;
            }

            conversations.forEach(conv => {
                const li = document.createElement('li');
                li.dataset.id = conv.id;
                if (conv.id == currentConversationId) {
                    li.classList.add('active');
                }
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
    
    /** Memulai sesi chat baru dari awal */
    const startNewChat = () => {
        currentConversationId = null;
        chatContainer.innerHTML = '';
        appendMessage('Halo! Selamat datang di Richatz.AI. Silakan ajukan pertanyaan Anda.', 'ai-system-message');
        promptInput.focus();
        fetchAndRenderHistory(); // Update sidebar untuk menghapus highlight
        toggleSidebar(true); // Selalu tutup sidebar saat chat baru dimulai
    };

    /** Memuat konten dari chat yang dipilih di history */
    const loadConversation = async (id) => {
        if (!id) return;
        currentConversationId = id;
        chatContainer.innerHTML = '';
        showTypingIndicator();

        try {
            const response = await fetch(`/conversation/${id}`);
            if (!response.ok) throw new Error('Gagal memuat percakapan.');
            
            const messages = await response.json();
            chatContainer.innerHTML = ''; 
            
            messages.forEach(msg => {
                appendMessage(msg.content, msg.role === 'assistant' ? 'ai' : 'user');
            });
            promptInput.focus();
            await fetchAndRenderHistory();
        } catch (error) {
            chatContainer.innerHTML = '';
            appendMessage(`Gagal memuat percakapan. ${error.message}`, 'ai-system-message');
        }
    };

    /** Menghapus percakapan */
    const handleDelete = async (id, listItemElement) => {
        if (!confirm('Anda yakin ingin menghapus percakapan ini secara permanen?')) return;
        try {
            await fetch(`/delete_conversation/${id}`, { method: 'DELETE' });
            listItemElement.remove();
            if (historyList.children.length === 0) {
                historyList.innerHTML = '<li class="empty-history">Belum ada riwayat.</li>';
            }
            if (currentConversationId == id) {
                startNewChat();
            }
        } catch (error) {
            console.error('Error deleting conversation:', error);
            alert('Gagal menghapus percakapan.');
        }
    };

    /** Mengatur buka/tutup sidebar */
    const toggleSidebar = (forceClose = false) => {
        if (forceClose) {
            document.body.classList.remove('sidebar-open');
            sidebarOverlay.classList.remove('active');
        } else {
            document.body.classList.toggle('sidebar-open');
            sidebarOverlay.classList.toggle('active');
        }
    };
    
    // === 4. Event Listeners ===

    /** Mengirim pesan ke backend */
    promptForm.addEventListener('submit', async (e) => {
        e.preventDefault(); 
        const userText = promptInput.value.trim();
        if (userText === '' || isLoading) return;

        // Jika belum ada chat, buat dulu
        if (!currentConversationId) {
            try {
                const newChatResponse = await fetch('/new_chat', { method: 'POST' });
                const newChatData = await newChatResponse.json();
                if (!newChatData.conversation_id) throw new Error('Gagal membuat sesi chat baru.');
                currentConversationId = newChatData.conversation_id;
                chatContainer.innerHTML = ''; // Hapus pesan selamat datang
                await fetchAndRenderHistory();
            } catch (error) {
                appendMessage(`Maaf, terjadi kesalahan: ${error.message}`, 'ai-system-message');
                return;
            }
        }
        
        isLoading = true;
        appendMessage(userText, 'user'); 
        promptInput.value = ''; 
        showTypingIndicator();

        try {
            const response = await fetch('/ask', { 
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt: userText, conversation_id: currentConversationId }),
            });

            if (!response.ok) throw new Error('Respons dari server tidak baik.');
            const data = await response.json();
            appendMessage(data.answer, 'ai');

            await fetchAndRenderHistory();

        } catch (error) {
            appendMessage(`Maaf, terjadi kesalahan: ${error.message}`, 'ai-system-message'); 
        } finally {
            isLoading = false;
        }
    });

    /** Listener untuk tombol-tombol utama */
    newChatBtn.addEventListener('click', startNewChat);
    
    const openHistorySidebar = async () => {
        await fetchAndRenderHistory();
        toggleSidebar();
    };
    
    historyBtn.addEventListener('click', openHistorySidebar);
    if(menuBtn) menuBtn.addEventListener('click', openHistorySidebar);
    
    closeSidebarBtn.addEventListener('click', () => toggleSidebar(true));
    sidebarOverlay.addEventListener('click', () => toggleSidebar(true));

    /** Listener untuk daftar history (memuat dan menghapus) */
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
    
    /** Listener untuk dropdown profil */
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

    // === 5. Inisialisasi Aplikasi ===
    startNewChat();
});