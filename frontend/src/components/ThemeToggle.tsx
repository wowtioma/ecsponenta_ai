import { useTheme } from "../theme";

function SunIcon() {
  return (
    <svg
      viewBox="0 0 12 12"
      width="10"
      height="10"
      aria-hidden="true"
      fill="none"
    >
      <circle cx="6" cy="6" r="2.3" fill="currentColor" />
      <path
        d="M6 1v1.3M6 9.7V11M1 6h1.3M9.7 6H11M2.5 2.5l.9.9M8.6 8.6l.9.9M9.5 2.5l-.9.9M3.4 8.6l-.9.9"
        stroke="currentColor"
        strokeWidth="1.1"
        strokeLinecap="round"
      />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg
      viewBox="0 0 12 12"
      width="10"
      height="10"
      aria-hidden="true"
      fill="none"
    >
      <path
        d="M9.8 7.4A4.2 4.2 0 0 1 4.6 2.2 4.2 4.2 0 1 0 9.8 7.4Z"
        fill="currentColor"
      />
    </svg>
  );
}

export default function ThemeToggle() {
  const mode = useTheme((state) => state.mode);
  const toggle = useTheme((state) => state.toggle);

  const dark = mode === "dark";

  return (
    <button
      type="button"
      className="app-theme-toggle"
      role="switch"
      aria-checked={dark}
      aria-label={
        dark
          ? "Переключить на светлую тему"
          : "Переключить на тёмную тему"
      }
      title={
        dark
          ? "Светлая тема"
          : "Тёмная тема"
      }
      onClick={toggle}
    >
      <span className="app-theme-toggle__track" aria-hidden="true">
        <span className="app-theme-toggle__thumb">
          {dark ? <MoonIcon /> : <SunIcon />}
        </span>
      </span>

      <span className="app-theme-toggle__label">
        {dark ? "Тёмная" : "Светлая"}
      </span>
    </button>
  );
}
