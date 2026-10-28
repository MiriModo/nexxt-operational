import { Link } from "react-router-dom";

/** The Keeper mark: a shield with a check, brand blue. Wordmark in Instrument Sans. */
export function Mark({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 2.5 4.5 5.3v6.2c0 4.6 3.1 8.6 7.5 9.9 4.4-1.3 7.5-5.3 7.5-9.9V5.3L12 2.5Z" fill="#2867e4" />
      <path d="m8.6 12.1 2.3 2.3 4.6-4.8" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Brand({ to = "/" }: { to?: string }) {
  return (
    <Link to={to} className="brand" aria-label="Keeper, home">
      <Mark />
      Keeper
    </Link>
  );
}
