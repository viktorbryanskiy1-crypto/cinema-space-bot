// main.js — полный рабочий файл с оптимизацией Telegram WebApp и fullscreen
// Обновлен для поддержки автоматического обновления ссылок на видео и масштабирования

// Глобальные переменные
let currentTab = 'moments';
let userId = 'user_' + Math.random().toString(36).substr(2, 9);

// Флаги для предотвращения множественных обработчиков
let modalClickHandlerAdded = false;
let formToggleHandlerAdded = false;

// --- ОПТИМИЗАЦИЯ: Локальное кэширование ---
const localCache = {
    videos: new Map(),
    set(key, value, ttl = 3600000) { // 1 час по умолчанию
        const item = {
            value: value,
            expiry: Date.now() + ttl,
        };
        this.videos.set(key, item);
        try {
            localStorage.setItem('cinema_cache_' + key, JSON.stringify(item));
        } catch (e) {
            console.warn('Не удалось сохранить в localStorage:', e);
        }
    },
    get(key) {
        // Проверяем память
        if (this.videos.has(key)) {
            const item = this.videos.get(key);
            if (Date.now() < item.expiry) {
                return item.value;
            } else {
                this.videos.delete(key);
            }
        }
        
        // Проверяем localStorage
        try {
            const itemStr = localStorage.getItem('cinema_cache_' + key);
            if (itemStr) {
                const item = JSON.parse(itemStr);
                if (Date.now() < item.expiry) {
                    this.videos.set(key, item);
                    return item.value;
                } else {
                    localStorage.removeItem('cinema_cache_' + key);
                }
            }
        } catch (e) {
            console.warn('Ошибка при чтении из localStorage:', e);
        }
        
        return null;
    }
};

document.addEventListener('DOMContentLoaded', function() {
    console.log("DOMContentLoaded сработал");

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

    const tabBtns = document.querySelectorAll('.tab-btn[data-tab]');

    // --- ОПТИМИЗАЦИЯ: Предзагрузка популярного контента ---
    function preloadPopularContent() {
        // Предзагрузка ссылок на популярные видео
        const popularVideos = document.querySelectorAll('.popular-video');
        popularVideos.forEach(video => {
            if (video.dataset.videoUrl) {
                const link = document.createElement('link');
                link.rel = 'prefetch';
                link.href = video.dataset.videoUrl;
                document.head.appendChild(link);
            }
        });
    }

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
            
            // Предзагрузка после загрузки контента
            setTimeout(preloadPopularContent, 1000);
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

    if (tabBtns.length > 0) {
        tabBtns[0].classList.add('active');
        loadTabContent(tabBtns[0].dataset.tab);
    } else {
        console.log("Кнопки вкладок не найдены на главной странице.");
    }

    setupFormSubmissions();
});

function addDynamicFeatures() {
    addReactionHandlers();
    addCommentHandlers();
    addLoadCommentsHandlers();
    addModalHandlers();
    setupFormToggles();
    initializeVideoErrorHandling();
    
    // --- ОПТИМИЗАЦИЯ: Ленивая загрузка изображений ---
    const lazyImages = document.querySelectorAll('img[loading="lazy"]');
    if ('IntersectionObserver' in window) {
        const imageObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    img.src = img.dataset.src;
                    img.classList.remove('lazy');
                    imageObserver.unobserve(img);
                }
            });
        });
        
        lazyImages.forEach(img => imageObserver.observe(img));
    }
}

// --- НОВАЯ ФУНКЦИЯ: Обработка ошибок воспроизведения видео ---
function initializeVideoErrorHandling() {
    document.querySelectorAll('video').forEach(video => {
        video.addEventListener('error', async function(e) {
            console.log('Ошибка воспроизведения видео:', e);
            
            const parent = this.parentNode;
            const loader = document.createElement('div');
            loader.className = 'video-loader';
            loader.innerHTML = `
                <div>
                    <div class="spinner"></div>
                    <div class="text">Обновление видео...</div>
                </div>
            `;
            
            parent.replaceChild(loader, this);
            
            try {
                const videoSrc = this.querySelector('source')?.src || this.src;
                if (videoSrc && videoSrc.includes('api.telegram.org/file')) {
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
                        const newVideo = document.createElement('video');
                        newVideo.controls = true;
                        newVideo.preload = 'metadata';
                        newVideo.style.cssText = 'max-width: 100%; border-radius: 10px; width: 100%; height: auto;';
                        
                        const source = document.createElement('source');
                        source.src = result.new_url;
                        source.type = 'video/mp4';
                        
                        newVideo.appendChild(source);
                        
                        newVideo.addEventListener('error', function(e) {
                            console.log('Ошибка воспроизведения обновленного видео:', e);
                            const errorNotice = document.createElement('div');
                            errorNotice.className = 'video-error-notice';
                            errorNotice.innerHTML = `
                                <div class="error-icon">❌</div>
                                <div class="error-message">Не удалось воспроизвести видео</div>
                                <div class="error-detail">Попробуйте обновить страницу или попробовать позже</div>
                            `;
                            parent.replaceChild(errorNotice, newVideo);
                        });
                        
                        parent.replaceChild(newVideo, loader);
                        newVideo.load();
                        
                        console.log('Видео успешно обновлено');
                    } else {
                        const errorNotice = document.createElement('div');
                        errorNotice.className = 'video-error-notice';
                        errorNotice.innerHTML = `
                            <div class="error-icon">❌</div>
                            <div class="error-message">Не удалось обновить видео</div>
                            <div class="error-detail">${result.error || 'Попробуйте позже'}</div>
                        `;
                        parent.replaceChild(errorNotice, loader);
                    }
                } else {
                    const errorNotice = document.createElement('div');
                    errorNotice.className = 'video-error-notice';
                    errorNotice.innerHTML = `
                        <div class="error-icon">❌</div>
                        <div class="error-message">Ошибка воспроизведения видео</div>
                        <div class="error-detail">Неподдерживаемый формат или файл недоступен</div>
                    `;
                    parent.replaceChild(errorNotice, loader);
                }
            } catch (refreshError) {
                console.error('Ошибка при обновлении видео:', refreshError);
                const errorNotice = document.createElement('div');
                errorNotice.className = 'video-error-notice';
                errorNotice.innerHTML = `
                    <div class="error-icon">🌐</div>
                    <div class="error-message">Ошибка сети при обновлении</div>
                    <div class="error-detail">Проверьте подключение и попробуйте позже</div>
                `;
                parent.replaceChild(errorNotice, loader);
            }
        });
    });
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

function showModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.style.display = 'flex';
}

function closeModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.style.display = 'none';
}

function showAddMomentModal() {
    showModal('add-moment-modal');
}

function showAddTrailerModal() {
    showModal('add-trailer-modal');
}

function showAddNewsModal() {
    showModal('add-news-modal');
}

function addModalHandlers() {
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
                if (!element.dataset.handlerAdded) {
                    element.addEventListener('click', handler);
                    element.dataset.handlerAdded = 'true';
                }
            }
        });

        document.addEventListener('click', function (e) {
            if (e.target.classList && e.target.classList.contains('modal')) {
                e.target.style.display = 'none';
            }
        });
        modalClickHandlerAdded = true;
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

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

function setupFormSubmissions() {
    setupContentForm('add-moment-form', 'video_type', '/api/add_moment', 'add-moment-modal');
    setupContentForm('add-trailer-form', 'video_type', '/api/add_trailer', 'add-trailer-modal');
    setupContentForm('add-news-form', 'image_type', '/api/add_news', 'add-news-modal', true);
}

console.log("main.js загружен и выполняется с fullscreen Telegram WebApp!");
