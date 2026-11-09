
import re
import json
import time
import pandas as pd

from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException


BASE_URL = "https://www.kinopoisk.ru"
LIST_URL = BASE_URL + "/lists/top250/?page={}&tab=all"

OUTPUT_DIR = Path("results")
OUTPUT_DIR.mkdir(exist_ok=True)

all_films = []


# ==========================================
# 1. НАСТРОЙКА БРАУЗЕРА
# ==========================================

options = webdriver.ChromeOptions()
options.add_argument("--start-maximized")

browser = webdriver.Chrome(options=options)


# ==========================================
# 2. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================

def clean_text(value):
    if not value:
        return ""

    return re.sub(r"\s+", " ", str(value)).strip()


def get_text(element):
    if element:
        return clean_text(element.get_text(" ", strip=True))
    return ""


def save_results():
    """Сохраняет текущие результаты."""

    if not all_films:
        return

    df = pd.DataFrame(all_films)

    df.to_csv(
        OUTPUT_DIR / "kinopoisk_top250.csv",
        index=False,
        encoding="utf-8-sig"
    )

    df.to_excel(
        OUTPUT_DIR / "kinopoisk_top250.xlsx",
        index=False
    )

    print(f"Сохранено фильмов: {len(df)}")


def is_blocked(html):
    """Проверяет, не показана ли страница блокировки."""

    text = html.lower()

    markers = [
        "smartcaptcha",
        "g-recaptcha",
        "captcha-container",
        "подтвердите, что вы не робот",
        "доступ ограничен"
    ]

    return any(marker in text for marker in markers)


def load_page(url):
    """Открывает страницу и ожидает загрузки."""

    browser.get(url)

    try:
        WebDriverWait(browser, 20).until(
            lambda driver: driver.execute_script(
                "return document.readyState"
            ) == "complete"
        )
    except TimeoutException:
        print("Предупреждение: страница загружалась слишком долго.")

    time.sleep(2)

    html = browser.page_source

    if is_blocked(html):
        print("\nОбнаружена проверка безопасности.")
        input(
            "Пройди проверку вручную в браузере, "
            "затем нажми Enter..."
        )

        html = browser.page_source

        if is_blocked(html):
            raise RuntimeError(
                "Проверка не пройдена. Парсинг остановлен."
            )

    return html


# ==========================================
# 3. ПАРСИНГ СПИСКА ФИЛЬМОВ
# ==========================================

def parse_listing_page(html):

    soup = BeautifulSoup(html, "lxml")

    films = soup.find_all(
        "div",
        class_="desktop-rating-selection-film-item__upper-wrapper"
    )

    results = []

    for film in films:

        # Название
        name_el = film.find(
            "p",
            class_="selection-film-item-meta__name"
        )

        name = get_text(name_el)

        # Рейтинг
        rating_el = film.find(
            "span",
            class_=re.compile(r"rating__value")
        )

        rating = get_text(rating_el)

        # Страна и жанр
        meta = film.find_all(
            "span",
            class_="selection-film-item-meta__meta-additional-item"
        )

        country = get_text(meta[0]) if len(meta) > 0 else ""
        genre = get_text(meta[1]) if len(meta) > 1 else ""

        # ID фильма
        link = film.find(
            "a",
            class_="selection-film-item-meta__link",
            href=True
        )

        if not link:
            link = film.find("a", href=re.compile(r"/film/\d+"))

        href = link["href"] if link else ""

        match = re.search(r"/film/(\d+)", href)

        film_id = match.group(1) if match else ""

        film_url = (
            urljoin(BASE_URL, href)
            if href else ""
        )

        if name:
            results.append({
                "ID": film_id,
                "Название": name,
                "Рейтинг": rating,
                "Страна": country,
                "Жанр": genre,
                "Ссылка": film_url
            })

    return results


# ==========================================
# 4. ИЗВЛЕЧЕНИЕ JSON-LD
# ==========================================

def extract_jsonld(soup):

    result = []

    scripts = soup.find_all(
        "script",
        type="application/ld+json"
    )

    def flatten(data):

        if isinstance(data, list):
            for item in data:
                flatten(item)

        elif isinstance(data, dict):

            result.append(data)

            if "@graph" in data:
                flatten(data["@graph"])

    for script in scripts:

        try:
            data = json.loads(script.string or script.get_text())
            flatten(data)

        except (json.JSONDecodeError, TypeError):
            continue

    return result


