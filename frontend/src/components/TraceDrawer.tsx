import { useEffect } from "react";
import type { ChatMessageMeta } from "../lib/types";
import CitationList from "./CitationList";
import ToolCallCard from "./ToolCallCard";
import styles from "./TraceDrawer.module.css";

type Props = {
  meta: ChatMessageMeta | null;
  open: boolean;
  onClose: () => void;
};

export default function TraceDrawer({ meta, open, onClose }: Props) {
  // Close on Escape whenever the drawer is open.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const backdropCls = open
    ? `${styles.backdrop} ${styles.backdropOpen}`
    : styles.backdrop;
  const panelCls = open ? `${styles.panel} ${styles.panelOpen}` : styles.panel;

  return (
    <>
      <div
        className={backdropCls}
        onClick={onClose}
        aria-hidden={!open}
      />
      <aside
        className={panelCls}
        role="dialog"
        aria-modal={open}
        aria-label="Debug trace"
      >
        <header className={styles.header}>
          <div>
            <div className={styles.eyebrow}>Debug trace</div>
            {meta?.debug_trace && (
              <div className={styles.intent}>{meta.debug_trace.intent}</div>
            )}
          </div>
          <button
            type="button"
            className={styles.close}
            onClick={onClose}
            aria-label="Close trace"
          >
            ✕
          </button>
        </header>

        {meta ? <DrawerBody meta={meta} /> : null}
      </aside>
    </>
  );
}

function DrawerBody({ meta }: { meta: ChatMessageMeta }) {
  const trace = meta.debug_trace;
  const toolCalls = trace?.tool_calls ?? [];
  const chunks = trace?.retrieved_chunks ?? [];
  const scores = trace?.recommendation_scores ?? [];

  return (
    <div className={styles.body}>
      <SummaryRow meta={meta} />

      <Section title={`Tool calls (${toolCalls.length})`}>
        {toolCalls.length === 0 ? (
          <div className={styles.empty}>none</div>
        ) : (
          <div className={styles.stack}>
            {toolCalls.map((call, i) => (
              <ToolCallCard key={`${call.tool_name}-${i}`} call={call} />
            ))}
          </div>
        )}
      </Section>

      <Section title={`Citations (${meta.citations.length})`}>
        <CitationList citations={meta.citations} />
      </Section>

      <Section title={`Retrieved chunks (${chunks.length})`}>
        {chunks.length === 0 ? (
          <div className={styles.empty}>none</div>
        ) : (
          <pre className={styles.pre}>{JSON.stringify(chunks, null, 2)}</pre>
        )}
      </Section>

      {scores.length > 0 && (
        <Section title={`Recommendation scores (${scores.length})`}>
          <pre className={styles.pre}>{JSON.stringify(scores, null, 2)}</pre>
        </Section>
      )}
    </div>
  );
}

function SummaryRow({ meta }: { meta: ChatMessageMeta }) {
  return (
    <div className={styles.summary}>
      <SummaryCell label="latency" value={`${meta.latency_ms} ms`} />
      <SummaryCell label="tools" value={String(meta.used_tools.length)} />
      <SummaryCell label="citations" value={String(meta.citations.length)} />
    </div>
  );
}

function SummaryCell({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.cell}>
      <div className={styles.cellLabel}>{label}</div>
      <div className={styles.cellValue}>{value}</div>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className={styles.section}>
      <h2 className={styles.sectionTitle}>{title}</h2>
      {children}
    </section>
  );
}
