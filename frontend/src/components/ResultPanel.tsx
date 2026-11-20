
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useStore } from "../store";
import RulesTable from "./RulesTable";
import DiagramPreview from "./DiagramPreview";
import { fileUsersLabel, plural } from "../lib/format";
import type { Result } from "../types";

type Tab = "explanation" | "rules" | "diagram";

const TABS: { id: Tab; label: string }[] = [
  { id: "explanation", label: "Объяснение" },
  { id: "rules", label: "Таблица правил" },
  { id: "diagram", label: "Схема" },
];

const STATUS_CLS: Record<Result["status"], string> = {
  needs_clarification: "border-orange-500 bg-orange-500/15 text-orange-300",
  preliminary: "border-amber-500 bg-amber-500/15 text-amber-300",
  completed: "border-emerald-500 bg-emerald-500/15 text-emerald-300",
  unsupported: "border-red-500 bg-red-500/15 text-red-300",
};

function statusText(r: Result): string {
  switch (r.status) {
    case "needs_clarification":
      return "Нужно уточнение";
    case "preliminary":
      return `Предварительная оценка: минимум ${r.rules_count} ${plural(
        r.rules_count,
        ["правило", "правила", "правил"]
      )}`;
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

      <ul className="list-disc space-y-0.5 pl-5 text-sm text-zinc-300">
        {items.map((x, i) => (
          <li key={i}>{x}</li>
        ))}
      </ul>
    </div>
  );
}

export default function ResultPanel() {
  const { result, explanation, loading } = useStore();
  const [tab, setTab] = useState<Tab>("explanation");

  if (!result) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-sm text-zinc-500">
        Результат появится здесь после описания сетей в чате
      </div>
    );
  }

  const showUnknowns =
    result.status !== "completed" && result.unknowns.length > 0;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="space-y-2 border-b border-zinc-800 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`rounded-full border px-3 py-1 text-xs font-medium ${STATUS_CLS[result.status]}`}
          >
            {statusText(result)}
          </span>

          {loading && (
            <span className="text-xs text-zinc-400">
              Обновляется…
            </span>
          )}
        </div>

        <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-zinc-400">
          <span>
            Правил:{" "}
            <b className="text-zinc-200">{result.rules_count}</b>
          </span>

          <span>
            Пользователей файловой передачи:{" "}
            <b className="text-zinc-200">
              {fileUsersLabel(result)}
            </b>
          </span>
        </div>

        {result.status === "needs_clarification" && (
          <p className="text-xs text-orange-300">
            Проект ещё не готов: ответьте на вопросы ассистента в чате.
          </p>
        )}

        {result.status === "unsupported" && (
          <p className="text-xs text-red-300">
            Запрос выходит за границы поддерживаемого.
            Подробности во вкладке «Объяснение».
          </p>
        )}

        {showUnknowns && (
          <div className="rounded-lg border border-amber-700/60 bg-amber-950/30 p-2 text-xs text-amber-200">
            <div className="mb-1 font-medium">
              Недостающие сведения
            </div>

            <ul className="list-disc space-y-0.5 pl-4">
              {result.unknowns.map((u, i) => (
                <li key={i}>{u}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div className="flex gap-1 border-b border-zinc-800 px-3 pt-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`rounded-t-lg px-3 py-1.5 text-sm ${
              tab === t.id
                ? "border-b-2 border-sky-500 text-white"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div
        className={`min-h-0 flex-1 overflow-auto ${
          loading ? "opacity-60" : ""
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
              title="Принятые допущения"
              items={result.assumptions}
            />

            {result.sources.length > 0 && (
              <List
                title="Источники"
                items={result.sources.map(
                  (s) =>
                    `${s.file}${s.section ? `, ${s.section}` : ""}${s.page ? `, стр. ${s.page}` : ""}`
                )}
              />
            )}
          </div>
        )}

        {tab === "rules" && <RulesTable result={result} />}

        {tab === "diagram" && (
          <div className="h-full overflow-auto p-3">
            <DiagramPreview result={result} />
          </div>
        )}
      </div>
    </div>
  );
}
