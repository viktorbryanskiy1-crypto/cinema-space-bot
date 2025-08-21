// main.js — полный рабочий файл с оптимизацией Telegram WebApp и fullscreen
// Обновлен для поддержки автоматического обновления ссылок на видео и улучшенного UX
// Исправлен конфликт обработчиков событий для search_by_link.html

// Глобальные переменные
let currentTab = 'moments';
let userId = 'user_' + Math.random().toString(36).substr(2, 9);

// Флаги для предотвращения множественных обработчиков
let modalClickHandlerAdded = false;
let formToggleHandlerAdded = false;

// --- НОВОЕ: Кэш для вкладок ---
let tabCache = {};

// === УЛЬТРАСОВРЕМЕННЫЙ КОСМИЧЕСКИЙ PRELOADER LOGIC ===
document.addEventListener('DOMContentLoaded', async function() {
    console.log("DOMContentLoaded сработал");

    // Инициализация Telegram WebApp (как было)
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

    // === ЛОГИКА КОСМИЧЕСКОГО PRELOADER'А ===
    const preloader = document.getElementById('cosmic-preloader');
    const progressBar = document.getElementById('cosmic-progress-bar');
    const statusText = document.getElementById('cosmic-status');
    const content = document.getElementById('app-content');

    if (!preloader) {
        // Если preloader не найден, просто показываем контент
        if (content) {
            content.style.display = 'block';
            initializeApp();
        }
        return;
    }

    function updatePreloaderProgress(percent, status) {
        if (progressBar) {
            progressBar.style.width = `${percent}%`;
        }
        if (statusText) {
            statusText.textContent = `${percent}% ${status}`;
        }
        console.log(`Космический прогресс: ${percent}% - ${status}`);
    }

    try {
        // 0% - Начало
        updatePreloaderProgress(0, "Инициализация ядра...");

        // 10% - Проверка API
        updatePreloaderProgress(10, "Проверка квантовых связей...");
        await new Promise(resolve => setTimeout(resolve, 300));

        // 20% - Проверка состояния приложения
        try {
            const healthResponse = await fetch('/health');
            if (healthResponse.ok) {
                const healthData = await healthResponse.json();
                console.log("API готов:", healthData);
                updatePreloaderProgress(30, "Квантовые связи установлены");
            } else {
                updatePreloaderProgress(30, "Квантовые связи нестабильны, продолжаем...");
            }
        } catch (err) {
            console.warn("API недоступен:", err);
            updatePreloaderProgress(30, "Квантовые связи нестабильны");
        }

        // 40% - Предзагрузка вкладок
        updatePreloaderProgress(40, "Сканирование галактик...");
        const tabs = ['moments', 'trailers', 'news'];
        let loadedTabs = 0;

        // Параллельная загрузка вкладок
        const tabPromises = tabs.map(async (tab) => {
            try {
                const response = await fetch(`/${tab}`);
                if (response.ok) {
                    const html = await response.text();
                    tabCache[tab] = html;
                    console.log(`Вкладка ${tab} предзагружена`);
                }
            } catch (error) {
                console.error(`Ошибка предзагрузки вкладки ${tab}:`, error);
            }
            loadedTabs++;
            const progress = 40 + Math.floor((loadedTabs / tabs.length) * 50);
            updatePreloaderProgress(progress, `Сканирование: ${loadedTabs}/${tabs.length} галактик`);
        });

        await Promise.all(tabPromises);

        // 90% - Финальная подготовка
        updatePreloaderProgress(90, "Активация двигателей...");
        await new Promise(resolve => setTimeout(resolve, 500));

        // 100% - Готово
        updatePreloaderProgress(100, "Готово! Вход в КиноВселенную...");

        // Плавное скрытие preloader'а
        setTimeout(() => {
            preloader.classList.add('fade-out');
            setTimeout(() => {
                preloader.style.display = 'none';
                if (content) {
                    content.style.display = 'block';
                    // Инициализируем основное приложение
                    initializeApp();
                }
            }, 800);
        }, 700);

    } catch (error) {
        console.error("Критическая ошибка загрузки:", error);
        // В случае ошибки всё равно показываем приложение
        preloader.classList.add('fade-out');
        setTimeout(() => {
            preloader.style.display = 'none';
            if (content) {
                content.style.display = 'block';
                initializeApp();
            }
        }, 800);
    }
});

