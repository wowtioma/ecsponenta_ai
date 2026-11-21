import type { Usage } from "../types";

// ============================================================
// РАСХОДЫ НА СЕССИЮ
// ============================================================
//
// Бэкенд хранит usage накопительно на уровне сессии
// (см. llm-сессию: input_tokens/output_tokens/calls за всю сессию).
// Поэтому каждый пришедший usage считается актуальным итогом,
// а не добавкой к предыдущему. Если контракт изменится и бэкенд
// начнёт присылать расход только за один шаг, правку нужно внести
// только в mergeUsage ниже.
//
// Данные читаются терпимо: поддерживаются snake_case и camelCase,
// отсутствующие поля заменяются null, а не нулём, чтобы интерфейс
// мог честно показать «не подтверждено» вместо $0,00.

export type UsageCall = {
  id: string;
  model: string | null;
  purpose: string | null;
  inputTokens: number;
  outputTokens: number;
  costUsd: number | null;
};

export type SessionUsage = {
  inputTokens: number;
  outputTokens: number;
  inputCostUsd: number | null;
  outputCostUsd: number | null;
  evaluationCostUsd: number | null;
  actualCostUsd: number | null;
  calls: UsageCall[];
  models: string[];
  status: string | null;
  measured: boolean;
};

export type CostKind = "actual" | "estimated" | "none";

export const EMPTY_USAGE: SessionUsage = {
  inputTokens: 0,
  outputTokens: 0,
  inputCostUsd: null,
  outputCostUsd: null,
  evaluationCostUsd: null,
  actualCostUsd: null,
  calls: [],
  models: [],
  status: null,
  measured: false,
};

type Snapshot = {
  inputTokens: number | null;
  outputTokens: number | null;
  inputCostUsd: number | null;
  outputCostUsd: number | null;
  evaluationCostUsd: number | null;
  actualCostUsd: number | null;
  calls: UsageCall[];
  models: string[];
  status: string | null;
  measured: boolean;
};

// ============================================================
// ЧТЕНИЕ ПОЛЕЙ
// ============================================================

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : null;
}

function readNumber(
  record: Record<string, unknown>,
  keys: string[],
): number | null {
  for (const key of keys) {
    const value = record[key];

    if (typeof value === "number" && Number.isFinite(value) && value >= 0) {
      return value;
    }

    // Строковые числа тоже встречаются в ответах провайдеров
    if (typeof value === "string" && value.trim() !== "") {
      const parsed = Number(value);

      if (Number.isFinite(parsed) && parsed >= 0) return parsed;
    }
  }

  return null;
}

function readString(
  record: Record<string, unknown>,
  keys: string[],
): string | null {
  for (const key of keys) {
    const value = record[key];

    if (typeof value === "string" && value.trim() !== "") {
      return value.trim();
    }
  }

  return null;
}

function normalizeCall(raw: unknown, index: number): UsageCall | null {
  const record = asRecord(raw);

  if (!record) return null;

  const model = readString(record, [
    "model",
    "model_name",
    "modelName",
    "model_id",
  ]);

  const inputTokens =
    readNumber(record, [
      "input_tokens",
      "inputTokens",
      "prompt_tokens",
      "promptTokens",
    ]) ?? 0;

  const outputTokens =
    readNumber(record, [
      "output_tokens",
      "outputTokens",
      "completion_tokens",
      "completionTokens",
    ]) ?? 0;

  const costUsd = readNumber(record, [
    "cost_total_usd",
    "costTotalUsd",
    "cost_usd",
    "costUsd",
    "cost",
    "total_cost_usd",
    "totalCostUsd",
    "actual_cost_usd",
    "actualCostUsd",
  ]);

  // Стабильный идентификатор нужен, чтобы повторно присланный
  // вызов не раздувал счётчик вызовов.
  const explicitId = readString(record, [
    "call_id",
    "callId",
    "id",
  ]);

  const fallbackId = [
    "call",
    index,
    model ?? "",
    inputTokens,
    outputTokens,
    costUsd ?? "",
  ].join("-");

  return {
    id: explicitId ?? fallbackId,
    model,
    purpose: readString(record, [
      "purpose",
      "stage",
      "kind",
      "operation",
    ]),
    inputTokens,
    outputTokens,
    costUsd,
  };
}

function normalizeUsage(raw: Usage): Snapshot {
  const record = raw as Record<string, unknown>;

  const callsRaw = Array.isArray(record.calls) ? record.calls : [];

  const calls = callsRaw
    .map((call, index) => normalizeCall(call, index))
    .filter((call): call is UsageCall => call !== null);

  const models = new Set<string>();

  for (const model of Array.isArray(record.models) ? record.models : []) {
    if (typeof model === "string" && model.trim() !== "") {
      models.add(model.trim());
    }
  }

  const singleModel = readString(record, [
    "model",
    "model_name",
    "modelName",
  ]);

  if (singleModel) models.add(singleModel);

  for (const call of calls) {
    if (call.model) models.add(call.model);
  }

  const status = readString(record, ["status", "usage_status"]);

  const inputTokens = readNumber(record, [
    "input_tokens",
    "inputTokens",
    "prompt_tokens",
    "promptTokens",
  ]);

  const outputTokens = readNumber(record, [
    "output_tokens",
    "outputTokens",
    "completion_tokens",
    "completionTokens",
  ]);

  const inputCostUsd = readNumber(record, [
    "input_cost_usd",
    "inputCostUsd",
  ]);

  const outputCostUsd = readNumber(record, [
    "output_cost_usd",
    "outputCostUsd",
  ]);

  const evaluationCostUsd = readNumber(record, [
    "evaluation_cost_usd",
    "evaluationCostUsd",
    "estimated_cost_usd",
    "estimatedCostUsd",
  ]);

  const actualCostUsd = readNumber(record, [
    "actual_cost_usd",
    "actualCostUsd",
  ]);

  // Бэкенд присылает status: "not_measured" и нулевые токены,
  // когда расход ещё не измерен. Нули не должны выглядеть как данные.
  const hasNumbers =
    (inputTokens ?? 0) > 0 ||
    (outputTokens ?? 0) > 0 ||
    inputCostUsd !== null ||
    outputCostUsd !== null ||
    evaluationCostUsd !== null ||
    actualCostUsd !== null ||
    calls.length > 0;

  const measured = status === "not_measured" ? false : hasNumbers;

  return {
    inputTokens,
    outputTokens,
    inputCostUsd,
    outputCostUsd,
    evaluationCostUsd,
    actualCostUsd,
    calls,
    models: [...models],
    status,
    measured,
  };
}

