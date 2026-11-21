"""Конфигурация участника B: модель OpenRouter, тарифы, пути к базе знаний.

Сюда НЕ попадают секреты — ключ берётся из переменной окружения или файла .env.
"""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import dotenv_values, load_dotenv
    load_dotenv()
except ImportError:  # dotenv не обязателен при конфигурации через окружение
    dotenv_values = None

# Корень проекта = папка, в которой лежит пакет llm/
ROOT = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------
# Провайдер LLM: "openrouter" | "yandex" | "gigachat"
# Переключается переменной окружения LLM_PROVIDER.
#
# ВАЖНО (ТЗ §7): в зачётном прогоне стоимость считается ТОЛЬКО по тарифу из
# каталога OpenRouter для той же модели. Профиль yandex/gigachat допустим лишь
# если организаторы письменно разрешили «другой API для той же модели».
# --------------------------------------------------------------------------
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openrouter").lower()

# Общие (OpenRouter)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
HTTP_REFERER = os.getenv("HTTP_REFERER", "https://neti-next.ru")
X_TITLE = os.getenv("X_TITLE", "NETI-NEXT 2.0 Sinonix")

# Модель по умолчанию.
# ВАЖНО (ТЗ §7): входной тариф <= $0.10/1M у КАЖДОЙ модели рабочего контура.
# Проверь фактическую цену на https://openrouter.ai/models и при необходимости
# поменяй DEFAULT_MODEL ниже (или переменной окружения OPENROUTER_MODEL).
DEFAULT_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemma-4-26b-a4b-it:free")

# Yandex AI Studio (OpenAI-совместимый endpoint)
# base_url с /v1 и вызовом chat/completions даёт .../v1/chat/completions —
# это правильный эндпоинт Яндекса.
YANDEX_API_KEY = os.getenv("YANDEX_API_KEY", "")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID", "")
YANDEX_BASE_URL = os.getenv("YANDEX_BASE_URL", "https://llm.api.cloud.yandex.net/v1")
# Короткое имя модели в AI Studio (без префикса gpt://).
# Самые дешёвые из доступных: gpt-oss-20b (0.10 ₽/1K), gpt-oss-120b (0.30 ₽/1K).
# Обе присутствуют в каталоге OpenRouter -> ТЗ §7 выполняется.
YANDEX_MODEL = os.getenv("YANDEX_MODEL", "gpt-oss-20b")

# Соответствие «модель AI Studio» -> «модель каталога OpenRouter + каталоговый тариф».
# По ТЗ §7 (стр. 157) при исполнении через другой API стоимость считается по
# снимку тарифов OpenRouter именно этой модели. Значения — USD за 1M токенов.
YANDEX_TO_OPENROUTER: dict[str, tuple[str, float, float]] = {
    "gpt-oss-20b": ("openai/gpt-oss-20b", 0.03, 0.14),
    "gpt-oss-120b": ("openai/gpt-oss-120b", 0.039, 0.19),
    "qwen3-235b-a22b-fp8": ("qwen/qwen3-235b-a22b", 0.10, 0.30),
}

# Groq (LPU, OpenAI-совместимый) — БЕСПЛАТНЫЙ план без карты.
# Модели gpt-oss-* есть в каталоге OpenRouter -> ТЗ §7 выполняется через
# «другой API для той же модели» (стр. 157). Стоимость считается по каталогу.
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

# Соответствие «модель у Groq/Яндекса» -> «модель каталога OpenRouter + тариф».
# По ТЗ §7 (стр. 157) при исполнении через другой API стоимость считается по
# снимку тарифов OpenRouter именно этой модели. Значения — USD за 1M токенов.
GROQ_TO_OPENROUTER: dict[str, tuple[str, float, float]] = {
    "openai/gpt-oss-20b": ("openai/gpt-oss-20b", 0.03, 0.14),
    "openai/gpt-oss-120b": ("openai/gpt-oss-120b", 0.039, 0.19),
    "gpt-oss-20b": ("openai/gpt-oss-20b", 0.03, 0.14),
    "gpt-oss-120b": ("openai/gpt-oss-120b", 0.039, 0.19),
    "qwen/qwen3.8-27b": ("qwen/qwen3.8-27b", 0.10, 0.30),
}

