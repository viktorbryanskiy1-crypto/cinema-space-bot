// main.js — полный рабочий файл с оптимизацией Telegram WebApp и fullscreen
// Обновлен для поддержки автоматического обновления ссылок на видео и улучшенного UX

// Глобальные переменные
let currentTab = 'moments';
let userId = 'user_' + Math.random().toString(36).substr(2, 9);

// Флаги для предотвращения множественных обработчиков
let modalClickHandlerAdded = false;
let formToggleHandlerAdded = false;

// --- Кэш для вкладок ---
let tabCache = {};

// === MODERN PRELOADER LOGIC ===
document.addEventListener('DOMContentLoaded', async function () {
    const preloader = document.getElementById("app-preloader");
    const progressBar = document.querySelector(".progress-fill");
    const content = document.getElementById("app-content");

    if (!preloader || !progressBar || !content) return;

    let progress = 0;

    function setProgress(value, status = "") {
        progress = value;
        progressBar.style.width = value + "%";
        console.log(`Preloader: ${value}% — ${status}`);
    }

    setProgress(10, "Инициализация...");

    // 1. Проверка API
    try {
        const res = await fetch("/health");
        if (res.ok) {
            const data = await res.json();
            console.log("API готов:", data);
            setProgress(40, "API инициализирован");
        } else {
            setProgress(40, "API недоступен, продолжаем...");
        }
    } catch (err) {
        console.warn("API недоступен:", err);
        setProgress(40, "API недоступен");
    }

    // 2. Предзагрузка вкладок
    const tabs = ['moments', 'trailers', 'news'];
    let loaded = 0;

    for (const tab of tabs) {
        try {
            const res = await fetch(`/${tab}`);
            if (res.ok) {
                const html = await res.text();
                sessionStorage.setItem(`tab_${tab}`, html);
                loaded++;
            }
        } catch (err) {
            console.warn(`Ошибка загрузки ${tab}:`, err);
        }
        setProgress(40 + (loaded / tabs.length) * 50, `Загрузка: ${loaded}/${tabs.length}`);
    }

    // 3. Завершение
    setProgress(100, "Готово!");

    setTimeout(() => {
        preloader.classList.add("fade-out");
        setTimeout(() => {
            preloader.style.display = "none";
            content.style.display = "block";
            setTimeout(() => {
                content.classList.add("visible");
            }, 50);
        }, 600);
    }, 500);

    // === ORIGINAL MAIN LOGIC (остаётся после preloader) ===
    initializeApp();
});

