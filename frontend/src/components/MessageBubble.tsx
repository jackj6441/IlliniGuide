import type { ChatMessage, ChatMessageMeta } from "../lib/types";
import styles from "./MessageBubble.module.css";

type Props = {
  message: ChatMessage;
  onShowTrace?: (meta: ChatMessageMeta) => void;
};

export default function MessageBubble({ message, onShowTrace }: Props) {
  const isUser = message.role === "user";
  const rowCls = isUser ? `${styles.row} ${styles.rowUser}` : styles.row;
  const bubbleCls = isUser
    ? `${styles.bubble} ${styles.bubbleUser}`
    : `${styles.bubble} ${styles.bubbleAssistant}`;

  return (
    <div className={rowCls}>
      <div className={bubbleCls}>
        <div className={styles.content}>
          {message.content}
          {message.streaming && (
            <span className={styles.caret} aria-hidden>
              ▍
            </span>
          )}
        </div>
        {message.error && (
          <div className={styles.error}>{message.error}</div>
        )}
        {!message.streaming && message.meta && !isUser && (
          <MetaFooter meta={message.meta} onShowTrace={onShowTrace} />
        )}
      </div>
    </div>
  );
}

function MetaFooter({
  meta,
  onShowTrace,
}: {
  meta: NonNullable<ChatMessage["meta"]>;
  onShowTrace?: (meta: ChatMessageMeta) => void;
}) {
  const intent = meta.debug_trace?.intent;
  return (
    <div className={styles.meta}>
      {intent && <span className={styles.pill}>{intent}</span>}
      <span className={styles.metaText}>
        {meta.used_tools.length} tools · {meta.latency_ms} ms
      </span>
      {meta.citations.length > 0 && (
        <span className={styles.metaText}>
          · {meta.citations.length} citation
          {meta.citations.length === 1 ? "" : "s"}
        </span>
      )}
      {onShowTrace && (
        <button
          type="button"
          className={styles.traceButton}
          onClick={() => onShowTrace(meta)}
        >
          View trace →
        </button>
      )}
    </div>
  );
}
