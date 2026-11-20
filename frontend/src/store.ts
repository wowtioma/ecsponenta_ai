import { create } from "zustand";
import type { Message, Result } from "./types";
import { askAi, resetSession } from "./api";

type State = {
  messages: Message[];
  result: Result | null;
  explanation: string; // текст ассистента, с которым пришёл последний результат
  loading: boolean;
  lastText: string | null;
  timings: number[]; // мс на каждый шаг: от отправки до завершённой отрисовки
  send: (text: string) => Promise<void>;
  retry: () => Promise<void>;
  reset: () => void;
};

export const useStore = create<State>((set, get) => {
  const run = async (text: string) => {
    const t0 = performance.now();
    set({ loading: true, lastText: text });

    try {
      const reply = await askAi(text, get().result);
      const aiMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        text: reply.text,
        questions: reply.questions ?? undefined,
        sources: reply.sources ?? undefined,
      };
      set((s) => ({
        messages: [...s.messages, aiMsg],
        loading: false,
        // результат заменяем только если бэкенд прислал новый
        result: reply.result ?? s.result,
        explanation: reply.explanation ?? (reply.result ? reply.text : s.explanation),
      }));
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Неизвестная ошибка";
      set((s) => ({
        loading: false,
        messages: [
          ...s.messages,
          { id: crypto.randomUUID(), role: "assistant", text: msg, isError: true },
        ],
      }));
    } finally {
      // конец замера: после того как React отрисовал новый результат
      requestAnimationFrame(() =>
        requestAnimationFrame(() =>
          set((s) => ({ timings: [...s.timings, performance.now() - t0] }))
        )
      );
    }
  };

  return {
    messages: [],
    result: null,
    explanation: "",
    loading: false,
    lastText: null,
    timings: [],

    send: async (text) => {
      const userMsg: Message = { id: crypto.randomUUID(), role: "user", text };
      set((s) => ({ messages: [...s.messages, userMsg] }));
      await run(text);
    },

    // повтор последнего запроса без потери введённых данных
    retry: async () => {
      const text = get().lastText;
      if (!text || get().loading) return;
      set((s) => ({ messages: s.messages.filter((m) => !m.isError) }));
      await run(text);
    },

    reset: () => {
      resetSession();
      set({ messages: [], result: null, explanation: "", loading: false, lastText: null, timings: [] });
    },
  };
});