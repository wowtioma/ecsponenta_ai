
import Chat from "./components/Chat";
import ResultPanel from "./components/ResultPanel";
import { useStore } from "./store";

export default function App() {
  const { timings, reset } = useStore();

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

          <span className="app-header__title">
            ИИ-ассистент по размещению «Синоникса»
          </span>
        </div>

        <div className="app-header__right">
          {last !== null && avg !== null && (
            <span className="app-header__timings">
              Шаг: {last.toFixed(1)} с · среднее: {avg.toFixed(1)} с
            </span>
          )}

          <button
            type="button"
            onClick={reset}
            className="app-button-outline px-4 py-2 text-sm"
          >
            Новая сессия
          </button>
        </div>
      </header>

      <main className="app-main">
        <section className="app-chat-section">
          <Chat />
        </section>

        <section className="app-result-section">
          <ResultPanel />
        </section>
      </main>
    </div>
  );
}
