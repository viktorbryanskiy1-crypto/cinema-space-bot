// Полноэкранный режим при загрузке с логированием
document.addEventListener('DOMContentLoaded', function() {
    console.log("DOMContentLoaded сработал");
    
    if (window.Telegram && window.Telegram.WebApp) {
        console.log("Telegram WebApp API доступен");
        
        const webApp = window.Telegram.WebApp;
        
        try {
            webApp.expand();
            console.log("Вызов webApp.expand() выполнен успешно");
        } catch (error) {
            console.error("Ошибка при вызове webApp.expand():", error);
        }
        
        webApp.enableClosingConfirmation();
        webApp.setHeaderColor('#0f0c29');
        webApp.setBackgroundColor('#0f0c29');
        
        console.log("Все методы Telegram WebApp вызваны");
    } else {
        console.warn("Telegram WebApp API недоступен");
    }
});

// Глобальные переменные
let currentTab = 'moments';
let userId = 'user_' + Math.random().toString(36).substr(2, 9);

// Флаги для предотвращения множественных обработчиков
let modalClickHandlerAdded = false;
let formToggleHandlerAdded = false;

// Плавные переходы между вкладками
document.addEventListener('DOMContentLoaded', function () {
    const contentArea = document.getElementById('content-area');
    if (!contentArea) {
        console.error('Элемент content-area не найден');
        return;
    }

    const tabBtns = document.querySelectorAll('.tab-btn[data-tab]'); // Только кнопки вкладок

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
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const html = await response.text();
            contentArea.innerHTML = html;
            currentTab = tabName;
            addDynamicFeatures(); // Добавляем обработчики для нового контента

        } catch (error) {
            console.error(`Ошибка загрузки вкладки "${tabName}":`, error);
            contentArea.innerHTML = `
                <div style="text-align: center; padding: 50px; color: var(--warning);">
                    <h2>❌ Ошибка загрузки</h2>
                    <p>Не удалось загрузить контент "${tabName}". Попробуйте позже.</p>
                    <small>${error.message}</small>
                </div>
            `;
        }
    }

    // Обработчики вкладок
    tabBtns.forEach(btn => {
        btn.addEventListener('click', function () {
            // Убираем активный класс со всех кнопок
            tabBtns.forEach(b => b.classList.remove('active'));
            // Добавляем активный класс текущей кнопке
            this.classList.add('active');
            // Загружаем контент
            loadTabContent(this.dataset.tab);
        });
    });

    // Поиск
    const searchBtn = document.getElementById('search-btn');
    const searchInput = document.getElementById('search-input');
    if (searchBtn) {
        searchBtn.addEventListener('click', async function () {
            const query = searchInput ? searchInput.value.trim() : '';
            if (query) {
                try {
                    contentArea.innerHTML = `
                        <div style="text-align: center; padding: 50px; color: var(--accent);">
                            <div>🌀 Поиск по запросу: "${query}"...</div>
                        </div>
                    `;

                    const response = await fetch(`/search?q=${encodeURIComponent(query)}`);
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    const html = await response.text();
                    contentArea.innerHTML = html;
                    addDynamicFeatures();
                } catch (error) {
                    console.error('Ошибка поиска:', error);
                    contentArea.innerHTML = `
                        <div style="text-align: center; padding: 50px; color: var(--warning);">
                            <h2>❌ Ошибка поиска</h2>
                            <p>Не удалось выполнить поиск. Попробуйте позже.</p>
                            <small>${error.message}</small>
                        </div>
                    `;
                }
            }
        });
    }

    // Enter в поиске
    if (searchInput) {
        searchInput.addEventListener('keypress', function (e) {
            if (e.key === 'Enter') {
                if (searchBtn) searchBtn.click();
            }
        });
    }

    // Инициализация: загружаем первую вкладку
    if (tabBtns.length > 0) {
        // Устанавливаем активную первую кнопку
        tabBtns[0].classList.add('active');
        // Загружаем контент первой вкладки
        loadTabContent(tabBtns[0].dataset.tab);
    } else {
        // Если кнопок вкладок нет на главной странице, загружаем контент по умолчанию
        console.log("Кнопки вкладок не найдены на главной странице.");
    }
});

// Добавление динамических функций после загрузки контента
function addDynamicFeatures() {
    addReactionHandlers();
    addCommentHandlers();
    addLoadCommentsHandlers();
    addModalHandlers();
    setupFormToggles();
}