# GigaChat (Sber)
GIGACHAT_API_KEY = os.getenv("GIGACHAT_API_KEY", "")
GIGACHAT_BASE_URL = os.getenv("GIGACHAT_BASE_URL", "https://gigachat.devices.sberbank.ru/api/v1")
GIGACHAT_MODEL = os.getenv("GIGACHAT_MODEL", "GigaChat-Pro")


def _groq_api_key() -> str:
    values = dotenv_values(ROOT / ".env.groq") if dotenv_values else {}
    slot = (os.getenv("GROQ_ACTIVE_SLOT") or values.get("GROQ_ACTIVE_SLOT") or "").strip()
    if not slot:
        return GROQ_API_KEY
    if slot not in {"1", "2", "3"}:
        raise ValueError("GROQ_ACTIVE_SLOT должен быть 1, 2 или 3.")
    name = f"GROQ_API_KEY_{slot}"
    key = (os.getenv(name) or values.get(name) or "").strip()
    if not key:
        raise ValueError(f"Заполните {name} в локальном файле .env.groq.")
    return key


def active_provider() -> str:
    return LLM_PROVIDER


def resolve_endpoint() -> tuple[str, str, str]:
    """Возвращает (base_url, model_id, api_key) для активного профиля."""
    if LLM_PROVIDER == "yandex":
        folder = YANDEX_FOLDER_ID or "<folder_id>"
        return (
            YANDEX_BASE_URL,
            f"gpt://{folder}/{YANDEX_MODEL}",
            YANDEX_API_KEY,
        )
    if LLM_PROVIDER == "groq":
        return (GROQ_BASE_URL, GROQ_MODEL, _groq_api_key())
    if LLM_PROVIDER == "gigachat":
        return (GIGACHAT_BASE_URL, GIGACHAT_MODEL, GIGACHAT_API_KEY)
    return (OPENROUTER_BASE_URL, DEFAULT_MODEL, OPENROUTER_API_KEY)


# Тарифы в USD за 1 000 000 токенов: (вход, выход).
# Заполни значениями с карточки модели НА МОМЕНТ прогона. Организаторы фиксируют
# единый снимок тарифов — тут должны лежать ровно те же числа, что ты заявил.
MODEL_TARIFFS: dict[str, tuple[float, float]] = {
    # Бесплатная модель OpenRouter — разрешена ТЗ §7 (нулевой тариф в каталоге).
    # Внимание: 50 запросов/день без покупки кредитов, 1000/день после $10.
    "google/gemma-4-26b-a4b-it:free": (0.0, 0.0),
    "google/gemma-4-31b-it:free": (0.0, 0.0),
    "nvidia/nemotron-3.5-lightning:free": (0.0, 0.0),
    # Grok :free снят с каталога — оставлен для истории/резерва.
    "x-ai/grok-4.1-fast:free": (0.0, 0.0),
    "google/gemini-2.0-flash-001": (0.10, 0.40),
    "google/gemini-2.0-flash-lite-001": (0.075, 0.30),
    # у llama-3.3-70b цена зависит от провайдера; ниже DeepInfra (Turbo)
    "meta-llama/llama-3.3-70b-instruct": (0.10, 0.32),
    # Открытые модели — есть и в каталоге OpenRouter, и у Яндекса.
    # Тариф ниже — КАТАЛОГОВЫЙ OpenRouter (для зачётного расчёта).
    "openai/gpt-oss-20b": (0.03, 0.14),
    "openai/gpt-oss-120b": (0.039, 0.19),
    "deepseek/deepseek-v4-flash": (0.03, 0.20),
}

# Привязка модели к конкретному провайдеру OpenRouter.
# КРИТИЧНО (ТЗ §7): цена привязана к провайдеру, а не к модели. Для llama-3.3-70b
# самый дешёвый провайдер — DeepInfra (Turbo) $0.10/$0.32, но без привязки
# OpenRouter может уйти на Parasail ($0.22) или AkashML ($0.20) — это нарушение
# лимита. Включаем allow_fallbacks=False, чтобы подмены не было.
MODEL_PROVIDER: dict[str, dict] = {
    "meta-llama/llama-3.3-70b-instruct": {
        "only": ["DeepInfra"],
        "order": ["DeepInfra"],
        "allow_fallbacks": False,
    },
    # Gemini Flash: Google — единственный провайдер с таким тарифом.
    "google/gemini-2.0-flash-001": {"allow_fallbacks": False},
    "google/gemini-2.0-flash-lite-001": {"allow_fallbacks": False},
}