function sumCalls(
  calls: UsageCall[],
  key: "inputTokens" | "outputTokens",
): number | null {
  if (calls.length === 0) return null;

  const total = calls.reduce((sum, call) => sum + call[key], 0);

  return total > 0 ? total : null;
}

function sumCallCosts(calls: UsageCall[]): number | null {
  const values = calls
    .map((call) => call.costUsd)
    .filter((value): value is number => value !== null);

  if (values.length === 0) return null;

  return values.reduce((sum, value) => sum + value, 0);
}

// ============================================================
// СЛИЯНИЕ ОТВЕТОВ БЭКЕНДА
// ============================================================

export function mergeUsage(
  previous: SessionUsage,
  raw: Usage | null | undefined,
): SessionUsage {
  if (!raw) return previous;

  const snapshot = normalizeUsage(raw);

  if (!snapshot.measured) {
    // Данные всё ещё не измерены: сохраняем статус, но не выдумываем нули
    return snapshot.status === previous.status
      ? previous
      : { ...previous, status: snapshot.status ?? previous.status };
  }

  // Повторно присланные вызовы не должны увеличивать счётчик
  const callsById = new Map<string, UsageCall>();

  for (const call of previous.calls) callsById.set(call.id, call);
  for (const call of snapshot.calls) callsById.set(call.id, call);

  const calls = [...callsById.values()];

  const models = [
    ...new Set([
      ...previous.models,
      ...snapshot.models,
      ...calls
        .map((call) => call.model)
        .filter((model): model is string => model !== null),
    ]),
  ];

  const callInputTokens = sumCalls(calls, "inputTokens");
  const callOutputTokens = sumCalls(calls, "outputTokens");

  // Берём наибольшее известное значение: так не теряются токены,
  // если бэкенд пришлёт частичный снимок usage
  const inputTokens =
    Math.max(snapshot.inputTokens ?? 0, callInputTokens ?? 0) ||
    previous.inputTokens;

  const outputTokens =
    Math.max(snapshot.outputTokens ?? 0, callOutputTokens ?? 0) ||
    previous.outputTokens;

  const next: SessionUsage = {
    inputTokens,
    outputTokens,

    inputCostUsd: snapshot.inputCostUsd ?? previous.inputCostUsd,
    outputCostUsd: snapshot.outputCostUsd ?? previous.outputCostUsd,
    evaluationCostUsd:
      snapshot.evaluationCostUsd ?? previous.evaluationCostUsd,
    actualCostUsd: snapshot.actualCostUsd ?? previous.actualCostUsd,

    calls,
    models,
    status: snapshot.status ?? previous.status,
    measured: true,
  };

  return next;
}

// ============================================================
// ПРОИЗВОДНЫЕ ВЕЛИЧИНЫ
// ============================================================

export function totalTokens(usage: SessionUsage): number {
  return usage.inputTokens + usage.outputTokens;
}

export function totalCost(usage: SessionUsage): {
  value: number | null;
  kind: CostKind;
} {
  // Оценочная стоимость с бэкенда — полная стоимость сессии
  // по тарифам модели; фактическая может быть подтверждена
  // только для части вызовов, поэтому не подменяет итог.
  const parts = [usage.inputCostUsd, usage.outputCostUsd].filter(
    (value): value is number => value !== null,
  );

  const estimated =
    usage.evaluationCostUsd ??
    (parts.length > 0
      ? parts.reduce((sum, value) => sum + value, 0)
      : null);

  if (estimated !== null) {
    // Если провайдер подтвердил всю сумму, показываем её как факт
    if (
      usage.actualCostUsd !== null &&
      usage.actualCostUsd + 1e-9 >= estimated
    ) {
      return { value: usage.actualCostUsd, kind: "actual" };
    }

    return { value: estimated, kind: "estimated" };
  }

  if (usage.actualCostUsd !== null) {
    return { value: usage.actualCostUsd, kind: "actual" };
  }

  const callCosts = sumCallCosts(usage.calls);

  if (callCosts !== null) {
    return { value: callCosts, kind: "estimated" };
  }

  return { value: null, kind: "none" };
}

// ============================================================
// ФОРМАТИРОВАНИЕ
// ============================================================

const integerFormatter = new Intl.NumberFormat("ru-RU");

export function formatTokens(value: number): string {
  return integerFormatter.format(value);
}

export function formatUsd(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "—";
  }

  if (value === 0) return "$0";

  // Совсем малые суммы не должны превращаться в $0,00
  if (value < 0.0001) return "< $0,0001";

  const digits = value < 0.01 ? 4 : 2;

  const formatted = new Intl.NumberFormat("ru-RU", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);

  return `$${formatted}`;
}
