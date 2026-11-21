
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useStore } from "../store";
import type { Question } from "../types";
import UsageFooter from "./UsageFooter";

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
    <div className="app-message__questions">
      {questions.map((q) => (
        <div key={q.id}>
          <div className="app-question__text">{q.text}</div>

          <div className="app-question__options">
            {[...q.options, UNKNOWN, OTHER].map((opt) => (
              <button
                key={opt}
                type="button"
                disabled={sent || disabled}
                onClick={() =>
                  setAnswers((a) => ({ ...a, [q.id]: opt }))
                }
                className={`app-chip${
                  answers[q.id] === opt ? " app-chip--active" : ""
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
              className="app-input app-input--sm app-question__input"
            />
          )}
        </div>
      ))}

      {!sent && (
        <button
          type="button"
          disabled={!ready || disabled}
          onClick={submit}
          className="app-button app-button-primary app-button-sm app-question__submit"
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
  const logRef = useRef<HTMLDivElement>(null);

  // Прокручиваем только ленту чата, не трогая страницу
  useEffect(() => {
    const log = logRef.current;

    if (!log) return;

    log.scrollTo({ top: log.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  const submit = () => {
    const value = text.trim();

    if (!value || loading) return;

    setText("");
    send(value);
  };

  return (
    <div className="app-chat">
      <div className="app-chat__log" ref={logRef}>
        {messages.length === 0 && (
          <div className="app-intro">
            <p>
              Я помогу понять, где в вашей инфраструктуре поставить
              «Синоникс» и сколько правил передачи понадобится.
              Опишите две сети и что между ними нужно передавать.
            </p>

            <p className="app-intro__muted">
              Если чего-то не знаете, не страшно: я задам
              уточняющие вопросы.
            </p>

            <button
              type="button"
              onClick={() => setText(EXAMPLE)}
              disabled={loading}
              className="app-button app-button-outline app-button-sm"
            >
              Подставить пример
            </button>
          </div>
        )}

        {messages.map((m) => (
          <div
            key={m.id}
            className={`app-message app-message--${m.role}${
              m.isError ? " app-message--error" : ""
            }`}
          >
            <div className="app-message__bubble">
              {m.role === "assistant" && (
                <div className="app-message__author">
                  ИИ-ассистент
                </div>
              )}

              <div className="app-markdown">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {m.text}
                </ReactMarkdown>
              </div>

              {m.isError && (
                <button
                  type="button"
                  onClick={retry}
                  disabled={loading}
                  className="app-button app-button-outline app-button-sm app-message__retry"
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
                <ul className="app-message__sources">
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
          <div className="app-message app-message--assistant">
            <div className="app-message__bubble">
              <div className="app-message__author">
                ИИ-ассистент
              </div>

              <div className="app-typing">
                <span className="app-typing__dot" />
                <span className="app-typing__dot" />
                <span className="app-typing__dot" />

                <span className="app-typing__text">
                  Анализирую сети и подбираю решение…
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

      <form
        className="app-composer"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Опишите ваши сети и потоки данных…"
          disabled={loading}
          className="app-input"
          aria-label="Сообщение ассистенту"
        />

        <button
          type="submit"
          disabled={loading || !text.trim()}
          className="app-button app-button-primary"
        >
          Отправить
        </button>
      </form>

      <UsageFooter />
    </div>
  );
}
