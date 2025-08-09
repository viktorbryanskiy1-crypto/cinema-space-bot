// Глобальные переменные
let currentTab = 'moments';
let userId = 'user_' + Math.random().toString(36).substr(2, 9);

// Плавные переходы между вкладками
document.addEventListener('DOMContentLoaded', function() {
    const tabBtns = document.querySelectorAll('.tab-btn');
    const contentArea = document.getElementById('content-area');
    
    // Загрузка контента для активной вкладки
    async function loadTabContent(tabName) {
        try {
            // Показываем индикатор загрузки
            contentArea.innerHTML = `
                <div style="text-align: center; padding: 50px; color: var(--accent);">
                    <div>🌀 Загрузка ${tabName}...</div>
                </div>
            `;
            
            // Загружаем реальный контент
            const response = await fetch(`/${tabName}`);
            const html = await response.text();
            contentArea.innerHTML = html;
            currentTab = tabName;
            addDynamicFeatures();
            
        } catch (error) {
            contentArea.innerHTML = `
                <div style="text-align: center; padding: 50px; color: var(--warning);">
                    <h2>❌ Ошибка загрузки</h2>
                    <p>Не удалось загрузить контент. Попробуйте позже.</p>
                </div>
            `;
        }
    }
    
    // Обработчики вкладок
    tabBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            tabBtns.forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            loadTabContent(this.dataset.tab);
        });
    });
    
    // Поиск
    document.getElementById('search-btn')?.addEventListener('click', async function() {
        const query = document.getElementById('search-input').value.trim();
        if (query) {
            try {
                contentArea.innerHTML = `
                    <div style="text-align: center; padding: 50px; color: var(--accent);">
                        <div>🌀 Поиск по запросу: "${query}"...</div>
                    </div>
                `;
                
                const response = await fetch(`/search?q=${encodeURIComponent(query)}`);
                const html = await response.text();
                contentArea.innerHTML = html;
                addDynamicFeatures();
            } catch (error) {
                contentArea.innerHTML = `
                    <div style="text-align: center; padding: 50px; color: var(--warning);">
                        <h2>❌ Ошибка поиска</h2>
                        <p>Не удалось выполнить поиск. Попробуйте позже.</p>
                    </div>
                `;
            }
        }
    });
    
    // Enter в поиске
    document.getElementById('search-input')?.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            document.getElementById('search-btn').click();
        }
    });
    
    // Добавление динамических функций после загрузки контента
    function addDynamicFeatures() {
        // Реакции
        document.querySelectorAll('.reaction-btn').forEach(btn => {
            btn.addEventListener('click', async function() {
                const itemId = this.dataset.id;
                const itemType = this.dataset.type;
                const reaction = this.dataset.reaction;
                
                // Анимация
                this.style.transform = 'scale(1.3)';
                this.style.boxShadow = '0 0 20px rgba(0, 243, 255, 0.8)';
                
                try {
                    const response = await fetch('/api/reaction', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            item_type: itemType,
                            item_id: parseInt(itemId),
                            user_id: userId,
                            reaction: reaction
                        })
                    });
                    
                    const result = await response.json();
                    if (result.success) {
                        // Обновляем счетчик
                        const countSpan = this.querySelector('.reaction-count');
                        if (countSpan) {
                            const currentCount = parseInt(countSpan.textContent) || 0;
                            countSpan.textContent = currentCount + 1;
                        }
                    }
                } catch (error) {
                    console.error('Ошибка при добавлении реакции:', error);
                }
                
                setTimeout(() => {
                    this.style.transform = 'scale(1)';
                    this.style.boxShadow = '';
                }, 300);
            });
        });
        
        // Комментарии
        document.querySelectorAll('.comment-form').forEach(form => {
            form.addEventListener('submit', async function(e) {
                e.preventDefault();
                const textarea = this.querySelector('textarea');
                const comment = textarea.value.trim();
                const itemId = this.dataset.id;
                const itemType = this.dataset.type;
                
                if (comment && itemId && itemType) {
                    const submitBtn = this.querySelector('.submit-btn');
                    const originalText = submitBtn.textContent;
                    submitBtn.textContent = 'Отправка...';
                    submitBtn.disabled = true;
                    
                    try {
                        const response = await fetch('/api/comment', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                            },
                            body: JSON.stringify({
                                item_type: itemType,
                                item_id: parseInt(itemId),
                                user_name: 'Гость',
                                text: comment
                            })
                        });
                        
                        const result = await response.json();
                        if (result.success) {
                            // Добавляем комментарий в DOM
                            const commentsList = this.previousElementSibling;
                            const newComment = document.createElement('div');
                            newComment.className = 'comment';
                            newComment.innerHTML = `
                                <div class="comment-text">${escapeHtml(comment)}</div>
                                <div class="comment-meta">
                                    <span>Гость</span>
                                    <span>Только что</span>
                                </div>
                            `;
                            commentsList.insertBefore(newComment, commentsList.firstChild);
                            
                            // Очищаем форму
                            textarea.value = '';
                        }
                    } catch (error) {
                        console.error('Ошибка при добавлении комментария:', error);
                    } finally {
                        submitBtn.textContent = originalText;
                        submitBtn.disabled = false;
                    }
                }
            });
        });
        
        // Загрузка комментариев
        document.querySelectorAll('.load-comments').forEach(btn => {
            btn.addEventListener('click', async function() {
                const itemId = this.dataset.id;
                const itemType = this.dataset.type;
                const commentsList = this.nextElementSibling;
                
                try {
                    const response = await fetch(`/api/comments?type=${itemType}&id=${itemId}`);
                    const result = await response.json();
                    
                    if (result.comments && result.comments.length > 0) {
                        commentsList.innerHTML = '';
                        result.comments.forEach(comment => {
                            const commentElement = document.createElement('div');
                            commentElement.className = 'comment';
                            commentElement.innerHTML = `
                                <div class="comment-text">${escapeHtml(comment[1])}</div>
                                <div class="comment-meta">
                                    <span>${escapeHtml(comment[0])}</span>
                                    <span>${formatDate(comment[2])}</span>
                                </div>
                            `;
                            commentsList.appendChild(commentElement);
                        });
                        this.style.display = 'none';
                    }
                } catch (error) {
                    console.error('Ошибка при загрузке комментариев:', error);
                }
            });
        });
    }
    
    // Вспомогательные функции
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    function formatDate(dateString) {
        const date = new Date(dateString);
        return date.toLocaleDateString('ru-RU', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric'
        });
    }
    
    // Инициализация
    if (tabBtns.length > 0) {
        tabBtns[0].click(); // Загружаем первую вкладку
    }
    
    addDynamicFeatures();
});

