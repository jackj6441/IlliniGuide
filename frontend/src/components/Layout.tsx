import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";
import styles from "./Layout.module.css";

export default function Layout() {
  return (
    <div className={styles.root}>
      <Sidebar />
      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  );
}
