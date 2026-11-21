"""Пакет участника B: LLM + факты + учёт стоимости.

Компоненты:
- config   — модель/провайдер, тарифы, пути к базе.
- client   — вызов модели с учётом токенов/стоимости.
- journal  — журнал вызовов и стоимость сессии.
- storage  — сохранение журнала сессии на диск (ТЗ §8).
- report   — блоки usage/timing по схеме result.example.json.
- rag      — ключевой поиск по базе знаний с цитатами.
- extract  — извлечение слотов из текста (LLM + regex-фолбэк).
- answer   — человеческие объяснения и фактические ответы.
- vendor   — сбор потребностей для разработчика (бонус §12.7).
- prompts  — промпты и стартовое сообщение.
"""
from . import answer, client, config, extract, journal, prompts, questions, rag, report, storage, vendor
from .answer import answer_fact, explain_placement, explain_rules
from .client import LLMClient
from .config import DEFAULT_MODEL, MODEL_TARIFFS
from .extract import extract, quick_extract
from .journal import CallRecord, Journal
from .questions import ensure_options, rephrase_questions
from .rag import KnowledgeBase, get_kb
from .report import build_timing, build_usage
from .storage import save_session
from .vendor import VendorRequests, detect_unsupported
from .prompts import STARTER_MESSAGE

__all__ = [
    "answer", "client", "config", "extract", "journal", "prompts", "questions",
    "rag", "report", "storage", "vendor",
    "answer_fact", "explain_placement", "explain_rules",
    "LLMClient", "DEFAULT_MODEL", "MODEL_TARIFFS",
    "extract", "quick_extract", "CallRecord", "Journal",
    "KnowledgeBase", "get_kb", "STARTER_MESSAGE",
    "build_timing", "build_usage", "save_session",
    "VendorRequests", "detect_unsupported",
    "ensure_options", "rephrase_questions",
]
