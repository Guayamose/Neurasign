"use client";

export function RosterPagination({ first, last, total, page, pages, size, label, itemLabel = "people", onPage, onSize }: {
  first: number; last: number; total: number; page: number; pages: number; size: number; label: string; itemLabel?: string;
  onPage: (page: number) => void; onSize: (size: number) => void;
}) {
  return <nav className="co-pagination" aria-label={`${label} pagination`}>
    <span aria-live="polite">{first}–{last} of {total} {itemLabel}</span>
    <label>Rows per page<select aria-label={`${label} rows per page`} value={size} onChange={event => onSize(Number(event.target.value))}><option value={25}>25</option><option value={50}>50</option></select></label>
    <div><button type="button" className="co-secondary" onClick={() => onPage(page - 1)} disabled={page === 0}>Previous page</button><span>Page {page + 1} of {pages}</span><button type="button" className="co-secondary" onClick={() => onPage(page + 1)} disabled={page + 1 >= pages}>Next page</button></div>
  </nav>;
}
