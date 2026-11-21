import Chat from "./components/Chat";
import ResultPanel from "./components/ResultPanel";
import { useStore } from "./store";

export default function App() {
  const { timings, reset } = useStore();
  const last = timings.length ? timings[timings.length - 1] / 1000 : null;
  const avg = timings.length ? timings.reduce((a, b) => a + b, 0) / timings.length / 1000 : null;

  return (
    <div className="flex h-screen flex-col bg-black text-white">
      
<header className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
  {/* Логотип и название */}
  <div className="flex min-w-0 items-center gap-3">
    <img
      src="/logo_shield.png"
      alt="Логотип Синоникс"
      className="h-10 w-10 shrink-0 object-contain"
    />

    <span className="text-sm font-semibold sm:text-base">
      ИИ-ассистент по размещению «Синоникса»
    </span>
  </div>

  {/* Правая часть шапки */}
  <div className="flex shrink-0 items-center gap-4">
    {last !== null && avg !== null && (
      <span className="text-xs text-zinc-500">
        Шаг: {last.toFixed(1)} с · среднее: {avg.toFixed(1)} с
      </span>
    )}

    <button
      onClick={reset}
      className="rounded-lg border border-zinc-600 px-3 py-1 text-sm hover:bg-zinc-900"
    >
      Новая сессия
    </button>
  </div>
</header>


      <main className="grid min-h-0 flex-1 grid-cols-[minmax(360px,1fr)_minmax(520px,1.3fr)]">
        <section className="min-h-0 min-w-0 border-r border-zinc-800">
          <Chat />
        </section>
        <section className="min-h-0 min-w-0">
          <ResultPanel />
        </section>
      </main>
    </div>
  );
}