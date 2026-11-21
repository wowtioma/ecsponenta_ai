
import { z } from "zod";

export const networkSchema = z.object({
  id: z.string(),
  name: z.string(),
  trust: z.enum(["open", "closed"]),
});

export const ruleSchema = z
  .object({
    id: z.number(),
    type: z.enum(["data", "file"]),
        from: z.string(),
    to: z.string(),

    // Конкретные устройства, участвующие в передаче
    from_device_id: z.string().nullish(),
    to_device_id: z.string().nullish(),

    // Способ передачи данных
    transport: z.enum(["network", "usb"]).optional(),

    mode: z.enum(["one-way", "two-way"]),
    protocol: z
      .union([
        z.string(),
        z
          .object({
            open: z.string().nullish(),
            closed: z.string().nullish(),
          })
          .passthrough(),
      ])
      .nullish(),
    port: z.number().nullish(),
    description: z.string(),
    justification: z.string().nullish(),

    // Дополнительные параметры файловых правил
    methods_by_node: z.unknown().optional(),
    checks_by_node: z.unknown().optional(),
  })
  .passthrough();

export const deviceSchema = z.object({
  id: z.string(),
  network_id: z.string(),
  name: z.string(),
});

export const sourceSchema = z.object({
  file: z.string(),
  section: z.string().nullish(),
  page: z.union([z.string(), z.number()]).nullish(),
});

export const usageSchema = z
  .object({
    status: z.string().nullish(),
    input_tokens: z.number().nullish(),
    output_tokens: z.number().nullish(),
    input_cost_usd: z.number().nullish(),
    output_cost_usd: z.number().nullish(),
    evaluation_cost_usd: z.number().nullish(),
    actual_cost_usd: z.number().nullish(),
    calls: z.array(z.unknown()).default([]),
  })
  .passthrough();

export const resultSchema = z
  .object({
    networks: z.array(networkSchema),
    firewall: z.object({ side: z.string() }).nullish(),
    rules: z.array(ruleSchema),
    rules_count: z.number(),
    synonyx: z
      .object({
        location: z.string(),
        node_a_faces: z.string(),
        node_b_faces: z.string(),
      })
      .nullish(),
    file_users_count: z.number().nullable(),
    file_users_range: z
      .object({
        min: z.number(),
        max: z.number().nullable(),
      })
      .nullish(),
    schema_version: z.string().optional(),
    session_id: z.string().optional(),
    status: z.enum([
      "needs_clarification",
      "preliminary",
      "completed",
      "unsupported",
    ]),
    unknowns: z.array(z.string()).default([]),
    assumptions: z.array(z.string()).default([]),
    devices: z.array(deviceSchema).default([]),
    sources: z.array(sourceSchema).default([]),
    requests_for_vendor: z.array(z.unknown()).default([]),
    usage: usageSchema.nullish(),
    timing: z.unknown().nullish(),
  })
  .passthrough();

// Вопрос ассистента.
// Варианты «Не знаю» и «Другое» фронт добавляет самостоятельно.
export const questionSchema = z.object({
  id: z.string(),
  text: z.string(),
  options: z.array(z.string()),
});

export const chatResponseSchema = z.object({
  text: z.string(),
  explanation: z.string().nullish(),
  questions: z.array(questionSchema).nullish(),
  sources: z.array(sourceSchema).nullish(),
  result: resultSchema.nullish(),
});

export type Network = z.infer<typeof networkSchema>;
export type Rule = z.infer<typeof ruleSchema>;
export type Device = z.infer<typeof deviceSchema>;
export type Source = z.infer<typeof sourceSchema>;
export type Usage = z.infer<typeof usageSchema>;
export type Result = z.infer<typeof resultSchema>;
export type Question = z.infer<typeof questionSchema>;
export type ChatResponse = z.infer<typeof chatResponseSchema>;

export type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
  questions?: Question[];
  sources?: Source[];
  isError?: boolean;
};