// === ORIGINAL MAIN LOGIC (остаётся после preloader) ===
function initializeApp() {
    console.log("Основное приложение инициализировано");

    // --- Вкладки ---
    const contentArea = document.getElementById('content-area');
    if (!contentArea) {
        console.error('Элемент content-area не найден');
        return;
    }

    const tabBtns = document.querySelectorAll('.tab-btn[data-tab]');

    // --- НОВОЕ: Асинхронная функция загрузки контента вкладки с кэшированием ---
    async function loadTabContent(tabName) {
        try {
            // --- НОВОЕ: Специальная обработка для search_by_link ---
            if (tabName === 'search_by_link') {
                console.log(`Загрузка специальной вкладки ${tabName}`);
                // Загружаем HTML напрямую
                const response = await fetch(`/${tabName}`);
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                const html = await response.text();
                
                // Вставляем HTML в contentArea
                contentArea.innerHTML = html;
                currentTab = tabName;
                
                // --- НОВОЕ: Добавляем обработчик кнопки поиска специально для этой вкладки ---
                addSearchByLinkHandler();
                
                // addDynamicFeatures(); // Не нужно вызывать для этой вкладки, чтобы не конфликтовать
                return; // Выходим из функции
            }
            // --- КОНЕЦ НОВОГО ---
            
            // Остальная логика для обычных вкладок (moments, trailers, news)
            // Проверяем кэш первым делом
            if (tabCache[tabName]) {
                console.log(`Загрузка вкладки ${tabName} из кэша`);
                contentArea.innerHTML = tabCache[tabName];
                currentTab = tabName;
                addDynamicFeatures();
                return;
            }
            
            // Показываем индикатор загрузки только если нет кэша
            contentArea.innerHTML = `
                <div style="text-align: center; padding: 50px; color: var(--accent);">
                    <div class="ultra-modern-spinner" style="margin: 0 auto 20px;"></div>
                    <div>🌀 Загрузка ${tabName}...</div>
                </div>
            `;

            const response = await fetch(`/${tabName}`);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const html = await response.text();
            
            // Кэшируем HTML для следующих загрузок
            tabCache[tabName] = html;
            
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
                            <div class="ultra-modern-spinner" style="margin: 0 auto 20px;"></div>
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
        // Найдем кнопку для search_by_link и сделаем её активной, если текущая вкладка такая
        // Иначе активной становится первая кнопка (moments)
        let initialTabBtn = Array.from(tabBtns).find(btn => btn.dataset.tab === currentTab);
        if (!initialTabBtn) {
            initialTabBtn = tabBtns[0];
        }
        initialTabBtn.classList.add('active');
        loadTabContent(initialTabBtn.dataset.tab);
    } else {
        console.log("Кнопки вкладок не найдены на главной странице.");
    }

    // --- Обработчики форм добавления контента ---
    setupFormSubmissions();
    
    // --- НОВОЕ: Предзагрузка популярных вкладок ---
    setTimeout(() => {
        // Предзагружаем остальные вкладки в фоне
        const otherTabs = ['trailers', 'news'];
        otherTabs.forEach(tabName => {
            fetch(`/${tabName}`)
                .then(response => response.text())
                .then(html => {
                    tabCache[tabName] = html;
                    console.log(`Вкладка ${tabName} предзагружена и закэширована`);
                })
                .catch(error => console.log(`Ошибка предзагрузки ${tabName}:`, error));
        });
    }, 2000); // Небольшая задержка, чтобы не перегружать сеть

    // === ВКЛЮЧЕНИЕ СКРОЛЛА ПОСЛЕ ЗАГРУЗКИ ===
    const appContent = document.getElementById('app-content');
    if (appContent) {
        // Разрешаем скролл после загрузки
        appContent.style.height = '100vh';
        appContent.style.overflowY = 'auto';
        appContent.style.webkitOverflowScrolling = 'touch';
        appContent.style.overscrollBehavior = 'contain';
        
        // Убираем фиксированную позицию у body/html если нужно
        // Но оставляем их зафиксированными для предотвращения overscroll
    }

    console.log("Приложение инициализировано, скролл разрешен");
}

// --- Динамические функции после загрузки контента ---
function addDynamicFeatures() {
    addReactionHandlers();
    addCommentHandlers();
    addLoadCommentsHandlers();
    addModalHandlers();
    setupFormToggles();
    initializeVideoErrorHandling();
    
    // --- Добавлено: Инициализация обработчиков для search_by_link, если это та страница ---
    // Это предотвратит конфликты с глобальными обработчиками
    const currentPagePath = window.location.pathname;
    if (currentPagePath === '/search_by_link') {
        console.log("На странице search_by_link, не добавляем глобальные обработчики модалок.");
        // Здесь можно добавить специфичные для этой страницы обработчики, если понадобятся
    }
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
    // И только если мы НЕ на странице search_by_link
    const currentPagePath = window.location.pathname;
    if (currentPagePath === '/search_by_link') {
        console.log("На странице search_by_link, пропускаем добавление глобальных обработчиков модалок.");
        return;
    }

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

        // --- ИСПРАВЛЕНО: Безопасный обработчик клика для закрытия модалок ---
        // Используем делегирование событий и проверку на клик вне содержимого
        document.addEventListener('click', function (e) {
            // Проверяем, является ли цель клика элементом модального окна (.modal)
            if (e.target.classList && e.target.classList.contains('modal')) {
                // Проверяем, что клик был НЕ на содержимом модального окна
                // Предполагаем, что содержимое обернуто в .modal-content
                const modalContent = e.target.querySelector('.modal-content');
                if (modalContent) {
                    // Проверяем, находится ли цель клика (или его родитель) внутри .modal-content
                    let isClickInsideContent = false;
                    let currentElement = e.target;
                    while (currentElement && currentElement !== e.target) { // Ограничиваем поиск текущим .modal
                        if (currentElement === modalContent) {
                            isClickInsideContent = true;
                            break;
                        }
                        currentElement = currentElement.parentElement;
                    }
                    
                    // Если клик был НЕ внутри содержимого, закрываем модалку
                    if (!isClickInsideContent) {
                        e.target.style.display = 'none';
                    }
                } else {
                    // Если .modal-content не найден, закрываем по клику на .modal
                    e.target.style.display = 'none';
                }
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

// --- НОВАЯ ФУНКЦИЯ: Обработчик для страницы search_by_link ---
function addSearchByLinkHandler() {
    console.log("Добавление обработчика для search_by_link");
    const searchBtn = document.getElementById('search-film-btn');
    const inputField = document.getElementById('video-link-input');
    const resultDiv = document.getElementById('search-result');

    // Убираем предыдущие обработчики, если они были (на всякий случай)
    // Это помогает избежать дублирования при быстром переключении вкладок
    if (searchBtn) {
        const newSearchBtn = searchBtn.cloneNode(true);
        searchBtn.parentNode.replaceChild(newSearchBtn, searchBtn);
        newSearchBtn.addEventListener('click', async function () {
            const url = inputField ? inputField.value.trim() : '';
            if (!url) {
                resultDiv.innerHTML = '<p class="result-error">Пожалуйста, введите ссылку на видео.</p>';
                return;
            }

            resultDiv.innerHTML = '<p class="result-loading">🔍 Ищем фильм... Это может занять немного времени.</p>';

            try {
                const response = await fetch('/api/search_film_by_link', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ url: url })
                });

                const data = await response.json();

                if (data.success) {
                    // Отображаем результат
                    let html = `<h2 class="film-title">${data.film.title || 'Название не найдено'}</h2>`;
                    if (data.film.year) html += `<p class="film-year">Год: ${data.film.year}</p>`;
                    if (data.film.description) html += `<p class="film-description">${data.film.description}</p>`;
                    if (data.film.poster_path) html += `<img src="${data.film.poster_path}" alt="Постер" class="film-poster">`;
                    
                    // Отображаем информацию от TinEye, если она есть
                    if (data.tineye_match_info) {
                        html += `<hr style="margin: 1rem 0; border-color: var(--border);">`;
                        html += `<h3 style="color: var(--accent);">Информация из TinEye:</h3>`;
                        html += `<p><a href="${data.tineye_match_info.url}" target="_blank" style="color: var(--accent-secondary);">${data.tineye_match_info.domain}</a> - Совпадение: ${data.tineye_match_info.score}</p>`;
                    } else if (data.tineye_matches) {
                        html += `<hr style="margin: 1rem 0; border-color: var(--border);">`;
                        html += `<h3 style="color: var(--accent);">Найденные совпадения изображений (TinEye):</h3><ul>`;
                        data.tineye_matches.slice(0, 5).forEach(match => {
                            html += `<li><a href="${match.url}" target="_blank" style="color: var(--accent-secondary);">${match.domain}</a> (score: ${match.score})</li>`;
                        });
                        html += `</ul>`;
                    }
                    resultDiv.innerHTML = html;
                } else {
                    // Улучшенная обработка ошибок
                    let errorMsg = data.error || 'Неизвестная ошибка';
                    resultDiv.innerHTML = `<p class="result-error">❌ Ошибка: ${errorMsg}</p>`;
                    
                    // Если есть дополнительная информация от TinEye, показываем её
                    if (data.tineye_matches) {
                        resultDiv.innerHTML += `<hr style="margin: 1rem 0; border-color: var(--border);">`;
                        resultDiv.innerHTML += `<h3 style="color: var(--accent);">Найденные совпадения изображений (TinEye):</h3><ul>`;
                        data.tineye_matches.slice(0, 5).forEach(match => {
                            resultDiv.innerHTML += `<li><a href="${match.url}" target="_blank" style="color: var(--accent-secondary);">${match.domain}</a> (score: ${match.score})</li>`;
                        });
                        resultDiv.innerHTML += `</ul>`;
                    }
                }
            } catch (error) {
                console.error('Ошибка при поиске фильма:', error);
                resultDiv.innerHTML = `<p class="result-error">❌ Произошла ошибка при поиске. Попробуйте позже.</p>`;
            }
        });
    } else {
        console.warn("Кнопка поиска не найдена на странице search_by_link");
        if(resultDiv) {
            resultDiv.innerHTML = '<p class="result-error">❌ Ошибка инициализации формы поиска. Элементы не найдены.</p>';
        }
    }
}
// --- КОНЕЦ НОВОЙ ФУНКЦИИ ---

console.log("main.js загружен и выполняется с fullscreen Telegram WebApp!");
