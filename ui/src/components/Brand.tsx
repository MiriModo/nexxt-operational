import { Link } from "react-router-dom";

/** The Keeper mark (logo option A): a Raiffeisen-yellow tile with an ink key, like an app icon. */
export function Mark({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect width="24" height="24" rx="6" fill="#fee600" />
      <circle cx="9.2" cy="9.2" r="3.6" stroke="#0c0d0f" strokeWidth="2" />
      <circle cx="9.2" cy="9.2" r="1.1" fill="#0c0d0f" />
      <path d="M11.8 11.8 18 18M15.4 15.4l1.6-1.6M17.1 17.1l1.4-1.4" stroke="#0c0d0f" strokeWidth="2" strokeLinecap="round" />
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
