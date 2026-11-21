import HeaderActions from "./HeaderActions";
import HeaderBrand from "./HeaderBrand";

/** Верхняя панель приложения. */
export default function AppHeader({
  last,
  avg,
  onReset,
}: {
  last: number | null;
  avg: number | null;
  onReset: () => void;
}) {
  return (
    <header className="app-header">
      <HeaderBrand />

      <HeaderActions last={last} avg={avg} onReset={onReset} />
    </header>
  );
}