def provider_routing(model: str) -> dict | None:
    """Возвращает extra_body['provider'] для OpenRouter или None."""
    return MODEL_PROVIDER.get(model)

# --------------------------------------------------------------------------
# База знаний (папка synonyx_base из кейса)
# --------------------------------------------------------------------------
SYNONYX_BASE_DIR = Path(
    os.getenv(
        "SYNONYX_BASE_DIR",
        str(ROOT / "Кейс АйТи Бастион — Синоникс" / "synonyx_base"),
    )
)

# Входной тариф выше которого модель не допускается (ТЗ §7).
PRICE_LIMIT_INPUT = 0.10  # USD / 1M


def knowledge_base_problem() -> str | None:
    """Проверяет базу знаний для RAG. Возвращает описание проблемы или None.

    База `synonyx_base` не лежит в репозитории (материалы кейса в .gitignore),
    поэтому при клонировании легко получить пустой индекс и непонятные
    падения тестов. Функция нужна для понятного сообщения при старте.
    """
    if not SYNONYX_BASE_DIR.is_dir():
        return (
            f"Папка базы знаний не найдена: {SYNONYX_BASE_DIR}\n"
            f"Укажите SYNONYX_BASE_DIR в .env или переменной окружения — "
            f"путь к каталогу synonyx_base с файлами *.md."
        )
    if not any(SYNONYX_BASE_DIR.glob("*.md")):
        return (
            f"В папке базы знаний нет файлов *.md: {SYNONYX_BASE_DIR}\n"
            f"Проверьте SYNONYX_BASE_DIR — там должны лежать "
            f"00_read_it_first.md, 02_methodology.md и другие материалы кейса."
        )
    return None


def tariff(model: str) -> tuple[float, float]:
    """Возвращает (вход, выход) в USD/1M. Падает, если модель не заявлена."""
    if model not in MODEL_TARIFFS:
        raise KeyError(
            f"Модель {model!r} не заявлена в MODEL_TARIFFS. "
            f"Добавь её тарифы в llm/config.py."
        )
    return MODEL_TARIFFS[model]


def catalog_model(served_model: str) -> str:
    """Каталоговая модель OpenRouter для той, что фактически исполняется.

    Если исполняем через Яндекс (gpt-oss-20b), в отчёте по ТЗ §7 должна стоять
    каталожная модель OpenRouter (openai/gpt-oss-20b) и её тариф.
    """
    short = served_model.split("/")[-1] if served_model.startswith("gpt://") else served_model
    if LLM_PROVIDER == "yandex" and short in YANDEX_TO_OPENROUTER:
        return YANDEX_TO_OPENROUTER[short][0]
    return served_model


def billable_tariff(served_model: str) -> tuple[str, float, float]:
    """(каталоговая модель, вход, выход) для расчёта стоимости в зачётном отчёте.

    ТЗ §7 стр. 157: при исполнении через «другой API» (Groq/Яндекс) стоимость
    считается по каталоговому тарифу OpenRouter той же модели.
    """
    if LLM_PROVIDER == "groq" and served_model in GROQ_TO_OPENROUTER:
        cat, p_in, p_out = GROQ_TO_OPENROUTER[served_model]
        if cat in MODEL_TARIFFS:  # отдаём предпочтение каталоговому тарифу
            p_in, p_out = MODEL_TARIFFS[cat]
        return (cat, p_in, p_out)
    short = served_model.split("/")[-1] if served_model.startswith("gpt://") else served_model
    if LLM_PROVIDER == "yandex" and short in YANDEX_TO_OPENROUTER:
        cat, p_in, p_out = YANDEX_TO_OPENROUTER[short]
        return (cat, p_in, p_out)
    p_in, p_out = tariff(served_model)
    return (served_model, p_in, p_out)


def estimate_cost(input_tokens: int, output_tokens: int, model: str) -> float:
    """Оценочная стоимость вызова по снимку тарифов (ТЗ §8):
    C = (T_in * P_in + T_out * P_out) / 1_000_000.
    Для Яндекса считается по каталоговому тарифу OpenRouter.
    """
    _, p_in, p_out = billable_tariff(model)
    return (input_tokens * p_in + output_tokens * p_out) / 1_000_000.0


def check_price_limit(model: str) -> tuple[float, bool]:
    """Возвращает (входной_тариф, допускается_ли)."""
    p_in, _ = tariff(model)
    return p_in, p_in <= PRICE_LIMIT_INPUT
