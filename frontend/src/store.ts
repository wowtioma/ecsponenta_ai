// dsh-skip-func-length: Единый фабричный стор zustand (create с набором действий) — существующая структура; в этой правке добавлен только вызов очистки схем при сбросе сессии, полное разбиение стора — отдельная задача

import { create } from "zustand";
import type { Message, Result } from "./types";
import { askAi, resetSession } from "./api";
import { clearAllDrawioDocuments } from "./lib/drawioDocument";
import {
  EMPTY_USAGE,
  mergeUsage,
  type SessionUsage,
} from "./lib/usage";

type State = {
  messages: Message[];
  result: Result | null;
  explanation: string;
  loading: boolean;
  lastText: string | null;
  lastAnswers: Record<string, string> | undefined;
  timings: number[];

  // Накопленный расход за сессию: токены и деньги
  usage: SessionUsage;

  // Показывает, что сохранённый результат больше не является
  // актуальным ответом на последний запрос
  resultIsStale: boolean;

  send: (text: string, answers?: Record<string, string>) => Promise<void>;
  retry: () => Promise<void>;
  reset: () => void;
};

export const useStore = create<State>((set, get) => {
  // Защита от записи ответа старого запроса после сброса сессии
  let activeRequest = 0;

  const run = async (text: string, answers?: Record<string, string>) => {
    const requestId = ++activeRequest;
    const t0 = performance.now();

    set((state) => ({
      loading: true,
      lastText: text,
      lastAnswers: answers,
      resultIsStale: state.result !== null,
    }));

    try {
      const reply = await askAi(text, get().result, answers);

      // Игнорируем ответ, если сессия уже была сброшена
      if (requestId !== activeRequest) return;

      const aiMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        text: reply.text,
        questions: reply.questions ?? undefined,
        sources:
          reply.sources?.length
            ? reply.sources
            : reply.result?.sources?.length
              ? reply.result.sources
              : undefined,
      };

      set((state) => {
        const hasNewResult = reply.result != null;

        return {
          messages: [...state.messages, aiMsg],
          loading: false,

          // Новый результат заменяет предыдущий.
          // Если результата нет, сохраняем предыдущий.
          result: reply.result ?? state.result,

          // Объяснение обновляем только вместе с новым результатом,
          // если сервер отдельно не прислал explanation
          explanation:
            reply.explanation ??
            (hasNewResult ? reply.text : state.explanation),

          // Если новой конфигурации нет, старый результат
          // остаётся помеченным как предыдущий
          resultIsStale: !hasNewResult && !reply.result_unchanged && state.result !== null,

          // usage в ответе — накопительный итог сессии
          usage: mergeUsage(
            state.usage,
            reply.usage ?? reply.result?.usage ?? null,
          ),
        };
      });
    } catch (e) {
      if (requestId !== activeRequest) return;

      const msg =
        e instanceof Error
          ? e.message
          : "Неизвестная ошибка";

      set((state) => ({
        loading: false,
        resultIsStale: state.result !== null,
        messages: [
          ...state.messages,
          {
            id: crypto.randomUUID(),
            role: "assistant",
            text: msg,
            isError: true,
          },
        ],
      }));
    } finally {
      if (requestId === activeRequest) {
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            if (requestId !== activeRequest) return;

            set((state) => ({
              timings: [
                ...state.timings,
                performance.now() - t0,
              ],
            }));
          });
        });
      }
    }
  };

  return {
    messages: [],
    result: null,
    explanation: "",
    loading: false,
    lastText: null,
    lastAnswers: undefined,
    timings: [],
    usage: EMPTY_USAGE,
    resultIsStale: false,

    // Отправка нового сообщения
    send: async (text, answers) => {
      if (get().loading || !text.trim()) return;

      const userMsg: Message = {
        id: crypto.randomUUID(),
        role: "user",
        text,
      };

      set((state) => ({
        messages: [...state.messages, userMsg],
      }));

      await run(text, answers);
    },

    // Повтор последнего запроса
    retry: async () => {
      const text = get().lastText;

      if (!text || get().loading) return;

      set((state) => ({
        messages: state.messages.filter((message) => !message.isError),
      }));

      await run(text, get().lastAnswers);
    },

    // Полный сброс сессии
    reset: () => {
      // Инвалидируем все незавершённые запросы
      activeRequest++;

      resetSession();

      // Новая сессия — чистая схема: убираем сохранённые правки,
      // привязанные к конфигурациям прошлой сессии.
      clearAllDrawioDocuments();

      set({
        messages: [],
        result: null,
        explanation: "",
        loading: false,
        lastText: null,
    lastAnswers: undefined,
        timings: [],
        usage: EMPTY_USAGE,
        resultIsStale: false,
      });
    },
  };
});