function initializeApp() {
    console.log("App initialized, running main logic...");

    // --- Telegram WebApp ---
    if (window.Telegram && window.Telegram.WebApp) {
        const webApp = window.Telegram.WebApp;
        try {
            webApp.ready();
            if (webApp.requestFullscreen) {
                webApp.requestFullscreen();
            } else {
                webApp.expand();
            }
            webApp.enableClosingConfirmation();
            webApp.setHeaderColor('#0f0c29');
            webApp.setBackgroundColor('#0f0c29');
            webApp.MainButton.hide();
            console.log("Telegram WebApp инициализирован");
        } catch (error) {
            console.error("Ошибка инициализации Telegram WebApp:", error);
        }
    }

    // --- Вкладки ---
    const contentArea = document.getElementById('content-area');
    const tabBtns = document.querySelectorAll('.tab-btn[data-tab]');

    async function loadTabContent(tabName) {
        try {
            if (tabCache[tabName]) {
                contentArea.innerHTML = tabCache[tabName];
                currentTab = tabName;
                addDynamicFeatures();
                return;
            }

            contentArea.innerHTML = `
                <div style="text-align: center; padding: 50px; color: var(--accent);">
                    <div class="ultra-modern-spinner" style="margin: 0 auto 20px;"></div>
                    <div>🌀 Загрузка ${tabName}...</div>
                </div>
            `;

            const response = await fetch(`/${tabName}`);
            const html = await response.text();
            tabCache[tabName] = html;
            contentArea.innerHTML = html;
            currentTab = tabName;
            addDynamicFeatures();
        } catch (error) {
            contentArea.innerHTML = `
                <div style="text-align: center; padding: 50px; color: var(--warning);">
                    <h2>❌ Ошибка загрузки</h2>
                    <p>Не удалось загрузить контент "${tabName}". Попробуйте позже.</p>
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

    if (tabBtns.length > 0) {
        tabBtns[0].classList.add('active');
        loadTabContent(tabBtns[0].dataset.tab);
    }

    setupFormSubmissions();

    setTimeout(() => {
        ['trailers', 'news'].forEach(tabName => {
            fetch(`/${tabName}`).then(r => r.text()).then(html => {
                tabCache[tabName] = html;
            });
        });
    }, 2000);
}

// === ОСТАЛЬНЫЕ ФУНКЦИИ (addReactionHandlers, addCommentHandlers и т.д.) ===
// ... (все твои функции: addDynamicFeatures, addReactionHandlers и т.д.) ...
// ВСЁ ОСТАЁТСЯ БЕЗ ИЗМЕНЕНИЙ — просто вставь свой полный код сюда

// Пример (вставь ВЕСЬ оставшийся код):
function addDynamicFeatures() {
    addReactionHandlers();
    addCommentHandlers();
    addLoadCommentsHandlers();
    addModalHandlers();
    setupFormToggles();
    initializeVideoErrorHandling();
}

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

// --- НОВАЯ ФУНКЦИЯ: Обработка ошибок воспроизведения видео ---
function initializeVideoErrorHandling() {
    // Добавляем обработчики ошибок для всех видеоэлементов
    document.querySelectorAll('video').forEach(video => {
        video.addEventListener('error', async function(e) {
            console.log('Ошибка воспроизведения видео:', e);
            
            // Получаем родительский элемент
            const parent = this.parentNode;
            
            // Создаем элемент прелоадера
            const loader = document.createElement('div');
            loader.className = 'video-loader';
            loader.innerHTML = `
                <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 300px; background: rgba(15, 12, 41, 0.8); border-radius: 10px; margin: 10px 0;">
                    <div class="ultra-modern-spinner"></div>
                    <div style="margin-top: 15px; color: #00f3ff;">🔄 Обновление видео...</div>
                </div>
            `;
            
            // Заменяем видео на прелоадер
            parent.replaceChild(loader, this);
            
            try {
                // Получаем источник видео
                const videoSrc = this.querySelector('source')?.src || this.src;
                if (videoSrc && videoSrc.includes('api.telegram.org/file')) {
                    // Отправляем запрос на обновление ссылки
                    const response = await fetch('/api/refresh_video_url', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            post_url: videoSrc
                        })
                    });
                    
                    const result = await response.json();
                    
                    if (result.success && result.new_url) {
                        // Создаем новый видеоэлемент с обновленной ссылкой
                        const newVideo = document.createElement('video');
                        newVideo.controls = true;
                        newVideo.preload = 'metadata';
                        newVideo.style.cssText = 'max-width: 100%; border-radius: 10px; width: 100%; height: auto;';
                        
                        const source = document.createElement('source');
                        source.src = result.new_url;
                        source.type = 'video/mp4';
                        
                        newVideo.appendChild(source);
                        
                        // Добавляем обработчик ошибок для нового видео
                        newVideo.addEventListener('error', function(e) {
                            console.log('Ошибка воспроизведения обновленного видео:', e);
                            const errorNotice = document.createElement('div');
                            errorNotice.className = 'video-error-notice';
                            errorNotice.innerHTML = `
                                <div style="background: rgba(255, 0, 0, 0.2); padding: 15px; border-radius: 8px; margin: 10px 0; color: #ff4444; text-align: center;">
                                    <div style="font-size: 24px; margin-bottom: 10px;">❌</div>
                                    <div>Не удалось воспроизвести видео</div>
                                    <div style="font-size: 12px; margin-top: 5px;">Попробуйте обновить страницу или попробовать позже</div>
                                </div>
                            `;
                            parent.replaceChild(errorNotice, newVideo);
                        });
                        
                        // Заменяем прелоадер на новое видео
                        parent.replaceChild(newVideo, loader);
                        
                        // Загружаем и воспроизводим видео
                        newVideo.load();
                        
                        console.log('Видео успешно обновлено');
                    } else {
                        // Показываем ошибку
                        const errorNotice = document.createElement('div');
                        errorNotice.className = 'video-error-notice';
                        errorNotice.innerHTML = `
                            <div style="background: rgba(255, 0, 0, 0.2); padding: 15px; border-radius: 8px; margin: 10px 0; color: #ff4444; text-align: center;">
                                <div style="font-size: 24px; margin-bottom: 10px;">❌</div>
                                <div>Не удалось обновить видео</div>
                                <div style="font-size: 12px; margin-top: 5px;">${result.error || 'Попробуйте позже'}</div>
                            </div>
                        `;
                        parent.replaceChild(errorNotice, loader);
                    }
                } else {
                    // Если это не Telegram ссылка, показываем общую ошибку
                    const errorNotice = document.createElement('div');
                    errorNotice.className = 'video-error-notice';
                    errorNotice.innerHTML = `
                        <div style="background: rgba(255, 0, 0, 0.2); padding: 15px; border-radius: 8px; margin: 10px 0; color: #ff4444; text-align: center;">
                            <div style="font-size: 24px; margin-bottom: 10px;">❌</div>
                            <div>Ошибка воспроизведения видео</div>
                            <div style="font-size: 12px; margin-top: 5px;">Неподдерживаемый формат или файл недоступен</div>
                        </div>
                    `;
                    parent.replaceChild(errorNotice, loader);
                }
            } catch (refreshError) {
                console.error('Ошибка при обновлении видео:', refreshError);
                const errorNotice = document.createElement('div');
                errorNotice.className = 'video-error-notice';
                errorNotice.innerHTML = `
                    <div style="background: rgba(255, 0, 0, 0.2); padding: 15px; border-radius: 8px; margin: 10px 0; color: #ff4444; text-align: center;">
                        <div style="font-size: 24px; margin-bottom: 10px;">🌐</div>
                        <div>Ошибка сети при обновлении</div>
                        <div style="font-size: 12px; margin-top: 5px;">Проверьте подключение и попробуйте позже</div>
                    </div>
                `;
                parent.replaceChild(errorNotice, loader);
            }
        });
    });
}

console.log("main.js загружен и выполняется с fullscreen Telegram WebApp!");