function addReactionHandlers() {
    document.querySelectorAll('.reaction-btn').forEach(btn => {
        // Удаляем предыдущие обработчики для предотвращения дублирования
        const clone = btn.cloneNode(true);
        btn.parentNode.replaceChild(clone, btn);
        
        clone.addEventListener('click', async function () {
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

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

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
}

function addCommentHandlers() {
    document.querySelectorAll('.comment-form').forEach(form => {
        // Удаляем предыдущие обработчики для предотвращения дублирования
        const clone = form.cloneNode(true);
        form.parentNode.replaceChild(clone, form);
        
        clone.addEventListener('submit', async function (e) {
            e.preventDefault();
            const textarea = this.querySelector('textarea');
            const comment = textarea.value.trim();
            const itemId = this.dataset.id;
            const itemType = this.dataset.type;

            if (comment && itemId && itemType) {
                const submitBtn = this.querySelector('.submit-btn');
                const originalText = submitBtn ? submitBtn.textContent : 'Отправить';
                if (submitBtn) {
                    submitBtn.textContent = 'Отправка...';
                    submitBtn.disabled = true;
                }

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

                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }

                    const result = await response.json();
                    if (result.success) {
                        // Добавляем комментарий в DOM
                        const commentsList = this.previousElementSibling;
                        if (commentsList) {
                            const newComment = document.createElement('div');
                            newComment.className = 'comment';
                            newComment.innerHTML = `
                                <div class="comment-text">${escapeHtml(comment)}</div>
                                <div class="comment-meta">
                                    <span>Гость</span>
                                    <span>Только что</span>
                                </div>
                            `;
                            // Вставляем в начало списка комментариев
                            if (commentsList.firstChild) {
                                commentsList.insertBefore(newComment, commentsList.firstChild);
                            } else {
                                commentsList.appendChild(newComment);
                            }
                        }

                        // Очищаем форму
                        textarea.value = '';
                    }
                } catch (error) {
                    console.error('Ошибка при добавлении комментария:', error);
                } finally {
                    if (submitBtn) {
                        submitBtn.textContent = originalText;
                        submitBtn.disabled = false;
                    }
                }
            }
        });
    });
}

function addLoadCommentsHandlers() {
    document.querySelectorAll('.load-comments').forEach(btn => {
        // Удаляем предыдущие обработчики для предотвращения дублирования
        const clone = btn.cloneNode(true);
        btn.parentNode.replaceChild(clone, btn);
        
        clone.addEventListener('click', async function () {
            const itemId = this.dataset.id;
            const itemType = this.dataset.type;
            const commentsList = this.nextElementSibling;

            if (!commentsList) {
                console.error('Список комментариев не найден');
                return;
            }

            try {
                const response = await fetch(`/api/comments?type=${itemType}&id=${itemId}`);
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
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
                    // Скрываем кнопку после загрузки
                    this.style.display = 'none';
                } else {
                    // Если комментариев нет, показываем сообщение или просто скрываем кнопку
                    commentsList.innerHTML = '<p>Комментариев пока нет.</p>';
                    this.style.display = 'none';
                }
            } catch (error) {
                console.error('Ошибка при загрузке комментариев:', error);
                commentsList.innerHTML = '<p>Ошибка загрузки комментариев.</p>';
            }
        });
    });
}

function addModalHandlers() {
    const modalButtons = [
        { id: 'add-moment-btn', handler: showAddMomentModal },
        { id: 'add-moment-btn-alt', handler: showAddMomentModal },
        { id: 'add-trailer-btn', handler: showAddTrailerModal },
        { id: 'add-trailer-btn-alt', handler: showAddTrailerModal },
        { id: 'add-news-btn', handler: showAddNewsModal },
        { id: 'add-news-btn-alt', handler: showAddNewsModal }
    ];

    modalButtons.forEach(({ id, handler }) => {
        const element = document.getElementById(id);
        if (element) {
            // Удаляем предыдущие обработчики и добавляем новые
            const clone = element.cloneNode(true);
            element.parentNode.replaceChild(clone, element);
            clone.addEventListener('click', handler);
        }
    });

    // Закрытие модального окна при клике вне его
    if (!modalClickHandlerAdded) {
        document.addEventListener('click', function (e) {
            if (e.target.classList.contains('modal')) {
                e.target.style.display = 'none';
            }
        });
        modalClickHandlerAdded = true;
    }
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

// Функция для добавления нового контента (заглушка)
function addNewItem(type) {
    alert(`Функция добавления ${type} будет доступна позже!`);
}

// --- Функции для работы с модальными окнами ---
function showAddMomentModal() {
    const modal = document.getElementById('add-moment-modal');
    if (modal) {
        modal.style.display = 'flex';
    } else {
        console.warn('Модальное окно моментов не найдено');
    }
}

function showAddTrailerModal() {
    const modal = document.getElementById('add-trailer-modal');
    if (modal) {
        modal.style.display = 'flex';
    } else {
        console.warn('Модальное окно трейлеров не найдено');
    }
}

function showAddNewsModal() {
    const modal = document.getElementById('add-news-modal');
    if (modal) {
        modal.style.display = 'flex';
    } else {
        console.warn('Модальное окно новостей не найдено');
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
    }
}

// --- Функции для переключения форм ---
function setupFormToggles() {
    if (!formToggleHandlerAdded) {
        document.addEventListener('change', function (e) {
            // Переключение между загрузкой и URL для моментов
            if (e.target.name === 'video_type' && e.target.closest('#add-moment-modal')) {
                const fileSection = document.getElementById('moment-file-section');
                const urlSection = document.getElementById('moment-url-section');
                if (fileSection && urlSection) {
                    if (e.target.value === 'upload') {
                        fileSection.style.display = 'block';
                        urlSection.style.display = 'none';
                    } else {
                        fileSection.style.display = 'none';
                        urlSection.style.display = 'block';
                    }
                }
            }

            // Переключение между загрузкой и URL для трейлеров
            if (e.target.name === 'video_type' && e.target.closest('#add-trailer-modal')) {
                const fileSection = document.getElementById('trailer-file-section');
                const urlSection = document.getElementById('trailer-url-section');
                if (fileSection && urlSection) {
                    if (e.target.value === 'upload') {
                        fileSection.style.display = 'block';
                        urlSection.style.display = 'none';
                    } else {
                        fileSection.style.display = 'none';
                        urlSection.style.display = 'block';
                    }
                }
            }

            // Переключение между загрузкой и URL для новостей
            if (e.target.name === 'image_type' && e.target.closest('#add-news-modal')) {
                const fileSection = document.getElementById('news-file-section');
                const urlSection = document.getElementById('news-url-section');
                if (fileSection && urlSection) {
                    if (e.target.value === 'upload') {
                        fileSection.style.display = 'block';
                        urlSection.style.display = 'none';
                    } else {
                        fileSection.style.display = 'none';
                        urlSection.style.display = 'block';
                    }
                }
            }
        });
        formToggleHandlerAdded = true;
    }
}

// --- Обработчики форм добавления контента ---
// Этот блок выполняется после полной загрузки DOM
document.addEventListener('DOMContentLoaded', function () {
    // Обработчик формы добавления момента
    const momentForm = document.getElementById('add-moment-form');
    if (momentForm) {
        // Удаляем предыдущие обработчики для предотвращения дублирования
        const clone = momentForm.cloneNode(true);
        momentForm.parentNode.replaceChild(clone, momentForm);
        
        clone.addEventListener('submit', async function (e) {
            e.preventDefault();

            const formData = new FormData(this);
            const videoType = this.querySelector('input[name="video_type"]:checked')?.value || 'url';

            try {
                let response;
                if (videoType === 'upload' && this.querySelector('input[name="video_file"]')?.files[0]) {
                    // Загрузка файла
                    response = await fetch('/api/add_moment', {
                        method: 'POST',
                        body: formData
                    });
                } else {
                    // Отправка URL в формате JSON
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

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const result = await response.json();
                if (result.success) {
                    closeModal('add-moment-modal');
                    location.reload();
                } else {
                    alert('Ошибка: ' + (result.error || 'Не удалось добавить момент'));
                }
            } catch (error) {
                console.error('Ошибка загрузки:', error);
                alert('Ошибка загрузки: ' + error.message);
            }
        });
    }

    // Обработчик формы добавления трейлера
    const trailerForm = document.getElementById('add-trailer-form');
    if (trailerForm) {
        // Удаляем предыдущие обработчики для предотвращения дублирования
        const clone = trailerForm.cloneNode(true);
        trailerForm.parentNode.replaceChild(clone, trailerForm);
        
        clone.addEventListener('submit', async function (e) {
            e.preventDefault();

            const formData = new FormData(this);
            const videoType = this.querySelector('input[name="video_type"]:checked')?.value || 'url';

            try {
                let response;
                if (videoType === 'upload' && this.querySelector('input[name="video_file"]')?.files[0]) {
                    // Загрузка файла
                    response = await fetch('/api/add_trailer', {
                        method: 'POST',
                        body: formData
                    });
                } else {
                    // Отправка URL в формате JSON
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

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const result = await response.json();
                if (result.success) {
                    closeModal('add-trailer-modal');
                    location.reload();
                } else {
                    alert('Ошибка: ' + (result.error || 'Не удалось добавить трейлер'));
                }
            } catch (error) {
                console.error('Ошибка загрузки:', error);
                alert('Ошибка загрузки: ' + error.message);
            }
        });
    }

    // Обработчик формы добавления новости
    const newsForm = document.getElementById('add-news-form');
    if (newsForm) {
        // Удаляем предыдущие обработчики для предотвращения дублирования
        const clone = newsForm.cloneNode(true);
        newsForm.parentNode.replaceChild(clone, newsForm);
        
        clone.addEventListener('submit', async function (e) {
            e.preventDefault();

            // Для новостей всегда используем FormData, так как может быть файл
            const formData = new FormData(this);
            // image_type не передается на сервер, удалим его из FormData
            formData.delete('image_type');

            try {
                const response = await fetch('/api/add_news', {
                    method: 'POST',
                    body: formData
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                const result = await response.json();
                if (result.success) {
                    closeModal('add-news-modal');
                    location.reload();
                } else {
                    alert('Ошибка: ' + (result.error || 'Не удалось добавить новость'));
                }
            } catch (error) {
                console.error('Ошибка загрузки:', error);
                alert('Ошибка загрузки: ' + error.message);
            }
        });
    }
});

console.log("main.js загружен и выполняется!");
