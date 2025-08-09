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
            
            // Имитируем загрузку (в будущем здесь будет реальный запрос)
            await new Promise(resolve => setTimeout(resolve, 1000));
            
            // Показываем контент вкладки
            let content = '';
            switch(tabName) {
                case 'moments':
                    content = `
                        <div style="text-align: center; padding: 50px; color: var(--accent);">
                            <h2>🎬 Моменты из кино</h2>
                            <p>Здесь скоро появятся лучшие моменты из фильмов</p>
                        </div>
                    `;
                    break;
                case 'trailers':
                    content = `
                        <div style="text-align: center; padding: 50px; color: var(--accent);">
                            <h2>🎥 Трейлеры</h2>
                            <p>Здесь скоро появятся свежие трейлеры</p>
                        </div>
                    `;
                    break;
                case 'news':
                    content = `
                        <div style="text-align: center; padding: 50px; color: var(--accent);">
                            <h2>📰 Новости</h2>
                            <p>Здесь скоро появятся горячие новости из мира кино</p>
                        </div>
                    `;
                    break;
                default:
                    content = `
                        <div style="text-align: center; padding: 50px; color: var(--accent);">
                            <h2>🌌 КиноВселенная</h2>
                            <p>Выберите вкладку для просмотра контента</p>
                        </div>
                    `;
            }
            
            contentArea.innerHTML = content;
            
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
    document.getElementById('search-btn')?.addEventListener('click', function() {
        const query = document.getElementById('search-input').value.trim();
        if (query) {
            contentArea.innerHTML = `
                <div style="text-align: center; padding: 50px; color: var(--accent);">
                    <h2>🔍 Поиск по запросу: "${query}"</h2>
                    <p>Здесь скоро появятся результаты поиска</p>
                </div>
            `;
        }
    });
    
    // Enter в поиске
    document.getElementById('search-input')?.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            document.getElementById('search-btn').click();
        }
    });
});

// Функция для добавления нового контента (заглушка)
function addNewItem(type) {
    alert(`Функция добавления ${type} будет доступна позже!`);
}
