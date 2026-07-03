// Mirrors backend/app/schemas.py — kept minimal to avoid drift.

export type Citation = {
  source_name: string;
  source_url: string;
  course_id: string | null;
  snippet: string;
};

export type ToolCall = {
  tool_name: string;
  arguments: Record<string, unknown>;
  status: "ok" | "error" | "empty";
  latency_ms: number;
  result_summary?: Record<string, unknown> | null;
  error?: string | null;
};

export type DebugTrace = {
  intent: string;
  tool_calls: ToolCall[];
  retrieved_chunks: Array<Record<string, unknown>>;
  recommendation_scores: Array<Record<string, unknown>>;
};

export type ChatMessageMeta = {
  citations: Citation[];
  used_tools: string[];
  latency_ms: number;
  debug_trace?: DebugTrace;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  meta?: ChatMessageMeta;
  streaming?: boolean;
  error?: string;
};

// Server-Sent Events emitted by POST /api/chat/stream.
export type ChatStreamEvent =
  | { type: "content"; delta: string }
  | ({ type: "metadata" } & ChatMessageMeta);

// POST /api/compare
export type ComparisonCourseItem = {
  course_id: string;
  title: string | null;
  career_tags: string[];
  direction_match: "match" | "no_match" | "not_requested";
  average_gpa: number | null;
  prerequisite_readiness: string;
  missing_prerequisites: string[];
  notes: string[];
};

export type ComparisonDetail = {
  course_ids: string[];
  dimension: string | null;
  courses: ComparisonCourseItem[];
  notes: string[];
};

export type CompareResponse = {
  summary: string;
  courses: Array<{ course_id: string; title: string; notes: string[] }>;
  comparison: ComparisonDetail;
  citations: Citation[];
};

// POST /api/recommend
export type Recommendation = {
  course_id: string;
  title: string;
  reason: string;
  citations: Citation[];
};

export type RecommendDebugScore = {
  course_id: string;
  title: string;
  score: number;
  score_breakdown: Record<string, number>;
  reason_codes: string[];
  target_direction: string;
  completed_courses: string[];
};

export type RecommendResponse = {
  recommendations: Recommendation[];
  debug_scores: RecommendDebugScore[] | null;
};
