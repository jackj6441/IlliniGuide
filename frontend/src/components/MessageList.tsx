import { useEffect, useRef } from "react";
import type { ChatMessage, ChatMessageMeta } from "../lib/types";
import MessageBubble from "./MessageBubble";
import styles from "./MessageList.module.css";

type Props = {
  messages: ChatMessage[];
  onShowTrace?: (meta: ChatMessageMeta) => void;
};

export default function MessageList({ messages, onShowTrace }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Snap to bottom on new message or streaming update; smooth would fight
  // the fast character-by-character updates.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages]);

  return (
    <div className={styles.list}>
      {messages.map((m) => (
        <MessageBubble key={m.id} message={m} onShowTrace={onShowTrace} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
