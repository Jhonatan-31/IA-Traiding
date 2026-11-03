import { useCallback, useEffect, useState } from "react";

export function useAsyncLoad<T>(loader: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    let attempt = 0;
    let lastErr: unknown = null;
    while (attempt < 3) {
      try {
        const value = await loader();
        setData(value);
        setLoading(false);
        return value;
      } catch (e) {
        lastErr = e;
        attempt += 1;
        await new Promise((r) => setTimeout(r, 400 * 2 ** (attempt - 1)));
      }
    }
    setError(lastErr instanceof Error ? lastErr.message : "Error de carga");
    setLoading(false);
    return null;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { data, error, loading, reload, setData };
}
