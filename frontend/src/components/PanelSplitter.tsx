import { useEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent, KeyboardEvent } from "react";
import {
  clamp,
  PANEL_MIN_CHAT_WIDTH,
  PANEL_MIN_WIDTH,
  PANEL_STEP,
  SPLITTER_WIDTH,
} from "../usePanelWidth";

type PanelSplitterProps = {
  width: number;
  collapsed: boolean;
  onResize: (width: number) => void;
  onStep: (delta: number) => void;
  onToggleCollapsed: () => void;
  onReset: () => void;
};

// Иконка из макета: прямоугольник, разделённый вертикальной линией,
// правая часть заштрихована — «раздвинуть панель».
function PanelIcon({ mirrored = false }: { mirrored?: boolean }) {
  return (
    <svg
      viewBox="0 0 20 20"
      width="17"
      height="17"
      aria-hidden="true"
      className={
        mirrored
          ? "app-splitter__icon app-splitter__icon--mirrored"
          : "app-splitter__icon"
      }
      fill="none"
    >
      <rect
        x="2.4"
        y="3.8"
        width="15.2"
        height="12.4"
        rx="3"
        stroke="currentColor"
        strokeWidth="1.5"
      />
      <line
        x1="13.1"
        y1="3.8"
        x2="13.1"
        y2="16.2"
        stroke="currentColor"
        strokeWidth="1.5"
      />
      <path
        d="M13.4 5.2h1.9c0 1.6-1.9 2.2-1.9 3.8 0 1.6 1.9 2.2 1.9 3.8 0 1.6-1.9 2.2-1.9 3.4"
        stroke="currentColor"
        strokeWidth="1.1"
        strokeLinecap="round"
        opacity="0.55"
      />
    </svg>
  );
}

export default function PanelSplitter({
  width,
  collapsed,
  onResize,
  onStep,
  onToggleCollapsed,
  onReset,
}: PanelSplitterProps) {
  const ref = useRef<HTMLDivElement>(null);
  const drag = useRef<{
    pointerId: number;
    startX: number;
    startWidth: number;
  } | null>(null);

  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    document.body.classList.toggle("is-resizing", dragging);

    return () => document.body.classList.remove("is-resizing");
  }, [dragging]);

  const maxWidth = () => {
    const parent = ref.current?.parentElement;

    const total =
      parent?.getBoundingClientRect().width ??
      (typeof window === "undefined" ? 1440 : window.innerWidth);

    return Math.max(
      PANEL_MIN_WIDTH,
      total - PANEL_MIN_CHAT_WIDTH - SPLITTER_WIDTH,
    );
  };

  const startDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (collapsed || event.button !== 0) return;

    event.preventDefault();

    event.currentTarget.setPointerCapture(event.pointerId);

    drag.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startWidth: width,
    };

    setDragging(true);
  };

  const moveDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    const state = drag.current;

    if (!state) return;

    // Двигаем влево — панель расширяется
    const next =
      state.startWidth + (state.startX - event.clientX);

    onResize(clamp(next, PANEL_MIN_WIDTH, maxWidth()));
  };

  const endDrag = () => {
    if (!drag.current) return;

    drag.current = null;
    setDragging(false);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      onStep(PANEL_STEP);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      onStep(-PANEL_STEP);
    } else if (event.key === "Home") {
      event.preventDefault();
      onReset();
    } else if (event.key === "End") {
      event.preventDefault();
      onResize(maxWidth());
    }
  };

  const classes = [
    "app-splitter",
    collapsed ? "app-splitter--collapsed" : "",
    dragging ? "app-splitter--dragging" : "",
  ]
    .filter(Boolean)
    .join(" ");

  // Для aria-атрибутов не читаем DOM во время рендера
  const ariaMax = Math.max(
    PANEL_MIN_WIDTH,
    (typeof window === "undefined" ? 1440 : window.innerWidth) -
      PANEL_MIN_CHAT_WIDTH -
      SPLITTER_WIDTH,
  );

  return (
    <div ref={ref} className={classes}>
      {/* Полоса перетаскивания и клавиатурного управления шириной */}
      <div
        className="app-splitter__drag"
        role="separator"
        aria-orientation="vertical"
        aria-label="Ширина панели результатов"
        aria-valuemin={PANEL_MIN_WIDTH}
        aria-valuemax={Math.round(ariaMax)}
        aria-valuenow={Math.round(width)}
        aria-disabled={collapsed}
        tabIndex={collapsed ? -1 : 0}
        onPointerDown={startDrag}
        onPointerMove={moveDrag}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onLostPointerCapture={endDrag}
        onDoubleClick={onReset}
        onKeyDown={handleKeyDown}
      />

      <div className="app-splitter__actions">
        {!collapsed && (
          <button
            type="button"
            className="app-splitter__btn"
            onClick={() => onStep(-PANEL_STEP)}
            title="Сузить панель"
            aria-label="Сузить панель результатов"
          >
            −
          </button>
        )}

        <button
          type="button"
          className="app-splitter__btn app-splitter__btn--main"
          onClick={onToggleCollapsed}
          title={
            collapsed
              ? "Показать панель результатов"
              : "Скрыть панель результатов"
          }
          aria-label={
            collapsed
              ? "Показать панель результатов"
              : "Скрыть панель результатов"
          }
          aria-pressed={collapsed}
        >
          <PanelIcon mirrored={collapsed} />
        </button>

        {!collapsed && (
          <button
            type="button"
            className="app-splitter__btn"
            onClick={() => onStep(PANEL_STEP)}
            title="Расширить панель"
            aria-label="Расширить панель результатов"
          >
            +
          </button>
        )}
      </div>

      {collapsed && (
        <span className="app-splitter__rail" aria-hidden="true">
          Результат
        </span>
      )}
    </div>
  );
}
