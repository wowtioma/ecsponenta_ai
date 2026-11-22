import { useState } from "react";
import { useStore } from "../store";
import {
  formatTokens,
  formatUsd,
  totalCost,
  totalTokens,
} from "../lib/usage";

function ChevronIcon() {
  return (
    <svg
      viewBox="0 0 12 12"
      width="11"
      height="11"
      aria-hidden="true"
      fill="none"
    >
      <path
        d="M2.5 4.5 6 8l3.5-3.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

// Компактный блок расходов внизу чата: токены и деньги за сессию
export default function UsageFooter() {
  const usage = useStore((state) => state.usage);
  const [open, setOpen] = useState(false);

  const tokens = totalTokens(usage);
  const cost = totalCost(usage);

  return (
    <section
      className={`app-usage${open ? " app-usage--open" : ""}`}
      aria-label="Расходы на сессию"
    >
      <button
        type="button"
        className="app-usage__summary"
        aria-expanded={open}
        aria-controls="usage-details"
        onClick={() => setOpen((value) => !value)}
      >
        <span className="app-usage__title">Расходы</span>

        {usage.measured ? (
          <>
            <span className="app-usage__value">
              {formatTokens(tokens)} ток.
            </span>

            <span className="app-usage__sep" aria-hidden="true">
              ·
            </span>

            <span className="app-usage__value">
              {formatUsd(cost.value)}
            </span>

            {usage.status === "partial" && <span className="app-usage__tag">частичные данные</span>}
            {cost.kind === "estimated" && (
              <span className="app-usage__tag">оценка</span>
            )}
          </>
        ) : (
          <span className="app-usage__value app-usage__value--muted">
            не измерены
          </span>
        )}

        <span className="app-usage__chevron">
          <ChevronIcon />
        </span>
      </button>

      {open && (
        <div className="app-usage__details" id="usage-details">
          <dl className="app-usage__grid">
            <div>
              <dt>Входные токены</dt>
              <dd>{formatTokens(usage.inputTokens)}</dd>
            </div>

            <div>
              <dt>Выходные токены</dt>
              <dd>{formatTokens(usage.outputTokens)}</dd>
            </div>

            <div>
              <dt>Стоимость входа</dt>
              <dd>{formatUsd(usage.inputCostUsd)}</dd>
            </div>

            <div>
              <dt>Стоимость выхода</dt>
              <dd>{formatUsd(usage.outputCostUsd)}</dd>
            </div>

            {usage.evaluationCostUsd !== null && (
              <div>
                <dt>Оценочная стоимость</dt>
                <dd>{formatUsd(usage.evaluationCostUsd)}</dd>
              </div>
            )}

            <div>
              <dt>Фактическая стоимость</dt>
              <dd>
                {usage.actualCostUsd === null
                  ? "Не подтверждено"
                  : formatUsd(usage.actualCostUsd)}
              </dd>
            </div>

            {usage.calls.length > 0 && (
              <div>
                <dt>Вызовов модели</dt>
                <dd>{formatTokens(usage.calls.length)}</dd>
              </div>
            )}

            {usage.models.length > 0 && (
              <div className="app-usage__grid-wide">
                <dt>Модели</dt>
                <dd>{usage.models.join(", ")}</dd>
              </div>
            )}
          </dl>

          {!usage.measured && (
            <p className="app-usage__note">
              Бэкенд не прислал данных о расходе для этой сессии.
            </p>
          )}

          {usage.measured && usage.actualCostUsd === null && (
            <p className="app-usage__note">
              Фактическая стоимость не подтверждена — показана оценка
              по тарифам модели.
            </p>
          )}

          {usage.measured &&
            usage.actualCostUsd !== null &&
            usage.evaluationCostUsd !== null &&
            usage.actualCostUsd < usage.evaluationCostUsd && (
              <p className="app-usage__note">
                Фактическая стоимость подтверждена не для всех вызовов —
                в итоге показана оценка.
              </p>
            )}
        </div>
      )}
    </section>
  );
}
