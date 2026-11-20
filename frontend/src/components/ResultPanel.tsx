
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useStore } from "../store";
import RulesTable from "./RulesTable";
import DiagramPreview from "./DiagramPreview";
import { fileUsersLabel } from "../lib/format";
import type { Result } from "../types";

type Tab = "explanation" | "rules" | "diagram";

const TABS: { id: Tab; label: string }[] = [
  { id: "explanation", label: "Объяснение" },
  { id: "rules", label: "Таблица правил" },
  { id: "diagram", label: "Схема" },
];

const STATUS_CLS: Record<Result["status"], string> = {
  needs_clarification:
    "border-orange-500 bg-orange-500/15 text-orange-300",
  preliminary:
    "border-amber-500 bg-amber-500/15 text-amber-300",
  completed:
    "border-emerald-500 bg-emerald-500/15 text-emerald-300",
  unsupported:
    "border-red-500 bg-red-500/15 text-red-300",
};

function statusText(status: Result["status"]): string {
  switch (status) {
    case "needs_clarification":
      return "Требуется уточнение";
    case "preliminary":
      return "Предварительно";
    case "completed":
      return "Готово";
    case "unsupported":
      return "Не поддерживается";
  }
}

function List({
  title,
  items,
}: {
  title: string;
  items: string[];
}) {
  if (items.length === 0) return null;

  return (
    <div className="mt-4">
      <div className="mb-1 text-xs font-medium text-zinc-400">
        {title}
      </div>

      <ul className="list-disc space-y-1 pl-5 text-sm text-zinc-300">
        {items.map((item, index) => (
          <li key={`${index}-${item}`}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export default function ResultPanel() {
  const {
    result,
    explanation,
    loading,
    resultIsStale,
  } = useStore();

  const [tab, setTab] = useState<Tab>("explanation");

  // Пока первый запрос выполняется и результата ещё нет
  if (!result && loading) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
        <span className="rounded-full border border-sky-500 bg-sky-500/15 px-3 py-1 text-xs font-medium text-sky-300">
          Обновляется
        </span>

        <p className="text-sm text-zinc-400">
          Анализирую данные и формирую результат…
        </p>
      </div>
    );
  }

  // Если результата пока нет и запрос не выполняется
  if (!result) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-sm text-zinc-500">
        Результат появится здесь после описания сетей в чате
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Статус и основные показатели */}
      <div className="space-y-3 border-b border-zinc-800 p-3">
        <div className="flex flex-wrap items-center gap-2">
          {loading ? (
            <span className="rounded-full border border-sky-500 bg-sky-500/15 px-3 py-1 text-xs font-medium text-sky-300">
              Обновляется…
            </span>
          ) : (
            <span
              className={`rounded-full border px-3 py-1 text-xs font-medium ${
                STATUS_CLS[result.status]
              }`}
            >
              {statusText(result.status)}
            </span>
          )}

          {resultIsStale && (
            <span className="text-xs text-amber-300">
              Показан предыдущий результат
            </span>
          )}
        </div>

        {/* Основные показатели */}
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-zinc-400">
          <span>
            Правил:{" "}
            <b className="text-zinc-200">
              {result.rules_count}
            </b>
          </span>

          <span>
            Пользователей файловой передачи:{" "}
            <b className="text-zinc-200">
              {fileUsersLabel(result)}
            </b>
          </span>
        </div>

        {/* Пояснение при обновлении или сохранении старого результата */}
        {loading && (
          <p className="text-xs text-sky-300">
            Выполняется новый запрос. Пока отображается предыдущая
            конфигурация, она ещё не подтверждена новым ответом.
          </p>
        )}

        {!loading && resultIsStale && (
          <p className="text-xs text-amber-300">
            Последний запрос не вернул новую конфигурацию.
            Ниже показан последний рассчитанный результат.
          </p>
        )}

        {/* Дополнительные пояснения по статусам */}
        {!loading && result.status === "needs_clarification" && (
          <p className="text-xs text-orange-300">
            Проект ещё не готов: ответьте на вопросы ассистента в чате.
          </p>
        )}

        {!loading && result.status === "unsupported" && (
          <p className="text-xs text-red-300">
            Запрос выходит за границы поддерживаемого.
            Подробности приведены во вкладке «Объяснение».
          </p>
        )}

        {/* Неизвестные сведения */}
        <List
          title="Недостающие сведения"
          items={result.unknowns}
        />

        {/* Принятые допущения видны независимо от выбранной вкладки */}
        <List
          title="Принятые допущения"
          items={result.assumptions}
        />
      </div>

      {/* Вкладки */}
      <div className="flex gap-1 border-b border-zinc-800 px-3 pt-2">
        {TABS.map((item) => (
          <button
            key={item.id}
            onClick={() => setTab(item.id)}
            className={`rounded-t-lg px-3 py-1.5 text-sm ${
              tab === item.id
                ? "border-b-2 border-sky-500 text-white"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {/* Содержимое вкладок */}
      <div
        className={`min-h-0 flex-1 overflow-auto ${
          loading || resultIsStale ? "opacity-60" : ""
        }`}
      >
        {tab === "explanation" && (
          <div className="p-4 text-sm">
            {explanation ? (
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {explanation}
              </ReactMarkdown>
            ) : (
              <p className="text-zinc-500">
                Объяснение пока недоступно.
              </p>
            )}

            <List
              title="Источники"
              items={result.sources.map(
                (source) =>
                  `${source.file}${
                    source.section ? `, ${source.section}` : ""
                  }${
                    source.page ? `, стр. ${source.page}` : ""
                  }`
              )}
            />
          </div>
        )}

        {tab === "rules" && (
          <RulesTable result={result} />
        )}

        {tab === "diagram" && (
          <div className="h-full overflow-auto p-3">
            <DiagramPreview result={result} />
          </div>
        )}
      </div>
    </div>
  );
}
