import type { CSSProperties } from "react";
import Chat from "./components/Chat";
import PanelSplitter from "./components/PanelSplitter";
import ResultPanel from "./components/ResultPanel";
import ThemeToggle from "./components/ThemeToggle";
import { useStore } from "./store";
import { usePanelWidth } from "./usePanelWidth";

export default function App() {
  const { timings, reset } = useStore();

  const {
    width,
    collapsed,
    setWidth,
    adjust,
    resetWidth,
    toggleCollapsed,
  } = usePanelWidth();

  const last = timings.length
    ? timings[timings.length - 1] / 1000
    : null;

  const avg = timings.length
    ? timings.reduce((a, b) => a + b, 0) / timings.length / 1000
    : null;

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-header__brand">
          <img
            src="/logo_shield.png"
            alt="Логотип Синоникс"
            className="app-header__logo"
          />

          <div className="app-header__titles">
            <span className="app-header__title">
              <span className="app-header__title-full">
                ИИ-ассистент по размещению «Синоникса»
              </span>

              <span className="app-header__title-short">
                ИИ-ассистент «Синоникс»
              </span>
            </span>

            <span className="app-header__subtitle">
              Расчёт правил обмена между двумя сетями
            </span>
          </div>
        </div>

        <div className="app-header__right">
          {last !== null && avg !== null && (
            <span className="app-header__timings">
              Шаг: {last.toFixed(1)} с · среднее: {avg.toFixed(1)} с
            </span>
          )}

          <ThemeToggle />

          <button
            type="button"
            onClick={reset}
            className="app-button app-button-outline app-button-sm"
          >
            Новая сессия
          </button>
        </div>
      </header>

      <main
        className="app-main"
        style={
          { "--result-width": `${width}px` } as CSSProperties
        }
      >
        <section className="app-chat-section" aria-label="Чат с ассистентом">
          <Chat />
        </section>

        <PanelSplitter
          width={width}
          collapsed={collapsed}
          onResize={setWidth}
          onStep={adjust}
          onToggleCollapsed={toggleCollapsed}
          onReset={resetWidth}
        />

        <section
          className={
            collapsed
              ? "app-result-section is-collapsed"
              : "app-result-section"
          }
          aria-label="Результат расчёта"
        >
          <ResultPanel />
        </section>
      </main>
    </div>
  );
}
