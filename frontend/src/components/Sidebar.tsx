import { NavLink } from "react-router-dom";
import styles from "./Sidebar.module.css";

type NavItem = { to: string; label: string; end?: boolean };

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Chat", end: true },
  { to: "/compare", label: "Compare" },
  { to: "/recommend", label: "Recommend" },
];

export default function Sidebar() {
  return (
    <aside className={styles.sidebar}>
      <div className={styles.brand}>
        <div className={styles.brandMark} />
        <div>
          <div className={styles.brandTitle}>IlliniGuide</div>
          <div className={styles.brandSubtitle}>Serve</div>
        </div>
      </div>

      <nav className={styles.nav}>
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              isActive ? `${styles.link} ${styles.linkActive}` : styles.link
            }
          >
            <span className={styles.linkBar} aria-hidden />
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className={styles.footer}>
        <div className={styles.footerLabel}>Self-hosted</div>
        <div className={styles.footerText}>
          LLM/RAG for UIUC ECE/CS advising
        </div>
      </div>
    </aside>
  );
}
