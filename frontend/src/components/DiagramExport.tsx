
import type { Result } from "../types";

import { exportJson } from "../lib/exportJson";

interface DiagramExportProps {
  result: Result;
}

/**
 * Экспорт результата расчёта в JSON.
 * Скачивание .drawio живёт рядом со схемой: у статичного
 * просмотра и у редактора draw.io — свои кнопки.
 */
export default function DiagramExport({
  result,
}: DiagramExportProps) {
  return (
    <div className="diagram-export">
      <button
        type="button"
        onClick={() => exportJson(result)}
        className="app-button app-button-outline app-button-sm"
      >
        JSON для эксперта
      </button>
    </div>
  );
}
