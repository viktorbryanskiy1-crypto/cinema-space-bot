// Глобальные переменные
let currentTab = 'moments';
let userId = 'user_' + Math.random().toString(36).substr(2, 9);

// Плавные переходы между вкладками
document.addEventListener('DOMContentLoaded', function () {
    const tabBtns = document.querySelectorAll('.tab-btn[data-tab]'); // Только кнопки вкладок
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
            addDynamicFeatures(); // Добавляем обработчики для нового контента

        } catch (error) {
            console.error('Ошибка загрузки вкладки:', error);
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
                    const html = await response.text();
                    contentArea.innerHTML = html;
                    addDynamicFeatures();
                } catch (error) {
                    console.error('Ошибка поиска:', error);
                    contentArea.innerHTML = `
                        <div style="text-align: center; padding: 50px; color: var(--warning);">
                            <h2>❌ Ошибка поиска</h2>
                            <p>Не удалось выполнить поиск. Попробуйте позже.</p>
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
        // или оставляем contentArea пустым/с заглушкой
        console.log("Кнопки вкладок не найдены на главной странице.");
    }
});

// Добавление динамических функций после загрузки контента
function addDynamicFeatures() {
    // Реакции
    document.querySelectorAll('.reaction-btn').forEach(btn => {
        btn.addEventListener('click', async function () {
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
        form.addEventListener('submit', async function (e) {
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
                        // Вставляем в начало списка комментариев
                        if (commentsList.firstChild) {
                            commentsList.insertBefore(newComment, commentsList.firstChild);
                        } else {
                            commentsList.appendChild(newComment);
                        }

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
        btn.addEventListener('click', async function () {
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

    // --- Добавление обработчиков событий для модальных окон ---
    // Эти обработчики добавляются после загрузки содержимого вкладки

    // Обработчики для кнопок добавления моментов
    const addMomentBtn = document.getElementById('add-moment-btn');
    if (addMomentBtn) {
        // Предотвращаем множественное добавление обработчиков
        addMomentBtn.removeEventListener('click', showAddMomentModal);
        addMomentBtn.addEventListener('click', showAddMomentModal);
        console.log('Обработчик для add-moment-btn добавлен (динамически)');
    }

    const addMomentBtnAlt = document.getElementById('add-moment-btn-alt');
    if (addMomentBtnAlt) {
        addMomentBtnAlt.removeEventListener('click', showAddMomentModal);
        addMomentBtnAlt.addEventListener('click', showAddMomentModal);
        console.log('Обработчик для add-moment-btn-alt добавлен (динамически)');
    }

    // Обработчики для кнопок добавления трейлеров
    const addTrailerBtn = document.getElementById('add-trailer-btn');
    if (addTrailerBtn) {
        addTrailerBtn.removeEventListener('click', showAddTrailerModal);
        addTrailerBtn.addEventListener('click', showAddTrailerModal);
        console.log('Обработчик для add-trailer-btn добавлен (динамически)');
    }

    const addTrailerBtnAlt = document.getElementById('add-trailer-btn-alt');
    if (addTrailerBtnAlt) {
        addTrailerBtnAlt.removeEventListener('click', showAddTrailerModal);
        addTrailerBtnAlt.addEventListener('click', showAddTrailerModal);
        console.log('Обработчик для add-trailer-btn-alt добавлен (динамически)');
    }

    // Обработчики для кнопок добавления новостей
    const addNewsBtn = document.getElementById('add-news-btn');
    if (addNewsBtn) {
        addNewsBtn.removeEventListener('click', showAddNewsModal);
        addNewsBtn.addEventListener('click', showAddNewsModal);
        console.log('Обработчик для add-news-btn добавлен (динамически)');
    }

    const addNewsBtnAlt = document.getElementById('add-news-btn-alt');
    if (addNewsBtnAlt) {
        addNewsBtnAlt.removeEventListener('click', showAddNewsModal);
        addNewsBtnAlt.addEventListener('click', showAddNewsModal);
        console.log('Обработчик для add-news-btn-alt добавлен (динамически)');
    }

    // Переключение между загрузкой и URL для форм
    setupFormToggles();

    // --- КОНЕЦ НОВЫХ ОБРАБОТЧИКОВ ---
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
        console.log('Модальное окно моментов открыто');
    } else {
        console.warn('Модальное окно моментов не найдено');
    }
}

function showAddTrailerModal() {
    const modal = document.getElementById('add-trailer-modal');
    if (modal) {
        modal.style.display = 'flex';
        console.log('Модальное окно трейлеров открыто');
    } else {
        console.warn('Модальное окно трейлеров не найдено');
    }
}

function showAddNewsModal() {
    const modal = document.getElementById('add-news-modal');
    if (modal) {
        modal.style.display = 'flex';
        console.log('Модальное окно новостей открыто');
    } else {
        console.warn('Модальное окно новостей не найдено');
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
        console.log(`Модальное окно ${modalId} закрыто`);
    }
}

// Закрытие модального окна при клике вне его
document.addEventListener('click', function (e) {
    // Проверяем, кликнули ли мы вне модального окна, но внутри оверлея
    if (e.target.classList.contains('modal')) {
        e.target.style.display = 'none';
        console.log('Модальное окно закрыто кликом вне его');
    }
});

// --- Функции для переключения форм ---
function setupFormToggles() {
    // Переключение между загрузкой и URL для моментов
    document.addEventListener('change', function (e) {
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
}

// --- Обработчики форм добавления контента ---
// Этот блок выполняется после полной загрузки DOM
document.addEventListener('DOMContentLoaded', function () {
    console.log("DOM загружен, инициализируем обработчики форм");

    // Обработчик формы добавления момента
    const momentForm = document.getElementById('add-moment-form');
    if (momentForm) {
        momentForm.addEventListener('submit', async function (e) {
            e.preventDefault();
            console.log("Отправка формы добавления момента");

            const formData = new FormData(this);
            const videoType = this.querySelector('input[name="video_type"]:checked')?.value || 'url';

            try {
                let response;
                if (videoType === 'upload' && this.querySelector('input[name="video_file"]')?.files[0]) {
                    console.log("Загрузка видео файла");
                    // Загрузка файла
                    response = await fetch('/api/add_moment', {
                        method: 'POST',
                        body: formData // Отправляем FormData для файлов
                    });
                } else {
                    console.log("Отправка URL видео");
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

                const result = await response.json();
                console.log("Ответ от сервера:", result);
                if (result.success) {
                    closeModal('add-moment-modal');
                    // Перезагружаем текущую вкладку
                    location.reload(); // Или можно сделать более плавную перезагрузку через AJAX
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
        trailerForm.addEventListener('submit', async function (e) {
            e.preventDefault();
            console.log("Отправка формы добавления трейлера");

            const formData = new FormData(this);
            const videoType = this.querySelector('input[name="video_type"]:checked')?.value || 'url';

            try {
                let response;
                if (videoType === 'upload' && this.querySelector('input[name="video_file"]')?.files[0]) {
                    console.log("Загрузка файла трейлера");
                    // Загрузка файла
                    response = await fetch('/api/add_trailer', {
                        method: 'POST',
                        body: formData
                    });
                } else {
                    console.log("Отправка URL трейлера");
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

                const result = await response.json();
                console.log("Ответ от сервера:", result);
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
        newsForm.addEventListener('submit', async function (e) {
            e.preventDefault();
            console.log("Отправка формы добавления новости");

            // Для новостей всегда используем FormData, так как может быть файл
            const formData = new FormData(this);
            // image_type не передается на сервер, удалим его из FormData
            formData.delete('image_type');

            try {
                const response = await fetch('/api/add_news', {
                    method: 'POST',
                    body: formData // Отправляем FormData, он сам определит Content-Type multipart/form-data
                });

                const result = await response.json();
                console.log("Ответ от сервера:", result);
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
