
import type { Result } from "../types";

export function exportJson(result: Result): void {
  const json = JSON.stringify(result, null, 2);

  const blob = new Blob(
    [json],
    { type: "application/json;charset=utf-8" }
  );

  const url = URL.createObjectURL(blob);

  const link = document.createElement("a");
  link.href = url;
  link.download = "synonyx-result.json";

  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);

  URL.revokeObjectURL(url);
}
