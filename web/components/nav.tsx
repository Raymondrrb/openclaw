import Link from "next/link";

export function Nav() {
  return (
    <nav className="border-b border-[var(--border)] bg-[var(--card)]">
      <div className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-3">
        <Link href="/" className="text-lg font-bold text-[var(--accent)]">
          Rayviews Lab Ops
        </Link>
        <Link href="/" className="text-sm text-[var(--muted)] hover:text-[var(--fg)]">
          Overview
        </Link>
        <Link href="/runs" className="text-sm text-[var(--muted)] hover:text-[var(--fg)]">
          Runs
        </Link>
      </div>
    </nav>
  );
}
