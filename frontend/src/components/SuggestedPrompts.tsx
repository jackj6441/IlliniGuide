import styles from "./SuggestedPrompts.module.css";

type Prompt = { label: string; intent: string };

const PROMPTS: Prompt[] = [
  { label: "What is ECE 391 about?", intent: "course_qa" },
  { label: "Compare ECE 408 and CS 433", intent: "comparison" },
  { label: "Courses for AI infrastructure?", intent: "recommendation" },
  { label: "Am I ready for ECE 408?", intent: "prereq_check" },
];

type Props = { onPick: (text: string) => void };

export default function SuggestedPrompts({ onPick }: Props) {
  return (
    <div className={styles.wrap}>
      <div className={styles.heading}>Try one of these</div>
      <div className={styles.grid}>
        {PROMPTS.map((p) => (
          <button
            key={p.label}
            type="button"
            className={styles.chip}
            onClick={() => onPick(p.label)}
          >
            <span className={styles.chipIntent}>{p.intent}</span>
            <span className={styles.chipLabel}>{p.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
