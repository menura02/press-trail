import { useEffect, useState } from "react";
import { api } from "../services/api";

export function useApi<T>(path: string, poll: boolean | ((data: T) => boolean) = false) {
  const [state, setState] = useState<{ path: string; data?: T; error?: string }>({ path });
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let pending = false;
    let latest: T | undefined;
    async function load() {
      if (pending) return;
      pending = true;
      try {
        const data = await api<T>(path, { signal: controller.signal });
        latest = data;
        if (!controller.signal.aborted) setState({ path, data });
      } catch (error) {
        if (!controller.signal.aborted) setState({ path, error: (error as Error).message });
      } finally {
        pending = false;
      }
    }
    void load();
    const timer = poll ? window.setInterval(() => {
      if (typeof poll !== "function" || latest === undefined || poll(latest)) void load();
    }, 5000) : undefined;
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [path, poll, revision]);
  return { ...(state.path === path ? state : {}), reload: () => setRevision(n => n + 1) };
}

