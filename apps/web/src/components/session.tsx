/** Shared student session (Step 20A).
 *
 * This is NOT authentication and NOT a user account: the backend keeps one
 * throwaway learning session per browser (process-local, in-memory). This
 * provider only remembers the current `session_id` in localStorage so the
 * five areas share one session instead of each creating its own.
 *
 * If the stored session is gone (backend restart, unknown id), a fresh
 * session is created and callers are told so via `freshNotice` — the UI
 * must present that as a fresh start, never as restored progress.
 */
"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import {
  ApiError,
  api,
  friendlyError,
  type JourneyResponse,
  type ProblemView,
  type SessionResponse,
} from "../app/lib/api";

const STORAGE_KEY = "cognify.session_id";
const STORAGE_LANG_KEY = "cognify.language_track";

export type SessionStatus = "loading" | "ready" | "failed";
export type LanguageTrack = "python" | "java";

export function normalizeTrack(raw: unknown): LanguageTrack {
  return raw === "java" ? "java" : "python";
}

export interface SessionValue {
  status: SessionStatus;
  sessionId: string | null;
  session: SessionResponse | null;
  journey: JourneyResponse | null;
  problem: ProblemView | null;
  error: string | null;
  /** Current language track (session truth, falling back to stored choice). */
  language: LanguageTrack;
  /** Set when the stored session was invalid and a fresh one was started. */
  freshNotice: string | null;
  refresh: () => Promise<void>;
  restart: () => Promise<void>;
  chooseLanguage: (track: LanguageTrack) => Promise<void>;
  dismissNotice: () => void;
}

const SessionContext = createContext<SessionValue | null>(null);

function readStoredId(): string | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw && raw.trim() ? raw : null;
  } catch {
    return null;
  }
}

function writeStoredId(id: string | null): void {
  try {
    if (id) window.localStorage.setItem(STORAGE_KEY, id);
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* storage unavailable: session simply won't survive reloads */
  }
}

function readStoredLanguage(): LanguageTrack {
  try {
    const raw = window.localStorage.getItem(STORAGE_LANG_KEY);
    return normalizeTrack(raw);
  } catch {
    return "python";
  }
}

function writeStoredLanguage(track: LanguageTrack): void {
  try {
    window.localStorage.setItem(STORAGE_LANG_KEY, track);
  } catch {
    /* storage unavailable */
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SessionStatus>("loading");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [session, setSession] = useState<SessionResponse | null>(null);
  const [journey, setJourney] = useState<JourneyResponse | null>(null);
  const [problem, setProblem] = useState<ProblemView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [freshNotice, setFreshNotice] = useState<string | null>(null);
  const bootId = useRef(0);

  const startFresh = useCallback(
    async (
      mine: number,
      notice: string | null,
      track?: LanguageTrack,
    ) => {
      // One request only: the session payload already carries the journey
      // state. Pages needing recommendations call refresh() themselves, so
      // Practice mounts stay at exactly one bootstrap request.
      const wanted: LanguageTrack =
        track ?? readStoredLanguage();
      try {
        const created = await api.createSession(wanted);
        if (bootId.current !== mine) return;
        writeStoredId(created.session_id);
        writeStoredLanguage(normalizeTrack(created.language_track));
        setSessionId(created.session_id);
        setSession(created);
        setProblem(created.problem);
        setJourney(null);
        setFreshNotice(notice);
        setError(null);
        setStatus("ready");
      } catch (err: unknown) {
        if (bootId.current !== mine) return;
        setError(friendlyError(err));
        setStatus("failed");
      }
    },
    [],
  );

  const boot = useCallback(async () => {
    const mine = ++bootId.current;
    setStatus("loading");
    setError(null);
    const stored = readStoredId();
    if (!stored) {
      await startFresh(mine, null);
      return;
    }
    try {
      const existing = await api.getJourney(stored);
      if (bootId.current !== mine) return;
      setSessionId(stored);
      setJourney(existing);
      try {
        const current = await api.getProblem(
          stored,
          existing.canonical_problem_id,
        );
        if (bootId.current === mine) setProblem(current);
      } catch {
        /* problem enriches; journey alone still answers "what's next" */
      }
      setError(null);
      setStatus("ready");
    } catch (err: unknown) {
      if (bootId.current !== mine) return;
      if (err instanceof ApiError && err.status === 404) {
        await startFresh(
          mine,
          "Your previous session had expired, so we started a fresh one.",
        );
      } else {
        setError(friendlyError(err));
        setStatus("failed");
      }
    }
  }, [startFresh]);

  useEffect(() => {
    // One-shot session bootstrap on mount. State updates all happen
    // asynchronously inside boot() after awaits, never synchronously here.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void boot();
    return () => {
      bootId.current += 1;
    };
  }, [boot]);

  const refresh = useCallback(async () => {
    if (!sessionId) {
      await boot();
      return;
    }
    try {
      const fresh = await api.getJourney(sessionId);
      setJourney(fresh);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 404) {
        await boot();
      }
    }
  }, [sessionId, boot]);

  const restart = useCallback(async () => {
    writeStoredId(null);
    setFreshNotice(null);
    await boot();
  }, [boot]);

  const chooseLanguage = useCallback(
    async (track: LanguageTrack) => {
      const mine = ++bootId.current;
      setStatus("loading");
      setError(null);
      writeStoredLanguage(track);
      writeStoredId(null);
      setSessionId(null);
      setSession(null);
      setJourney(null);
      setProblem(null);
      setFreshNotice(null);
      await startFresh(mine, null, track);
    },
    [startFresh],
  );

  const dismissNotice = useCallback(() => setFreshNotice(null), []);

  const language: LanguageTrack =
    normalizeTrack(
      session?.language_track ?? journey?.language_track ?? problem?.language,
    );

  const value = useMemo<SessionValue>(
    () => ({
      status,
      sessionId,
      session,
      journey,
      problem,
      error,
      language,
      freshNotice,
      refresh,
      restart,
      chooseLanguage,
      dismissNotice,
    }),
    [
      status,
      sessionId,
      session,
      journey,
      problem,
      error,
      language,
      freshNotice,
      refresh,
      restart,
      chooseLanguage,
      dismissNotice,
    ],
  );

  return (
    <SessionContext.Provider value={value}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside SessionProvider");
  return ctx;
}
