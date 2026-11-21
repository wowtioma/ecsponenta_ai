"""Клиент OpenRouter с учётом токенов и стоимости (ТЗ §7, §8).

Один метод chat() возвращает (текст_ответа, CallRecord). CallRecord сразу пишется
в переданный Journal. Стоимость берётся из usage.cost провайдера, если он её
вернул, иначе считается по снимку тарифов из config.MODEL_TARIFFS.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from . import config
from .journal import CallRecord, Journal


def _num(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


class LLMClient:
    def __init__(
        self,
        journal: Journal,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.journal = journal
        # Профиль провайдера: openrouter (по умолчанию) / yandex / gigachat.
        _base, _model, _key = config.resolve_endpoint()
        self.api_key = api_key if api_key is not None else _key
        self.model = model or _model
        self.base_url = base_url or _base
        self.provider = config.active_provider()
        self._client = None

    def _ensure(self):
        if self._client is None:
            import openai

            if not self.api_key:
                raise RuntimeError(
                    f"API-ключ для провайдера {self.provider!r} не задан. "
                    "Положи ключ в .env или переменную окружения."
                )
            headers = {}
            if self.provider == "openrouter":
                headers = {
                    "HTTP-Referer": config.HTTP_REFERER,
                    "X-Title": config.X_TITLE,
                }
            self._client = openai.OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                default_headers=headers,
            )
        return self._client

    def _provider_body(self) -> dict:
        """Привязка к провайдеру + отключение reasoning (ТЗ §9, лимит 15 секунд).

        Работает только для профиля openrouter — у Яндекса/GigaChat этих полей нет.
        Gemma 4 / Grok умеют «thinking mode», который добавляет секунды к ответу.
        Для укладывания в 15 с на шаг reasoning выключаем.
        """
        if self.provider != "openrouter":
            return {}
        body: dict = {"reasoning": {"enabled": False}}
        routing = config.provider_routing(self.model)
        if routing:
            body["provider"] = routing
        return body

    def chat(
        self,
        messages: list[dict],
        *,
        purpose: str = "",
        session_id: str = "",
        turn_id: int = 0,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> tuple[str, CallRecord]:
        """Один вызов. Возвращает (текст, запись журнала)."""
        client = self._ensure()
        call_id = uuid.uuid4().hex
        started = time.time()

        extra_body = self._provider_body()
        if self.provider == "groq" and purpose == "extract":
            extra_body.update(response_format={"type": "json_object"}, reasoning_effort="low")
        resp = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            extra_body=extra_body,
        )

        choice = resp.choices[0]
        text = choice.message.content or ""

        usage = resp.usage
        prompt_tokens = _num(getattr(usage, "prompt_tokens", None))
        completion_tokens = _num(getattr(usage, "completion_tokens", None))

        cached = 0
        reasoning = 0
        ptd = getattr(usage, "prompt_tokens_details", None)
        ctd = getattr(usage, "completion_tokens_details", None)
        if ptd is not None:
            cached = _num(getattr(ptd, "cached_tokens", None))
        if ctd is not None:
            reasoning = _num(getattr(ctd, "reasoning_tokens", None))

        raw_usage = None
        try:
            raw_usage = usage.model_dump()
        except Exception:
            raw_usage = str(usage)

        # Стоимость (ТЗ §7): при исполнении через Яндекс считаем по КАТАЛОГОВОМУ
        # тарифу OpenRouter для той же модели, а не по яндексовскому.
        catalog_id, p_in, p_out = config.billable_tariff(self.model)
        # Фактическую стоимость провайдера берём только для профиля openrouter.
        provider_cost = getattr(usage, "cost", None) if self.provider == "openrouter" else None

        if provider_cost is not None:
            cost_total = float(provider_cost)
            cost_source = "provider"
            # Раскладываем пропорционально токенам (для отчёта входа/выхода).
            cost_input = cost_total * prompt_tokens / max(prompt_tokens + completion_tokens, 1)
            cost_output = cost_total - cost_input
        else:
            cost_input = prompt_tokens * p_in / 1_000_000.0
            cost_output = completion_tokens * p_out / 1_000_000.0
            cost_total = cost_input + cost_output
            cost_source = "estimated"

        rec = CallRecord(
            session_id=session_id,
            turn_id=turn_id,
            call_id=call_id,
            # В журнал пишем КАТАЛОГОВЫЙ id — именно его проверяют организаторы.
            model_id=catalog_id,
            purpose=purpose,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            cached_tokens=cached,
            reasoning_tokens=reasoning,
            prompt_price=p_in,
            completion_price=p_out,
            cost_input=cost_input,
            cost_output=cost_output,
            cost_total=cost_total,
            cost_source=cost_source,
            started_at=started,
            finished_at=time.time(),
            status="ok",
            provider_response_id=getattr(resp, "id", ""),
            raw_usage=raw_usage,
        )
        self.journal.add(rec)
        return text, rec
