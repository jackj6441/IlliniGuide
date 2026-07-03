import type { Citation } from "../lib/types";
import styles from "./CitationList.module.css";

type Props = { citations: Citation[] };

export default function CitationList({ citations }: Props) {
  if (citations.length === 0) {
    return <div className={styles.empty}>none</div>;
  }
  return (
    <div className={styles.list}>
      {citations.map((c, i) => (
        <CitationCard key={`${c.source_name}-${i}`} citation={c} />
      ))}
    </div>
  );
}

function CitationCard({ citation }: { citation: Citation }) {
  return (
    <div className={styles.card}>
      <div className={styles.header}>
        {citation.course_id && (
          <span className={styles.courseId}>{citation.course_id}</span>
        )}
        <span className={styles.sourceName}>{citation.source_name}</span>
      </div>
      <div className={styles.snippet}>{citation.snippet}</div>
      {citation.source_url && (
        <a
          className={styles.link}
          href={citation.source_url}
          target="_blank"
          rel="noreferrer noopener"
        >
          source →
        </a>
      )}
    </div>
  );
}
