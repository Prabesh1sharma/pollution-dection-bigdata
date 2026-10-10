"use client";
import { useCallback, useEffect, useState } from "react";

/** Fetch JSON now and every `ms` milliseconds. Keeps the previous data while refreshing. */
export function usePoll<T>(url: string, ms = 30000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [updated, setUpdated] = useState<Date | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const r = await fetch(url, { cache: "no-store" });
      if (!r.ok) throw new Error(`API returned ${r.status}`);
      setData((await r.json()) as T);
      setError(null);
      setUpdated(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : "request failed");
    } finally {
      setLoading(false);
    }
  }, [url]);

  useEffect(() => {
    setLoading(true);
    load();
    const id = setInterval(load, ms);
    return () => clearInterval(id);
  }, [load, ms]);

  return { data, error, updated, loading, reload: load };
}