def find_film_data(soup):

    objects = extract_jsonld(soup)

    for obj in objects:

        types = obj.get("@type", [])

        if isinstance(types, str):
            types = [types]

        if any(
            item in ["Movie", "Film"]
            for item in types
        ):
            return obj

    return {}


def extract_value(value):

    if isinstance(value, str):
        return value

    if isinstance(value, dict):
        return (
            value.get("name")
            or value.get("alternateName")
            or ""
        )

    if isinstance(value, list):
        return ", ".join(
            filter(None, [extract_value(x) for x in value])
        )

    return ""


# ==========================================
# 5. ПАРСИНГ СТРАНИЦЫ ОТДЕЛЬНОГО ФИЛЬМА
# ==========================================

def parse_film_page(url):

    if not url:
        return {}

    try:

        html = load_page(url)
        soup = BeautifulSoup(html, "lxml")

        data = find_film_data(soup)

        # Дополнительная информация
        description = data.get("description", "")

        year = data.get("datePublished", "")

        if year:
            year = str(year)[:4]

        duration = data.get("duration", "")

        original_name = data.get("alternateName", "")

        director = extract_value(
            data.get("director", "")
        )

        actors = extract_value(
            data.get("actor", "")
        )

        detailed_genre = extract_value(
            data.get("genre", "")
        )

        country = extract_value(
            data.get("countryOfOrigin", "")
        )

        # Если JSON-LD не содержит данных,
        # пробуем получить описание из meta-тегов.

        if not description:

            meta = soup.find(
                "meta",
                attrs={"property": "og:description"}
            )

            if meta:
                description = meta.get("content", "")

        if not original_name:

            meta = soup.find(
                "meta",
                attrs={"property": "og:title"}
            )

            if meta:
                original_name = meta.get("content", "")

        return {
            "Оригинальное название": original_name,
            "Год выпуска": year,
            "Продолжительность": duration,
            "Описание": description,
            "Режиссер": director,
            "Актеры": actors,
            "Дополнительный жанр": detailed_genre,
            "Страна производства": country
        }

    except Exception as error:

        print(f"Ошибка страницы фильма {url}: {error}")

        return {}


# ==========================================
# 6. ОСНОВНОЙ ПАРСИНГ
# ==========================================

try:

    # Собираем фильмы со всех 9 страниц

    for page in range(1, 10):

        print(f"\n{'=' * 40}")
        print(f"Страница {page} из 9")
        print(f"{'=' * 40}")

        url = LIST_URL.format(page)

        html = load_page(url)

        # Сохраняем HTML для возможной диагностики
        (OUTPUT_DIR / f"page_{page}.html").write_text(
            html,
            encoding="utf-8"
        )

        page_films = parse_listing_page(html)

        print(f"Найдено фильмов: {len(page_films)}")

        if not page_films:

            print("Фильмы не найдены.")
            print("HTML сохранен для проверки.")
            break

        all_films.extend(page_films)

        # Удаляем дубликаты по ID
        unique = {}

        for film in all_films:

            key = film["ID"] or film["Название"]

            unique[key] = film

        all_films = list(unique.values())

        save_results()

        time.sleep(2)

    # ======================================
    # 7. ДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ
    # ======================================

    print("\nНачинаем обработку страниц фильмов.")

    total = len(all_films)

    for index, film in enumerate(all_films, start=1):

        print(
            f"[{index}/{total}] "
            f"{film['Название']}"
        )

        if film["Ссылка"]:

            details = parse_film_page(
                film["Ссылка"]
            )

            film.update(details)

        # Сохраняем прогресс после каждого фильма
        save_results()

        time.sleep(2)

    print("\nПарсинг завершен!")

    print(f"Всего фильмов: {len(all_films)}")

    if len(all_films) != 250:
        print(
            "ВНИМАНИЕ: количество фильмов отличается "
            "от ожидаемых 250."
        )

    print(f"\nРезультаты находятся в папке: {OUTPUT_DIR}")

finally:

    browser.quit()
    save_results()
