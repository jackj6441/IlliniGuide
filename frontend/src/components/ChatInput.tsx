import { useEffect, useRef, useState } from "react";
import styles from "./ChatInput.module.css";

type Props = {
  onSend: (message: string) => void;
  onStop: () => void;
  streaming: boolean;
  autoFocus?: boolean;
};

export default function ChatInput({
  onSend,
  onStop,
  streaming,
  autoFocus,
}: Props) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (autoFocus) textareaRef.current?.focus();
  }, [autoFocus]);

  // Grow the textarea with content up to ~6 lines, then scroll internally.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [value]);

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || streaming) return;
    onSend(trimmed);
    setValue("");
  };

  return (
    <form
      className={styles.form}
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <textarea
        ref={textareaRef}
        className={styles.textarea}
        placeholder="Ask about a course, compare two, or get a recommendation…"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        rows={1}
        disabled={streaming}
      />
      {streaming ? (
        <button
          type="button"
          className={`${styles.button} ${styles.buttonStop}`}
          onClick={onStop}
          aria-label="Stop streaming"
        >
          Stop
        </button>
      ) : (
        <button
          type="submit"
          className={styles.button}
          disabled={!value.trim()}
          aria-label="Send message"
        >
          Send
        </button>
      )}
    </form>
  );
}