// Функция для добавления нового контента (заглушка)
function addNewItem(type) {
    alert(`Функция добавления ${type} будет доступна позже!`);
}
// Функции для работы с модальными окнами
function showAddMomentModal() {
    document.getElementById('add-moment-modal').style.display = 'flex';
}

function showAddTrailerModal() {
    document.getElementById('add-trailer-modal').style.display = 'flex';
}

function showAddNewsModal() {
    document.getElementById('add-news-modal').style.display = 'flex';
}

function closeModal(modalId) {
    document.getElementById(modalId).style.display = 'none';
}

// Закрытие модального окна при клике вне его
window.addEventListener('click', function(e) {
    const modals = document.querySelectorAll('.modal');
    modals.forEach(modal => {
        if (e.target === modal) {
            modal.style.display = 'none';
        }
    });
});

// Переключение между загрузкой и URL для моментов
document.addEventListener('change', function(e) {
    if (e.target.name === 'video_type' && e.target.closest('#add-moment-modal')) {
        const fileSection = document.getElementById('moment-file-section');
        const urlSection = document.getElementById('moment-url-section');
        if (e.target.value === 'upload') {
            fileSection.style.display = 'block';
            urlSection.style.display = 'none';
        } else {
            fileSection.style.display = 'none';
            urlSection.style.display = 'block';
        }
    }
    
    // Переключение между загрузкой и URL для трейлеров
    if (e.target.name === 'video_type' && e.target.closest('#add-trailer-modal')) {
        const fileSection = document.getElementById('trailer-file-section');
        const urlSection = document.getElementById('trailer-url-section');
        if (e.target.value === 'upload') {
            fileSection.style.display = 'block';
            urlSection.style.display = 'none';
        } else {
            fileSection.style.display = 'none';
            urlSection.style.display = 'block';
        }
    }
    
    // Переключение между загрузкой и URL для новостей
    if (e.target.name === 'image_type' && e.target.closest('#add-news-modal')) {
        const fileSection = document.getElementById('news-file-section');
        const urlSection = document.getElementById('news-url-section');
        if (e.target.value === 'upload') {
            fileSection.style.display = 'block';
            urlSection.style.display = 'none';
        } else {
            fileSection.style.display = 'none';
            urlSection.style.display = 'block';
        }
    }
});

