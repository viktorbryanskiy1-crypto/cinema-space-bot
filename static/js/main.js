// main.js — полный рабочий файл с оптимизацией Telegram WebApp и fullscreen

// Глобальные переменные
let currentTab = 'moments';
let userId = 'user_' + Math.random().toString(36).substr(2, 9);

// Флаги для предотвращения множественных обработчиков
let modalClickHandlerAdded = false;
let formToggleHandlerAdded = false;

document.addEventListener('DOMContentLoaded', function() {
    console.log("DOMContentLoaded сработал");

    // --- Telegram WebApp ---
    if (window.Telegram && window.Telegram.WebApp) {
        const webApp = window.Telegram.WebApp;

        try {
            webApp.ready(); // уведомляем Telegram, что приложение готово

            // Попытка fullscreen (максимальный размер)
            if (webApp.requestFullscreen) {
                webApp.requestFullscreen();
            } else {
                webApp.expand(); // fallback
            }

            webApp.enableClosingConfirmation();
            webApp.setHeaderColor('#0f0c29');
            webApp.setBackgroundColor('#0f0c29');
            webApp.MainButton.hide(); // скрыть нижнюю кнопку
            console.log("Telegram WebApp инициализирован и расширен до полного экрана");
        } catch (error) {
            console.error("Ошибка инициализации Telegram WebApp:", error);
        }
    } else {
        console.warn("Telegram WebApp API недоступен");
    }

    // --- Вкладки ---
    const contentArea = document.getElementById('content-area');
    if (!contentArea) {
        console.error('Элемент content-area не найден');
        return;
    }

    const tabBtns = document.querySelectorAll('.tab-btn[data-tab]'); // Только кнопки вкладок

    async function loadTabContent(tabName) {
        try {
            contentArea.innerHTML = `
                <div style="text-align: center; padding: 50px; color: var(--accent);">
                    <div>🌀 Загрузка ${tabName}...</div>
                </div>
            `;

            const response = await fetch(`/${tabName}`);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const html = await response.text();
            contentArea.innerHTML = html;
            currentTab = tabName;
            addDynamicFeatures();
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

    tabBtns.forEach(btn => {
        btn.addEventListener('click', function () {
            tabBtns.forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            loadTabContent(this.dataset.tab);
        });
    });

    // --- Поиск ---
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
                    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
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

    if (searchInput) {
        searchInput.addEventListener('keypress', function (e) {
            if (e.key === 'Enter') {
                if (searchBtn) searchBtn.click();
            }
        });
    }

    // --- Инициализация вкладки ---
    if (tabBtns.length > 0) {
        tabBtns[0].classList.add('active');
        loadTabContent(tabBtns[0].dataset.tab);
    } else {
        console.log("Кнопки вкладок не найдены на главной странице.");
    }

    // --- Обработчики форм добавления контента ---
    setupFormSubmissions();
});

// --- Динамические функции после загрузки контента ---
function addDynamicFeatures() {
    addReactionHandlers();
    addCommentHandlers();
    addLoadCommentsHandlers();
    addModalHandlers();
    setupFormToggles();
}

// --- Реакции ---
function addReactionHandlers() {
    document.querySelectorAll('.reaction-btn').forEach(btn => {
        const clone = btn.cloneNode(true);
        btn.parentNode.replaceChild(clone, btn);

        clone.addEventListener('click', async function () {
            const itemId = this.dataset.id;
            const itemType = this.dataset.type;
            const reaction = this.dataset.reaction;

            this.style.transform = 'scale(1.3)';
            this.style.boxShadow = '0 0 20px rgba(0, 243, 255, 0.8)';

            try {
                const response = await fetch('/api/reaction', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        item_type: itemType,
                        item_id: parseInt(itemId),
                        user_id: userId,
                        reaction: reaction
                    })
                });

                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                const result = await response.json();
                if (result.success) {
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

// --- Комментарии ---
function addCommentHandlers() {
    document.querySelectorAll('.comment-form').forEach(form => {
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
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            item_type: itemType,
                            item_id: parseInt(itemId),
                            user_name: 'Гость',
                            text: comment
                        })
                    });

                    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                    const result = await response.json();
                    if (result.success) {
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
                            commentsList.firstChild
                                ? commentsList.insertBefore(newComment, commentsList.firstChild)
                                : commentsList.appendChild(newComment);
                        }
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

// --- Загрузка комментариев ---
function addLoadCommentsHandlers() {
    document.querySelectorAll('.load-comments').forEach(btn => {
        const clone = btn.cloneNode(true);
        btn.parentNode.replaceChild(clone, btn);

        clone.addEventListener('click', async function () {
            const itemId = this.dataset.id;
            const itemType = this.dataset.type;
            const commentsList = this.nextElementSibling;

            if (!commentsList) return console.error('Список комментариев не найден');

            try {
                const response = await fetch(`/api/comments?type=${itemType}&id=${itemId}`);
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
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
                } else {
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

// --- Модальные окна ---
// Глобальные функции для открытия модалок
function showAddMomentModal() {
    showModal('add-moment-modal');
}
function showAddTrailerModal() {
    showModal('add-trailer-modal');
}
function showAddNewsModal() {
    showModal('add-news-modal');
}
function showModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.style.display = 'flex';
}
function closeModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.style.display = 'none';
}

function addModalHandlers() {
    // Убираем клонирование и добавляем обработчики только если они еще не добавлены
    if (!modalClickHandlerAdded) {
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
                // Проверяем, не добавлен ли уже обработчик
                if (!element.dataset.handlerAdded) {
                    element.addEventListener('click', handler);
                    element.dataset.handlerAdded = 'true'; // Флаг для предотвращения дублирования
                }
            }
        });

        // Обработчик закрытия модалки при клике вне окна
        document.addEventListener('click', function (e) {
            if (e.target.classList && e.target.classList.contains('modal')) {
                e.target.style.display = 'none';
            }
        });
        modalClickHandlerAdded = true;
    }
}

// --- Вспомогательные ---
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

// --- Переключение форм ---
function setupFormToggles() {
    if (!formToggleHandlerAdded) {
        document.addEventListener('change', function (e) {
            const target = e.target;

            const toggleSections = [
                { modalId: 'add-moment-modal', typeName: 'video_type', fileId: 'moment-file-section', urlId: 'moment-url-section' },
                { modalId: 'add-trailer-modal', typeName: 'video_type', fileId: 'trailer-file-section', urlId: 'trailer-url-section' },
                { modalId: 'add-news-modal', typeName: 'image_type', fileId: 'news-file-section', urlId: 'news-url-section' }
            ];

            toggleSections.forEach(({ modalId, typeName, fileId, urlId }) => {
                if (target.name === typeName && target.closest(`#${modalId}`)) {
                    const fileSection = document.getElementById(fileId);
                    const urlSection = document.getElementById(urlId);
                    if (fileSection && urlSection) {
                        if (target.value === 'upload') {
                            fileSection.style.display = 'block';
                            urlSection.style.display = 'none';
                        } else {
                            fileSection.style.display = 'none';
                            urlSection.style.display = 'block';
                        }
                    }
                }
            });
        });
        formToggleHandlerAdded = true;
    }
}

// --- Формы добавления контента ---
function setupFormSubmissions() {
    // Моменты
    setupContentForm('add-moment-form', 'video_type', '/api/add_moment', 'add-moment-modal');
    // Трейлеры
    setupContentForm('add-trailer-form', 'video_type', '/api/add_trailer', 'add-trailer-modal');
    // Новости
    setupContentForm('add-news-form', 'image_type', '/api/add_news', 'add-news-modal', true);
}

function setupContentForm(formId, typeName, apiUrl, modalId, alwaysFormData=false) {
    const form = document.getElementById(formId);
    if (!form) return;

    const clone = form.cloneNode(true);
    form.parentNode.replaceChild(clone, form);

    clone.addEventListener('submit', async function (e) {
        e.preventDefault();
        const formData = new FormData(this);
        if (alwaysFormData) formData.delete(typeName);

        const typeValue = this.querySelector(`input[name="${typeName}"]:checked`)?.value || 'url';
        try {
            let response;
            if (!alwaysFormData && typeValue === 'upload' && this.querySelector(`input[name="${typeName}_file"]`)?.files[0]) {
                response = await fetch(apiUrl, { method: 'POST', body: formData });
            } else {
                const jsonData = {};
                formData.forEach((v, k) => jsonData[k] = v);
                response = await fetch(apiUrl, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(jsonData) });
            }

            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const result = await response.json();
            if (result.success) {
                closeModal(modalId);
                location.reload();
            } else {
                alert('Ошибка: ' + (result.error || 'Не удалось добавить контент'));
            }
        } catch (error) {
            console.error('Ошибка загрузки:', error);
            alert('Ошибка загрузки: ' + error.message);
        }
    });
}

console.log("main.js загружен и выполняется с fullscreen Telegram WebApp!");
