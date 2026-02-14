import type { Top5Product } from "@/lib/types";

interface Props {
  product: Top5Product;
}

export function ProductCard({ product }: Props) {
  const benefits = Array.isArray(product.benefits) ? product.benefits : [];

  return (
    <div className="rounded border border-[var(--border)] bg-[var(--card)] p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <span className="mr-2 text-sm font-bold text-[var(--accent)]">#{product.rank}</span>
          <span className="text-sm font-medium">{product.asin}</span>
          {product.role_label && (
            <span className="ml-2 rounded bg-[var(--border)] px-2 py-0.5 text-xs text-[var(--muted)]">
              {product.role_label}
            </span>
          )}
        </div>
        <div className="text-right">
          {product.price !== null && (
            <span className="text-sm font-bold">${product.price}</span>
          )}
        </div>
      </div>

      {benefits.length > 0 && (
        <ul className="mt-2 space-y-1">
          {benefits.slice(0, 3).map((b, i) => (
            <li key={i} className="text-xs text-[var(--green)]">+ {String(b)}</li>
          ))}
        </ul>
      )}

      {product.downside && (
        <p className="mt-1 text-xs text-[var(--red)]">- {product.downside}</p>
      )}

      <div className="mt-2 flex items-center gap-2">
        {product.affiliate_short_url ? (
          <span className="rounded bg-green-900/30 px-2 py-0.5 text-xs text-[var(--green)]">
            Link OK
          </span>
        ) : (
          <span className="rounded bg-red-900/30 px-2 py-0.5 text-xs text-[var(--red)]">
            No Link
          </span>
        )}
        {product.source_evidence && product.source_evidence.length > 0 && (
          <span className="text-xs text-[var(--muted)]">
            {product.source_evidence.length} source(s)
          </span>
        )}
      </div>
    </div>
  );
}