// Обработчики форм добавления контента
document.addEventListener('DOMContentLoaded', function() {
    // Обработчик формы добавления момента
    const momentForm = document.getElementById('add-moment-form');
    if (momentForm) {
        momentForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const formData = new FormData(this);
            const videoType = this.querySelector('input[name="video_type"]:checked').value;
            
            try {
                let response;
                if (videoType === 'upload' && this.querySelector('input[name="video_file"]').files[0]) {
                    // Загрузка файла
                    response = await fetch('/api/add_moment', {
                        method: 'POST',
                        body: formData
                    });
                } else {
                    // Отправка URL
                    const jsonData = {
                        title: formData.get('title'),
                        description: formData.get('description'),
                        video_url: formData.get('video_url') || ''
                    };
                    response = await fetch('/api/add_moment', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify(jsonData)
                    });
                }
                
                const result = await response.json();
                if (result.success) {
                    closeModal('add-moment-modal');
                    location.reload();
                } else {
                    alert('Ошибка: ' + (result.error || 'Не удалось добавить момент'));
                }
            } catch (error) {
                alert('Ошибка загрузки: ' + error.message);
            }
        });
    }
    
    // Обработчик формы добавления трейлера
    const trailerForm = document.getElementById('add-trailer-form');
    if (trailerForm) {
        trailerForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const formData = new FormData(this);
            const videoType = this.querySelector('input[name="video_type"]:checked').value;
            
            try {
                let response;
                if (videoType === 'upload' && this.querySelector('input[name="video_file"]').files[0]) {
                    // Загрузка файла
                    response = await fetch('/api/add_trailer', {
                        method: 'POST',
                        body: formData
                    });
                } else {
                    // Отправка URL
                    const jsonData = {
                        title: formData.get('title'),
                        description: formData.get('description'),
                        video_url: formData.get('video_url') || ''
                    };
                    response = await fetch('/api/add_trailer', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify(jsonData)
                    });
                }
                
                const result = await response.json();
                if (result.success) {
                    closeModal('add-trailer-modal');
                    location.reload();
                } else {
                    alert('Ошибка: ' + (result.error || 'Не удалось добавить трейлер'));
                }
            } catch (error) {
                alert('Ошибка загрузки: ' + error.message);
            }
        });
    }
    
    // Обработчик формы добавления новости
    const newsForm = document.getElementById('add-news-form');
    if (newsForm) {
        newsForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            const formData = new FormData(this);
            
            try {
                const response = await fetch('/api/add_news', {
                    method: 'POST',
                    body: formData
                });
                
                const result = await response.json();
                if (result.success) {
                    closeModal('add-news-modal');
                    location.reload();
                } else {
                    alert('Ошибка: ' + (result.error || 'Не удалось добавить новость'));
                }
            } catch (error) {
                alert('Ошибка загрузки: ' + error.message);
            }
        });
    }
});
