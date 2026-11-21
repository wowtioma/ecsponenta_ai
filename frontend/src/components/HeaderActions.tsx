import ThemeToggle from "./ThemeToggle";

/** Тайминги шага, переключатель темы и кнопка новой сессии. */
export default function HeaderActions({
  last,
  avg,
  onReset,
}: {
  last: number | null;
  avg: number | null;
  onReset: () => void;
}) {
  return (
    <div className="app-header__right">
      {last !== null && avg !== null && (
        <span className="app-header__timings">
          Шаг: {last.toFixed(1)} с · среднее: {avg.toFixed(1)} с
        </span>
      )}

      <ThemeToggle />

      <button
        type="button"
        onClick={onReset}
        className="app-button app-button-outline app-button-sm"
      >
        Новая сессия
      </button>
    </div>
  );
}
