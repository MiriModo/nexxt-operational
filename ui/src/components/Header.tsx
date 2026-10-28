import { useEffect, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { homeFor, useEu } from "../auth";
import { Brand } from "./Brand";

/** The menu bar as on scoutnext.io: fixed 64 px, transparent over the hero and frosted white with a hairline once
 *  scrolled, a 2 px blue reading-progress bar at the bottom, nav links with an underline that draws in from the left,
 *  "Sign in" as text and a black primary button. Below 1024 px: a round burger that morphs into an X and a
 *  full-screen menu with large links and full-width buttons. */
export function Header({ offline }: { offline: boolean }) {
  const { eu, logout } = useEu();
  const nav = useNavigate();
  const loc = useLocation();
  const [scrolled, setScrolled] = useState(false);
  const [progress, setProgress] = useState(0);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => {
      const el = document.scrollingElement ?? document.documentElement;
      const max = el.scrollHeight - el.clientHeight;
      setScrolled(el.scrollTop > 8);
      setProgress(max > 0 ? Math.min(1, el.scrollTop / max) : 0);
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);
  useEffect(() => setOpen(false), [loc.pathname, loc.hash]);
  useEffect(() => {
    document.documentElement.style.overflow = open ? "hidden" : "";
    return () => {
      document.documentElement.style.overflow = "";
    };
  }, [open]);

  const signOut = async () => {
    await logout();
    nav("/");
  };
  const landing = !eu && loc.pathname === "/";
  const goHash = (e: React.MouseEvent<HTMLAnchorElement>) => {
    const hash = e.currentTarget.getAttribute("href") ?? "";
    if (loc.pathname !== "/") {
      e.preventDefault();
      nav(`/${hash}`);
    }
  };

  const links = eu?.rol === "consilier"
    ? [{ to: "/desk", t: "My desk" }, { to: "/queue", t: "My queue" }]
    : eu?.rol === "admin"
      ? [{ to: "/overview", t: "Overview" }, { to: "/queue", t: "Queue" }, { to: "/reports", t: "Reports" }, { to: "/rules", t: "Rules engine" }]
      : [{ to: "/#welcome", t: "Welcome" }, { to: "/#how", t: "How it works" }];

  const Item = ({ to, t, big = false }: { to: string; t: string; big?: boolean }) =>
    to.startsWith("/#") ? (
      <a href={to.slice(1)} className={`nav-link ${big ? "big" : ""} ${landing && loc.hash === to.slice(1) ? "active" : ""}`} onClick={goHash}>
        {t}
        <span className="ul" aria-hidden="true" />
      </a>
    ) : (
      <NavLink to={to} className={({ isActive }) => `nav-link ${big ? "big" : ""} ${isActive ? "active" : ""}`}>
        {t}
        <span className="ul" aria-hidden="true" />
      </NavLink>
    );

  return (
    <header className={`hdr ${scrolled || open ? "scrolled" : ""} ${open ? "open" : ""}`}>
      <div className="hdr-bg" aria-hidden="true" />
      <div className="hdr-progress" aria-hidden="true" style={{ transform: `scaleX(${progress})`, opacity: scrolled ? 1 : 0 }} />
      <nav className="hdr-in" aria-label="Main">
        <Brand to={homeFor(eu)} />
        <ul className="nav">
          {links.map((l) => (
            <li key={l.to}>
              <Item {...l} />
            </li>
          ))}
        </ul>
        <div className="cta">
          {offline && <span className="who">static data · server offline</span>}
          {eu ? (
            <>
              <span className="who">{eu.nume}</span>
              <button type="button" className="btn ghost" onClick={signOut}>
                Sign out
              </button>
            </>
          ) : (
            <>
              <Link to="/signin" className="btn primary">
                Sign in <span className="arrow">→</span>
              </Link>
            </>
          )}
          <button type="button" className="burger" aria-expanded={open} aria-controls="mobile-menu" aria-label={open ? "Close menu" : "Open menu"} onClick={() => setOpen(!open)}>
            <span aria-hidden="true">
              <i />
              <i />
              <i />
            </span>
          </button>
        </div>
      </nav>
      <div id="mobile-menu" className="mobile-menu" hidden={!open}>
        <ul>
          {links.map((l) => (
            <li key={l.to}>
              <Item {...l} big />
            </li>
          ))}
        </ul>
        <div className="mobile-cta">
          {eu ? (
            <button type="button" className="btn secondary lg" onClick={signOut}>
              Sign out
            </button>
          ) : (
            <>
              <Link to="/signin" className="btn primary lg">
                Sign in <span className="arrow">→</span>
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
