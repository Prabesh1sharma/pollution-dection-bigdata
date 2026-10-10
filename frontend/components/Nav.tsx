"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Live" },
  { href: "/history", label: "History" },
  { href: "/analysis", label: "Prediction analysis" },
];

export default function Nav() {
  const path = usePathname();
  return (
    <header className="nav">
      <div className="nav-inner">
        <div className="brand">
          <span className="brand-dot" />
          Nepal Air Quality
        </div>
        <nav>
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href} className={path === l.href ? "active" : ""}>
              {l.label}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
