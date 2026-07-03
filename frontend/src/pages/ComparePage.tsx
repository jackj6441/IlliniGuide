import { useState } from "react";
import CitationList from "../components/CitationList";
import { compareCourses } from "../lib/api";
import type { CompareResponse, ComparisonCourseItem } from "../lib/types";
import styles from "./ComparePage.module.css";

const DIMENSIONS = [
  { value: "", label: "any" },
  { value: "ai_infra", label: "AI infra" },
  { value: "systems", label: "systems" },
  { value: "software", label: "software" },
  { value: "hardware", label: "hardware" },
];

type Status =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; data: CompareResponse }
  | { kind: "error"; message: string };

export default function ComparePage() {
  const [courseA, setCourseA] = useState("ECE 408");
  const [courseB, setCourseB] = useState("CS 433");
  const [dimension, setDimension] = useState("ai_infra");
  const [status, setStatus] = useState<Status>({ kind: "idle" });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const ids = [courseA.trim(), courseB.trim()].filter(Boolean);
    if (ids.length < 2) {
      setStatus({ kind: "error", message: "Please enter two course IDs." });
      return;
    }
    setStatus({ kind: "loading" });
    try {
      const data = await compareCourses(ids, dimension || null);
      setStatus({ kind: "ok", data });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setStatus({ kind: "error", message: msg });
    }
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.eyebrow}>Compare</div>
        <h1 className={styles.title}>Compare two courses side by side</h1>
        <p className={styles.lead}>
          Structured comparison over career-direction match, GPA evidence, and
          prerequisite readiness — powered by the <code>compare_courses</code>
          <span> </span>tool.
        </p>
      </header>

      <form className={styles.form} onSubmit={submit}>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>Course A</span>
          <input
            className={styles.input}
            value={courseA}
            onChange={(e) => setCourseA(e.target.value)}
            placeholder="ECE 408"
            disabled={status.kind === "loading"}
          />
        </label>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>Course B</span>
          <input
            className={styles.input}
            value={courseB}
            onChange={(e) => setCourseB(e.target.value)}
            placeholder="CS 433"
            disabled={status.kind === "loading"}
          />
        </label>
        <label className={styles.field}>
          <span className={styles.fieldLabel}>Dimension</span>
          <select
            className={styles.select}
            value={dimension}
            onChange={(e) => setDimension(e.target.value)}
            disabled={status.kind === "loading"}
          >
            {DIMENSIONS.map((d) => (
              <option key={d.value} value={d.value}>
                {d.label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="submit"
          className={styles.submit}
          disabled={status.kind === "loading"}
        >
          {status.kind === "loading" ? "Comparing…" : "Compare"}
        </button>
      </form>

      {status.kind === "error" && (
        <div className={styles.error}>{status.message}</div>
      )}

      {status.kind === "ok" && <Result data={status.data} />}
    </div>
  );
}

function Result({ data }: { data: CompareResponse }) {
  const items = data.comparison.courses;
  const notes = data.comparison.notes;

  return (
    <section className={styles.result}>
      <p className={styles.summary}>{data.summary}</p>

      {items.length === 0 ? (
        <div className={styles.empty}>
          <div className={styles.emptyTitle}>No structured data found</div>
          {notes.length > 0 && (
            <ul className={styles.noteList}>
              {notes.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <div className={styles.grid}>
          {items.map((item) => (
            <CourseCard key={item.course_id} item={item} />
          ))}
        </div>
      )}

      {notes.length > 0 && items.length > 0 && (
        <ul className={styles.noteList}>
          {notes.map((n, i) => (
            <li key={i}>{n}</li>
          ))}
        </ul>
      )}

      {data.citations.length > 0 && (
        <div className={styles.citations}>
          <h2 className={styles.sectionTitle}>Citations</h2>
          <CitationList citations={data.citations} />
        </div>
      )}
    </section>
  );
}

function CourseCard({ item }: { item: ComparisonCourseItem }) {
  return (
    <div className={styles.card}>
      <div className={styles.cardHeader}>
        <span className={styles.courseId}>{item.course_id}</span>
        {item.title && <span className={styles.courseTitle}>{item.title}</span>}
      </div>

      <Row label="Direction match" value={<MatchBadge status={item.direction_match} />} />
      <Row
        label="Average GPA"
        value={
          item.average_gpa != null ? (
            <span className={styles.value}>{item.average_gpa.toFixed(2)}</span>
          ) : (
            <span className={styles.valueDim}>no evidence</span>
          )
        }
      />
      <Row
        label="Prereq readiness"
        value={<ReadinessBadge readiness={item.prerequisite_readiness} />}
      />
      {item.missing_prerequisites.length > 0 && (
        <Row
          label="Missing"
          value={
            <span className={styles.value}>
              {item.missing_prerequisites.join(", ")}
            </span>
          }
        />
      )}
      {item.career_tags.length > 0 && (
        <Row
          label="Tags"
          value={
            <span className={styles.tags}>
              {item.career_tags.map((t) => (
                <span key={t} className={styles.tag}>
                  {t}
                </span>
              ))}
            </span>
          }
        />
      )}
      {item.notes.length > 0 && (
        <ul className={styles.noteListInline}>
          {item.notes.map((n, i) => (
            <li key={i}>{n}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className={styles.row}>
      <span className={styles.rowLabel}>{label}</span>
      <span className={styles.rowValue}>{value}</span>
    </div>
  );
}

function MatchBadge({ status }: { status: ComparisonCourseItem["direction_match"] }) {
  const cls =
    status === "match"
      ? `${styles.badge} ${styles.badgeMatch}`
      : status === "no_match"
        ? `${styles.badge} ${styles.badgeNoMatch}`
        : `${styles.badge} ${styles.badgeNeutral}`;
  const label =
    status === "match"
      ? "match"
      : status === "no_match"
        ? "no match"
        : "not requested";
  return <span className={cls}>{label}</span>;
}

function ReadinessBadge({ readiness }: { readiness: string }) {
  const cls =
    readiness === "likely_ready"
      ? `${styles.badge} ${styles.badgeMatch}`
      : readiness === "missing_prerequisites"
        ? `${styles.badge} ${styles.badgeNoMatch}`
        : `${styles.badge} ${styles.badgeNeutral}`;
  return <span className={cls}>{readiness.replace(/_/g, " ")}</span>;
}
