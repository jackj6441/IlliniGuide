import type {
  ChatStreamEvent,
  CompareResponse,
  RecommendResponse,
} from "./types";

// Thin JSON POST helper: preserves 4xx body for readable error messages.
async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text().catch(() => "");
    throw new Error(`HTTP ${response.status}: ${text.slice(0, 240)}`);
  }
  return response.json() as Promise<T>;
}

export function compareCourses(
  courseIds: string[],
  dimension: string | null,
): Promise<CompareResponse> {
  return postJSON<CompareResponse>("/api/compare", {
    course_ids: courseIds,
    dimension,
    debug: true,
  });
}

export function recommendCourses(
  targetDirection: string,
  completedCourses: string[],
  maxResults: number,
): Promise<RecommendResponse> {
  return postJSON<RecommendResponse>("/api/recommend", {
    target_direction: targetDirection,
    completed_courses: completedCourses,
    max_results: maxResults,
    debug: true,
  });
}

// Streams events from POST /api/chat/stream.
//
// SSE framing recap: one event = "data: <json>\n\n". A single TCP read may
// hand us half an event, or several events at once, so we buffer raw text
// and split on "\n\n", keeping the trailing partial for the next round.
// TextDecoder({ stream: true }) preserves multibyte characters that get
// split across chunks (relevant if the model emits CJK or emoji).
export async function* streamChat(
  message: string,
  options: { debug?: boolean; signal?: AbortSignal } = {},
): AsyncGenerator<ChatStreamEvent> {
  const { debug = true, signal } = options;

  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, debug }),
    signal,
  });

  if (!response.ok || !response.body) {
    const text = await response.text().catch(() => "");
    throw new Error(
      `Chat stream failed: HTTP ${response.status} ${text.slice(0, 160)}`,
    );
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const chunks = buffer.split("\n\n");
      buffer = chunks.pop() ?? "";

      for (const raw of chunks) {
        const event = parseSSEChunk(raw);
        if (event === "DONE") return;
        if (event) yield event;
      }
    }
  } finally {
    // Best-effort release; ignore errors on cancel.
    reader.releaseLock();
  }
}

function parseSSEChunk(raw: string): ChatStreamEvent | "DONE" | null {
  // A chunk may contain multiple lines (comment lines, event lines, data
  // lines) — we only care about "data:" lines.
  const dataLine = raw
    .split("\n")
    .map((l) => l.trim())
    .find((l) => l.startsWith("data:"));
  if (!dataLine) return null;
  const payload = dataLine.slice(5).trim();
  if (payload === "[DONE]") return "DONE";
  try {
    return JSON.parse(payload) as ChatStreamEvent;
  } catch {
    // Malformed frame — drop it rather than tearing down the stream.
    return null;
  }
}
