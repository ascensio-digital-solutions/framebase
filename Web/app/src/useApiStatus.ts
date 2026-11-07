import { useEffect, useState } from "react";

export type ApiStatus = "checking" | "ok" | "unreachable";

export function useApiStatus(): ApiStatus {
  const [status, setStatus] = useState<ApiStatus>("checking");

  useEffect(() => {
    const controller = new AbortController();
    fetch("/healthz", { signal: controller.signal })
      .then((res) => setStatus(res.ok ? "ok" : "unreachable"))
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError"))
          setStatus("unreachable");
      });
    return () => controller.abort();
  }, []);

  return status;
}
