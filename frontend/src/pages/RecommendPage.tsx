import { useState } from "react";
import { recommendCourses } from "../lib/api";
import type {
  RecommendDebugScore,
  RecommendResponse,
  Recommendation,
} from "../lib/types";
import styles from "./RecommendPage.module.css";

const DIRECTIONS = [
  { value: "ai_infra", label: "AI infrastructure" },
  { value: "systems", label: "Systems" },
  { value: "software", label: "Software" },
  { value: "hardware", label: "Hardware" },
];

type Status =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; data: RecommendResponse }
  | { kind: "error"; message: string };

export default function RecommendPage() {
  const [direction, setDirection] = useState("ai_infra");
  const [completedText, setCompletedText] = useState("ECE 220, ECE 391");
  const [maxResults, setMaxResults] = useState(5);
  const [status, setStatus] = useState<Status>({ kind: "idle" });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const completed = completedText
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    setStatus({ kind: "loading" });
    try {
      const data = await recommendCourses(direction, completed, maxResults);
      setStatus({ kind: "ok", data });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setStatus({ kind: "error", message: msg });
    }
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.eyebrow}>Recommend</div>
        <h1 className={styles.title}>Recommend courses by career direction</h1>
        <p className={styles.lead}>
          Rule-based recommender weighing direction match, prerequisite
          readiness, course-level progression, and GPA risk — powered by the
          <span> </span>
          <code>recommend_courses</code> tool.
        </p>
      </header>

      <form className={styles.form} onSubmit={submit}>
        <div className={styles.chipRow}>
          <span className={styles.chipRowLabel}>Direction</span>
          <div className={styles.chips}>
            {DIRECTIONS.map((d) => (
              <button
                key={d.value}
                type="button"
                className={
                  direction === d.value
                    ? `${styles.chip} ${styles.chipActive}`
                    : styles.chip
                }
                onClick={() => setDirection(d.value)}
                disabled={status.kind === "loading"}
              >
                {d.label}
              </button>
            ))}
          </div>
        </div>

        <label className={styles.field}>
          <span className={styles.fieldLabel}>Completed courses</span>
          <input
            className={styles.input}
            value={completedText}
            onChange={(e) => setCompletedText(e.target.value)}
            placeholder="ECE 220, ECE 391"
            disabled={status.kind === "loading"}
          />
          <span className={styles.fieldHint}>
            comma-separated course IDs; leave empty to see all candidates
          </span>
        </label>

        <div className={styles.controls}>
          <label className={styles.fieldInline}>
            <span className={styles.fieldLabel}>Max results</span>
            <input
              className={styles.number}
              type="number"
              min={1}
              max={10}
              value={maxResults}
              onChange={(e) =>
                setMaxResults(Math.max(1, Math.min(10, Number(e.target.value))))
              }
              disabled={status.kind === "loading"}
            />
          </label>
          <button
            type="submit"
            className={styles.submit}
            disabled={status.kind === "loading"}
          >
            {status.kind === "loading" ? "Scoring…" : "Recommend"}
          </button>
        </div>
      </form>

      {status.kind === "error" && (
        <div className={styles.error}>{status.message}</div>
      )}

      {status.kind === "ok" && <Result data={status.data} />}
    </div>
  );
}

function Result({ data }: { data: RecommendResponse }) {
  const debugMap = new Map<string, RecommendDebugScore>();
  for (const score of data.debug_scores ?? []) {
    debugMap.set(score.course_id, score);
  }

  if (data.recommendations.length === 0) {
    return (
      <div className={styles.empty}>
        <div className={styles.emptyTitle}>No candidates</div>
        <p className={styles.emptyBody}>
          The recommender found no courses matching this direction with
          positive scores. Either the DB has no career-tagged courses, or all
          candidates were already in your completed list.
        </p>
      </div>
    );
  }

  return (
    <section className={styles.result}>
      <div className={styles.list}>
        {data.recommendations.map((rec, i) => (
          <RecommendationCard
            key={rec.course_id}
            rank={i + 1}
            rec={rec}
            debug={debugMap.get(rec.course_id)}
          />
        ))}
      </div>
    </section>
  );
}

function RecommendationCard({
  rank,
  rec,
  debug,
}: {
  rank: number;
  rec: Recommendation;
  debug?: RecommendDebugScore;
}) {
  return (
    <div className={styles.card}>
      <div className={styles.cardHeader}>
        <span className={styles.rank}>#{rank}</span>
        <div className={styles.cardTitle}>
          <span className={styles.courseId}>{rec.course_id}</span>
          <span className={styles.courseTitle}>{rec.title}</span>
        </div>
        {debug && (
          <span className={styles.score} title="composite score">
            {debug.score.toFixed(2)}
          </span>
        )}
      </div>

      <p className={styles.reason}>{rec.reason}</p>

      {debug && <ScoreBreakdown breakdown={debug.score_breakdown} />}
    </div>
  );
}

function ScoreBreakdown({
  breakdown,
}: {
  breakdown: Record<string, number>;
}) {
  const entries = Object.entries(breakdown);
  return (
    <div className={styles.breakdown}>
      <div className={styles.breakdownLabel}>score breakdown</div>
      <div className={styles.bars}>
        {entries.map(([key, value]) => (
          <div key={key} className={styles.bar}>
            <span className={styles.barLabel}>
              {key.replace(/_/g, " ")}
            </span>
            <div className={styles.barTrack}>
              <div
                className={styles.barFill}
                style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }}
              />
            </div>
            <span className={styles.barValue}>{value.toFixed(2)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
