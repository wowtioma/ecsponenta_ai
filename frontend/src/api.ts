import { chatResponseSchema, type ChatResponse, type Result } from "./types";
import { mockAnswer } from "./mocks";

// Включается строкой VITE_USE_MOCK=true в файле .env.local (рядом с package.json)
const USE_MOCK = import.meta.env.VITE_USE_MOCK === "true";

function getSessionId(): string {
  let id = localStorage.getItem("session_id");
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem("session_id", id);
  }
  return id;
}

export function resetSession() {
  localStorage.removeItem("session_id");
}

export async function askAi(message: string, current: Result | null): Promise<ChatResponse> {
  if (USE_MOCK) return mockAnswer(message, current);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 60000);

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: getSessionId(), message, current_result: current }),
      signal: controller.signal,
    });

    if (res.status === 429) {
      const body = await res.json().catch(() => null);
      const message = typeof body?.detail === "string"
        ? body.detail
        : "Достигнут лимит Groq. Повторите запрос позже.";
      throw new Error(message);
    }
    if (!res.ok) throw new Error(`Сервер вернул ошибку ${res.status}`);

    const json = await res.json();
    const parsed = chatResponseSchema.safeParse(json);
    if (!parsed.success) {
      console.error("Неверный формат ответа бэкенда", parsed.error, json);
      throw new Error("Бэкенд вернул ответ в неожиданном формате");
    }
    return parsed.data;
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new Error("Сервер слишком долго отвечает", { cause: e });
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}