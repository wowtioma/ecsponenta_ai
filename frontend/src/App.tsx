import type { CSSProperties } from "react";
import AppHeader from "./components/AppHeader";
import Chat from "./components/Chat";
import PanelSplitter from "./components/PanelSplitter";
import ResultPanel from "./components/ResultPanel";
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
      <AppHeader last={last} avg={avg} onReset={reset} />

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
