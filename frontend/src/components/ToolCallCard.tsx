import type { ToolCall } from "../lib/types";
import styles from "./ToolCallCard.module.css";

type Props = { call: ToolCall };

const STATUS_LABEL: Record<ToolCall["status"], string> = {
  ok: "ok",
  empty: "empty",
  error: "error",
};

export default function ToolCallCard({ call }: Props) {
  const dotCls = `${styles.dot} ${styles[`dot_${call.status}`]}`;

  return (
    <div className={styles.card}>
      <div className={styles.header}>
        <span className={dotCls} aria-label={STATUS_LABEL[call.status]} />
        <span className={styles.name}>{call.tool_name}</span>
        <span className={styles.latency}>{call.latency_ms} ms</span>
      </div>

      <Section label="arguments" json={call.arguments} />

      {call.result_summary && Object.keys(call.result_summary).length > 0 && (
        <Section label="result" json={call.result_summary} />
      )}

      {call.error && (
        <div className={styles.error}>
          <span className={styles.errorLabel}>error</span>
          <div className={styles.errorText}>{call.error}</div>
        </div>
      )}
    </div>
  );
}

function Section({ label, json }: { label: string; json: unknown }) {
  return (
    <div className={styles.section}>
      <div className={styles.sectionLabel}>{label}</div>
      <pre className={styles.pre}>{formatJSON(json)}</pre>
    </div>
  );
}

function formatJSON(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}
