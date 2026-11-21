import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useStore } from "../store";
import RulesTable from "./RulesTable";
import { diagramDocumentKey } from "../lib/drawioDocument";
import DrawioEditor from "./DrawioEditor";
import DiagramExport from "./DiagramExport";
import { fileUsersLabel } from "../lib/format";
import type { Result } from "../types";

type Tab = "explanation" | "rules" | "diagram";

type DiagramMode = "editor" | "preview";

const TABS: { id: Tab; label: string }[] = [
  { id: "explanation", label: "Объяснение" },
  { id: "rules", label: "Таблица правил" },
  { id: "diagram", label: "Схема" },
];

const STATUS_CLASS: Record<Result["status"], string> = {
  needs_clarification: "app-badge app-badge--progress",
  preliminary: "app-badge app-badge--warning",
  completed: "app-badge app-badge--success",
  unsupported: "app-badge app-badge--error",
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
    <div className="app-note">
      <div className="app-note__title">{title}</div>

      <ul className="app-note__list">
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

  // Схема по умолчанию открывается в редакторе draw.io;
  // статичный просмотр остаётся запасным вариантом
  const [diagramMode, setDiagramMode] =
    useState<DiagramMode>("editor");

  // Пока первый запрос выполняется и результата ещё нет
  if (!result && loading) {
    return (
      <div className="app-result">
        <div className="app-empty">
          <span className="app-badge app-badge--muted app-badge--pulse">
            Обновляется
          </span>

          <p>Анализирую данные и формирую результат…</p>
        </div>
      </div>
    );
  }

  // Если результата пока нет и запрос не выполняется
  if (!result) {
    return (
      <div className="app-result">
        <div className="app-empty">
          <div className="app-empty__mark" aria-hidden="true">
            ◫
          </div>

          <p>
            Результат появится здесь после описания сетей в чате
          </p>
        </div>
      </div>
    );
  }

  const documentKey = tab === "diagram" ? diagramDocumentKey(result) : "";

  return (
    <div className="app-result">
      {/* Статус и основные показатели */}
      <div className="app-result__head">
        <div className="app-result__statusrow">
          {loading ? (
            <span className="app-badge app-badge--muted app-badge--pulse">
              Обновляется…
            </span>
          ) : (
            <span className={STATUS_CLASS[result.status]}>
              {statusText(result.status)}
            </span>
          )}

          {resultIsStale && (
            <span className="app-stale">
              Показан предыдущий результат
            </span>
          )}
        </div>

        {/* Основные показатели */}
        <div className="app-result__metrics">
          <span className="app-metric">
            Правил: <b>{result.rules_count}</b>
          </span>

          <span className="app-metric">
            Пользователей файловой передачи:{" "}
            <b>{fileUsersLabel(result)}</b>
          </span>
        </div>

        {/* Пояснение при обновлении или сохранении старого результата */}
        {loading && (
          <p className="app-hint">
            Выполняется новый запрос. Пока отображается предыдущая
            конфигурация, она ещё не подтверждена новым ответом.
          </p>
        )}

        {!loading && resultIsStale && (
          <p className="app-hint app-hint--warning">
            Последний запрос не вернул новую конфигурацию.
            Ниже показан последний рассчитанный результат.
          </p>
        )}

        {/* Дополнительные пояснения по статусам */}
        {!loading && result.status === "needs_clarification" && (
          <p className="app-hint">
            Проект ещё не готов: ответьте на вопросы ассистента в чате.
          </p>
        )}

        {!loading && result.status === "unsupported" && (
          <p className="app-hint app-hint--warning">
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
      <div className="app-tabs" role="tablist" aria-label="Разделы результата">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            onClick={() => setTab(item.id)}
            className={`app-tab${
              tab === item.id ? " app-tab--active" : ""
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {/* Содержимое вкладок */}
      <div
        className={`app-result__body${
          loading || resultIsStale
            ? " app-result__body--stale"
            : ""
        }`}
        role="tabpanel"
      >
        {tab === "explanation" && (
          <div className="app-result__pane">
            {explanation ? (
              <div className="app-markdown">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {explanation}
                </ReactMarkdown>
              </div>
            ) : (
              <p className="app-hint">Объяснение пока недоступно.</p>
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
          <div className="app-result__pane">
            <RulesTable result={result} />
          </div>
        )}

        {tab === "diagram" && (
          <div className="app-result__pane app-result__pane--diagram">
            <div className="diagram-viewbar">
              <div
                className="diagram-viewswitch"
                role="group"
                aria-label="Режим отображения схемы"
              >
                <button
                  type="button"
                  onClick={() => setDiagramMode("editor")}
                  aria-pressed={diagramMode === "editor"}
                  className={`diagram-viewswitch__btn${
                    diagramMode === "editor" ? " is-active" : ""
                  }`}
                >
                  Редактор
                </button>

                <button
                  type="button"
                  onClick={() => setDiagramMode("preview")}
                  aria-pressed={diagramMode === "preview"}
                  className={`diagram-viewswitch__btn${
                    diagramMode === "preview" ? " is-active" : ""
                  }`}
                >
                  Просмотр
                </button>
              </div>

              <DiagramExport result={result} />
            </div>

            <DrawioEditor
              key={documentKey}
              documentKey={documentKey}
              result={result}
              preview={diagramMode === "preview"}
              onPreview={() => setDiagramMode("preview")}
            />
          </div>
        )}
      </div>
    </div>
  );
}
