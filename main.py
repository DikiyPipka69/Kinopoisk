import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import pandas as pd
import random
import time
import re

# Инициализируем защищенный драйвер
# Он автоматически подберет ваш Chrome и очистит его от флагов автоматизации
options = uc.ChromeOptions()
options.add_argument('--log-level=3')

browser = uc.Chrome(options=options)

def human_delay(min_sec=3, max_sec=6):
    """Имитирует хаотичную паузу реального пользователя."""
    time.sleep(random.uniform(min_sec, max_sec))

def get_value(element):
    if element:
        text = element.get_text(strip=True)
        return re.sub(r'\s+', ' ', text)
    return ''

all_films = []

try:
    for page in range(1, 10):
        print(f"Парсинг страницы {page} из 9...")
        url = f"https://www.kinopoisk.ru/lists/top250/?page={page}&tab=all"
        
        browser.get(url)
        human_delay(4, 7) # Имитация времени на чтение страницы
        
        # Эмуляция активности: легкий скролл страницы вниз-вверх, как делает человек
        browser.execute_script(f"window.scrollTo(0, {random.randint(300, 700)});")
        human_delay(1, 3)
        browser.execute_script("window.scrollTo(0, 0);")
        
        html_content = browser.page_source
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Аварийный перехват капчи
        if "smartcaptcha" in html_content.lower() or soup.find('div', class_='g-recaptcha'):
            input("Система безопасности Яндекса вывела капчу. Решите её руками в окне браузера и нажмите Enter здесь...")
            soup = BeautifulSoup(browser.page_source, 'html.parser')
            
        films_list = soup.find_all('div', class_='desktop-rating-selection-film-item__upper-wrapper')
        print(f"-> Найдено фильмов на странице {page}: {len(films_list)}")
        
        for film in films_list:
            name_el = film.find('p', class_='selection-film-item-meta__name')
            name = get_value(name_el)
            
            rating_el = film.find('span', class_=re.compile(r'rating__value'))
            rating = get_value(rating_el)
            
            meta_items = film.find_all('span', class_='selection-film-item-meta__meta-additional-item')
            
            country = get_value(meta_items[0]) if len(meta_items) > 0 else ''
            genre = get_value(meta_items[1]) if len(meta_items) > 1 else ''
            
            if name:
                all_films.append({
                    'Название': name,
                    'Рейтинг': rating,
                    'Страна': country,
                    'Жанр': genre
                })

finally:
    browser.quit()

if all_films:
    df = pd.DataFrame(all_films)
    df.to_excel('kinopoisk_top250.xlsx', index=False)
    df.to_csv('kinopoisk_top250.csv', index=False, encoding='utf-8-sig')
    print(f"\nУспешно! Всего собрано и записано {len(df)} фильмов.")
else:
    print("\nСбор данных не удался.")
