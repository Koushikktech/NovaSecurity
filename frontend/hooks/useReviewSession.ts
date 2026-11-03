"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";

type Snapshot = { id: string; status: string };
type Client = (path: string, init?: RequestInit) => Promise<unknown>;
type Connection = "connected" | "retrying" | "offline";
type State<R, F> = {
  run: R | null;
  findings: F[];
  busy: boolean;
  error: string;
  connection: Connection;
};
type Action<R, F> =
  | { type: "begin" }
  | { type: "snapshot"; run: R }
  | { type: "findings"; findings: F[]; done?: boolean }
  | { type: "connection"; connection: Connection }
  | { type: "error"; error: string; stop?: boolean };
const terminal = new Set([
  "completed",
  "partial",
  "failed",
  "cancelled",
  "interrupted",
]);
const statuses = new Set(["queued", "running", ...terminal]);

function reducer<R, F>(state: State<R, F>, action: Action<R, F>): State<R, F> {
  switch (action.type) {
    case "begin":
      return {
        run: null,
        findings: [],
        busy: true,
        error: "",
        connection: "connected",
      };
    case "snapshot":
      return { ...state, run: action.run, connection: "connected" };
    case "findings":
      return {
        ...state,
        findings: action.findings,
        busy: action.done ? false : state.busy,
        connection: "connected",
      };
    case "connection":
      return { ...state, connection: action.connection };
    case "error":
      return {
        ...state,
        error: action.error,
        busy: action.stop ? false : state.busy,
        connection: action.stop ? "offline" : state.connection,
      };
  }
}
function pause(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal.aborted) {
      reject(signal.reason);
      return;
    }
    const abort = () => {
      clearTimeout(timer);
      reject(signal.reason);
    };
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", abort);
      resolve();
    }, ms);
    signal.addEventListener("abort", abort, { once: true });
  });
}

/** One watched review at a time. Reconnect reads existing state; it never submits another model job. */
export function useReviewSession<R extends Snapshot, F>(request: Client) {
  const [state, dispatch] = useReducer(reducer<R, F>, {
    run: null,
    findings: [],
    busy: false,
    error: "",
    connection: "connected",
  });
  const epoch = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const activeRunId = useRef<string | null>(null);
  const autoLoaded = useRef(false);
  useEffect(
    () => () => {
      epoch.current++;
      controller.current?.abort();
      autoLoaded.current = false;
    },
    [],
  );
  const begin = useCallback(() => {
    controller.current?.abort();
    const session = {
      epoch: ++epoch.current,
      controller: new AbortController(),
    };
    controller.current = session.controller;
    activeRunId.current = null;
    dispatch({ type: "begin" });
    return session;
  }, []);
  const follow = useCallback(
    async (id: string, session: ReturnType<typeof begin>) => {
      const signal = session.controller.signal;
      const current = () => epoch.current === session.epoch && !signal.aborted;
      if (!current()) return;
      activeRunId.current = id;
      window.history.replaceState(null, "", "?run=" + encodeURIComponent(id));
      let failures = 0;
      while (current()) {
        try {
          const snapshot = (await request(
            "/reviews/" + encodeURIComponent(id),
            { signal: AbortSignal.any([signal, AbortSignal.timeout(15000)]) },
          )) as R;
          if (!current()) return;
          if (snapshot.id !== id || !statuses.has(snapshot.status))
            throw Object.assign(new Error("Invalid review snapshot"), {
              status: 422,
            });
          dispatch({ type: "snapshot", run: snapshot });
          if (terminal.has(snapshot.status)) {
            const findings = await request(
              "/reviews/" + encodeURIComponent(id) + "/findings",
              { signal: AbortSignal.any([signal, AbortSignal.timeout(15000)]) },
            );
            if (!current()) return;
            if (!Array.isArray(findings))
              throw Object.assign(new Error("Invalid findings response"), {
                status: 422,
              });
            dispatch({
              type: "findings",
              findings: findings as F[],
              done: true,
            });
            return;
          }
          failures = 0;
          await pause(1000, signal);
        } catch (error) {
          if (!current()) return;
          const status = (error as { status?: number })?.status;
          if (
            (status && status >= 400 && status < 500 && status !== 429) ||
            ++failures > 3
          )
            throw error;
          dispatch({ type: "connection", connection: "retrying" });
          await pause(Math.min(8000, 1000 * 2 ** (failures - 1)), signal);
        }
      }
    },
    [request],
  );
  const startReview = useCallback(
    async (create: (signal: AbortSignal) => Promise<{ run_id: string }>) => {
      const session = begin();
      try {
        const created = await create(session.controller.signal);
        if (
          epoch.current !== session.epoch ||
          session.controller.signal.aborted
        )
          return;
        if (!created.run_id) throw new Error("Review did not return an ID");
        await follow(created.run_id, session);
      } catch (error) {
        if (
          epoch.current === session.epoch &&
          !session.controller.signal.aborted
        )
          dispatch({ type: "error", error: String(error), stop: true });
      }
    },
    [begin, follow],
  );
  const openReview = useCallback(
    async (id: string) => {
      const session = begin();
      try {
        await follow(id, session);
      } catch (error) {
        if (
          epoch.current === session.epoch &&
          !session.controller.signal.aborted
        )
          dispatch({ type: "error", error: String(error), stop: true });
      }
    },
    [begin, follow],
  );
  useEffect(() => {
    if (autoLoaded.current) return;
    autoLoaded.current = true;
    const id = new URLSearchParams(window.location.search).get("run");
    if (id && /^[a-zA-Z0-9-]{1,80}$/.test(id)) void openReview(id);
  }, [openReview]);
  const refreshFindings = useCallback(
    async (id: string) => {
      const started = epoch.current;
      const findings = await request(
        "/reviews/" + encodeURIComponent(id) + "/findings",
        { signal: controller.current?.signal },
      );
      if (
        started === epoch.current &&
        activeRunId.current === id &&
        Array.isArray(findings)
      )
        dispatch({ type: "findings", findings: findings as F[] });
    },
    [request],
  );
  const setError = useCallback(
    (error: string) => dispatch({ type: "error", error }),
    [],
  );
  return {
    ...state,
    startReview,
    openReview,
    refreshFindings,
    setError,
    activeRunId,
  };
}
