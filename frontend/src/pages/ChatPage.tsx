import { useCallback, useReducer, useRef, useState } from "react";
import ChatInput from "../components/ChatInput";
import MessageList from "../components/MessageList";
import SuggestedPrompts from "../components/SuggestedPrompts";
import TraceDrawer from "../components/TraceDrawer";
import { streamChat } from "../lib/api";
import type { ChatMessage, ChatMessageMeta } from "../lib/types";
import styles from "./ChatPage.module.css";

type State = {
  messages: ChatMessage[];
  streaming: boolean;
};

type Action =
  | { type: "user_send"; id: string; content: string }
  | { type: "assistant_open"; id: string }
  | { type: "assistant_chunk"; delta: string }
  | { type: "assistant_meta"; meta: ChatMessageMeta }
  | { type: "assistant_close" }
  | { type: "assistant_error"; error: string };

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "user_send":
      return {
        ...state,
        streaming: true,
        messages: [
          ...state.messages,
          { id: action.id, role: "user", content: action.content },
        ],
      };
    case "assistant_open":
      return {
        ...state,
        messages: [
          ...state.messages,
          { id: action.id, role: "assistant", content: "", streaming: true },
        ],
      };
    case "assistant_chunk":
      return {
        ...state,
        messages: patchLast(state.messages, (m) => ({
          ...m,
          content: m.content + action.delta,
        })),
      };
    case "assistant_meta":
      return {
        ...state,
        messages: patchLast(state.messages, (m) => ({ ...m, meta: action.meta })),
      };
    case "assistant_close":
      return {
        ...state,
        streaming: false,
        messages: patchLast(state.messages, (m) => ({ ...m, streaming: false })),
      };
    case "assistant_error":
      return {
        ...state,
        streaming: false,
        messages: patchLast(state.messages, (m) => ({
          ...m,
          streaming: false,
          error: action.error,
        })),
      };
  }
}

function patchLast(
  messages: ChatMessage[],
  fn: (m: ChatMessage) => ChatMessage,
): ChatMessage[] {
  if (messages.length === 0) return messages;
  const last = messages[messages.length - 1];
  if (last.role !== "assistant") return messages;
  return [...messages.slice(0, -1), fn(last)];
}

const INITIAL: State = { messages: [], streaming: false };

let messageIdSeq = 0;
const nextId = () => `m${++messageIdSeq}`;

export default function ChatPage() {
  const [state, dispatch] = useReducer(reducer, INITIAL);
  const abortRef = useRef<AbortController | null>(null);
  const [traceMeta, setTraceMeta] = useState<ChatMessageMeta | null>(null);

  const send = useCallback(async (message: string) => {
    dispatch({ type: "user_send", id: nextId(), content: message });
    dispatch({ type: "assistant_open", id: nextId() });

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      for await (const event of streamChat(message, {
        signal: controller.signal,
      })) {
        if (event.type === "content") {
          dispatch({ type: "assistant_chunk", delta: event.delta });
        } else if (event.type === "metadata") {
          const { type: _t, ...meta } = event;
          dispatch({ type: "assistant_meta", meta });
        }
      }
      dispatch({ type: "assistant_close" });
    } catch (err) {
      if ((err as { name?: string }).name === "AbortError") {
        dispatch({ type: "assistant_close" });
      } else {
        const msg = err instanceof Error ? err.message : String(err);
        dispatch({ type: "assistant_error", error: msg });
      }
    } finally {
      abortRef.current = null;
    }
  }, []);

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const isEmpty = state.messages.length === 0;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.eyebrow}>Chat</div>
        <h1 className={styles.title}>Ask an advising question</h1>
      </header>

      <div className={styles.thread}>
        {isEmpty ? (
          <div className={styles.empty}>
            <p className={styles.emptyLead}>
              Ask about a course, compare two options, or get a recommendation.
              Every answer is grounded in structured tools and citations.
            </p>
            <SuggestedPrompts onPick={send} />
          </div>
        ) : (
          <MessageList messages={state.messages} onShowTrace={setTraceMeta} />
        )}
      </div>

      <div className={styles.inputWrap}>
        <ChatInput
          onSend={send}
          onStop={stop}
          streaming={state.streaming}
          autoFocus
        />
      </div>

      <TraceDrawer
        meta={traceMeta}
        open={traceMeta !== null}
        onClose={() => setTraceMeta(null)}
      />
    </div>
  );
}
