
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useStore } from "../store";
import type { Question } from "../types";

const UNKNOWN = "Не знаю";
const OTHER = "Другое";

const EXAMPLE =
  "Насосная станция водоканала работает в отдельной закрытой сети. Диспетчер сидит в общей сети водоканала. Нужно: 1) программа диспетчера опрашивает контроллер насосов по Modbus TCP, порт 502, и получает давление и уровень воды; 2) компьютер оператора станции отправляет журналы событий на сервер мониторинга в общей сети по UDP 514, обратно ничего; 3) сервер времени из общей сети передаёт точное время на сервер времени станции по NTP, это UDP 123. Нарисуй схему и посчитай правила.";

function QuestionCard({
  questions,
  disabled,
  onSubmit,
}: {
  questions: Question[];
  disabled: boolean;
  onSubmit: (text: string) => void;
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [other, setOther] = useState<Record<string, string>>({});
  const [sent, setSent] = useState(false);

  const ready = questions.every(
    (q) =>
      answers[q.id] &&
      (answers[q.id] !== OTHER || (other[q.id] ?? "").trim() !== "")
  );

  const submit = () => {
    if (!ready || sent || disabled) return;

    const text = questions
      .map((q) => {
        const answer =
          answers[q.id] === OTHER
            ? other[q.id].trim()
            : answers[q.id];

        return questions.length > 1
          ? `${q.text} ${answer}`
          : answer;
      })
      .join("\n");

    setSent(true);
    onSubmit(text);
  };

  return (
    <div className="mt-3 space-y-4">
      {questions.map((q) => (
        <div key={q.id}>
          <div className="mb-2 text-sm font-medium">{q.text}</div>

          <div className="flex flex-wrap gap-2">
            {[...q.options, UNKNOWN, OTHER].map((opt) => (
              <button
                key={opt}
                disabled={sent || disabled}
                onClick={() =>
                  setAnswers((a) => ({ ...a, [q.id]: opt }))
                }
                className={`rounded-full border px-3 py-1 text-xs disabled:opacity-50 ${
                  answers[q.id] === opt
                    ? "border-sky-500 bg-sky-600/30"
                    : "border-zinc-600 hover:bg-zinc-800"
                }`}
              >
                {opt}
              </button>
            ))}
          </div>

          {answers[q.id] === OTHER && (
            <input
              disabled={sent || disabled}
              value={other[q.id] ?? ""}
              onChange={(e) =>
                setOther((o) => ({
                  ...o,
                  [q.id]: e.target.value,
                }))
              }
              placeholder="Ваш вариант…"
              className="mt-2 w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1.5 text-sm disabled:opacity-50"
            />
          )}
        </div>
      ))}

      {!sent && (
        <button
          disabled={!ready || disabled}
          onClick={submit}
          className="rounded-lg bg-sky-600 px-4 py-1.5 text-sm font-medium disabled:opacity-40"
        >
          Ответить
        </button>
      )}
    </div>
  );
}

export default function Chat() {
  const { messages, loading, send, retry } = useStore();
  const [text, setText] = useState("");
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const submit = () => {
    const value = text.trim();

    if (!value || loading) return;

    setText("");
    send(value);
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {messages.length === 0 && (
          <div className="space-y-3 text-sm text-zinc-300">
            <p>
              Я помогу понять, где в вашей инфраструктуре поставить
              «Синоникс» и сколько правил передачи понадобится.
              Опишите две сети и что между ними нужно передавать.
            </p>

            <p className="text-zinc-400">
              Если чего-то не знаете, не страшно: я задам
              уточняющие вопросы.
            </p>

            <button
              onClick={() => setText(EXAMPLE)}
              disabled={loading}
              className="rounded-lg border border-zinc-600 px-3 py-1.5 text-xs hover:bg-zinc-900 disabled:opacity-50"
            >
              Подставить пример
            </button>
          </div>
        )}

        {messages.map((m) => (
          <div
            key={m.id}
            className={m.role === "user" ? "flex justify-end" : ""}
          >
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-2 text-sm ${
                m.role === "user" ? "bg-zinc-800" : ""
              } ${m.isError ? "border border-red-900 text-red-300" : ""}`}
            >
              {m.role === "assistant" && (
                <div className="mb-1 text-xs text-sky-400">
                  ИИ-ассистент
                </div>
              )}

              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {m.text}
              </ReactMarkdown>

              {m.isError && (
                <button
                  onClick={retry}
                  disabled={loading}
                  className="mt-2 rounded-lg border border-red-800 px-3 py-1 text-xs hover:bg-red-950 disabled:opacity-40"
                >
                  Повторить
                </button>
              )}

              {m.questions && m.questions.length > 0 && (
                <QuestionCard
                  questions={m.questions}
                  disabled={loading}
                  onSubmit={send}
                />
              )}

              {m.sources && m.sources.length > 0 && (
                <ul className="mt-2 space-y-0.5 text-xs text-zinc-500">
                  {m.sources.map((s, i) => (
                    <li key={i}>
                      Источник: {s.file}
                      {s.section ? `, ${s.section}` : ""}
                      {s.page ? `, стр. ${s.page}` : ""}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div>
            <div className="mb-1 text-xs text-sky-400">
              ИИ-ассистент
            </div>

            <div className="flex items-center gap-1 text-sm text-zinc-400">
              <span className="h-2 w-2 animate-bounce rounded-full bg-zinc-400 [animation-delay:-0.3s]" />
              <span className="h-2 w-2 animate-bounce rounded-full bg-zinc-400 [animation-delay:-0.15s]" />
              <span className="h-2 w-2 animate-bounce rounded-full bg-zinc-400" />
              <span className="ml-2">
                Анализирую сети и подбираю решение…
              </span>
            </div>
          </div>
        )}

        <div ref={bottom} />
      </div>

      <div className="flex gap-2 border-t border-zinc-800 p-3">
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          placeholder="Опишите ваши сети и потоки данных…"
          disabled={loading}
          className="flex-1 rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm disabled:opacity-50"
        />

        <button
          onClick={submit}
          disabled={loading || !text.trim()}
          className="rounded-lg bg-sky-600 px-4 text-sm font-medium disabled:opacity-40"
        >
          Отправить
        </button>
      </div>
    </div>
  );
}
