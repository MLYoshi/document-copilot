// Thread list/create over the api singleton, plus the sidebar list hook.
// Thread creation happens lazily on the first question (the backend has no
// title-update endpoint), so createThread is only called from the new-chat
// flow in ChatPage.
import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { Thread } from "@/chat/types";

export function listThreads(): Promise<Thread[]> {
  return api.get<Thread[]>("/threads");
}

export function createThread(title: string): Promise<Thread> {
  return api.post<Thread>("/threads", { title });
}

export function useThreads() {
  const [threads, setThreads] = useState<Thread[]>([]);

  const refresh = useCallback(() => {
    listThreads()
      .then(setThreads)
      .catch(() => setThreads([]));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { threads, refresh };
}
