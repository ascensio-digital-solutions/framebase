import { useEffect, useRef } from "react";
import { useLibrary } from "../library/LibraryContext";

/** Loads the next page when scrolled into view; the button is the keyboard and fallback path. */
export function LoadMore() {
  const { hasMore, loadingAssets, loadMore } = useLibrary();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || !hasMore) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) loadMore();
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [hasMore, loadMore]);

  if (!hasMore) return null;
  return (
    <div ref={ref} className="load-more">
      <button type="button" className="link-button" onClick={loadMore} disabled={loadingAssets}>
        {loadingAssets ? "Loading…" : "Load more"}
      </button>
    </div>
  );
}
