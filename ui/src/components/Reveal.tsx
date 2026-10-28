import { useEffect, useRef, type CSSProperties, type ReactNode } from "react";

/** Reveal on scroll: the element starts slightly lower and transparent and settles when it enters the viewport.
 *  One observer per element, fires once. `delay` (ms) staggers siblings. Respects prefers-reduced-motion (CSS). */
export function Reveal({ children, delay = 0, className = "", as: Tag = "div", style }: { children: ReactNode; delay?: number; className?: string; as?: "div" | "section" | "li"; style?: CSSProperties }) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (!("IntersectionObserver" in window)) {
      el.classList.add("in");
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            el.classList.add("in");
            io.disconnect();
          }
        });
      },
      { rootMargin: "0px 0px -10% 0px", threshold: 0.08 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);
  const T = Tag as "div";
  return (
    <T ref={ref as never} className={`reveal ${className}`} style={{ ...style, transitionDelay: delay ? `${delay}ms` : undefined }}>
      {children}
    </T>
  );
}
