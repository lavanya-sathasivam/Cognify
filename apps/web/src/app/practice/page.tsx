/** Practice: the core coding experience (Step 20A).
 *
 * Moved from the Step 16 single-screen flow. Same verified journey —
 * Problem -> Code -> Feedback -> Retry -> Transfer -> Verification — now in
 * a two-column layout sharing one session with the rest of the app.
 * Renders server-provided JSON only; student wording comes from lib/copy.
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSession } from "../../components/session";
import {
  CodeEditor,
  ProblemPanel,
  ResultPanel,
} from "../../components/practice";
import {
  Alert,
  Loading,
  SecondaryButton,
} from "../../components/ui";
import {
  api,
  friendlyError,
  type ProblemView,
  type SubmissionResponse,
} from "../lib/api";

/** Must stay in sync with the backend cap (student.py MAX_CODE_CHARS). */
const MAX_CODE_CHARS = 100_000;

export default function PracticePage() {
  const {
    status,
    sessionId,
    problem: sessionProblem,
    language,
    freshNotice,
    dismissNotice,
    refresh,
    restart,
    chooseLanguage,
  } = useSession();
  const [problem, setProblem] = useState<ProblemView | null>(null);
  const [code, setCode] = useState("");
  const [result, setResult] = useState<SubmissionResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Guards late responses: only the newest submit may update the screen.
  const requestId = useRef(0);
  const initializedFor = useRef<string | null>(null);
  const resultAnchor = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (
      sessionProblem &&
      initializedFor.current !== sessionProblem.problem_id
    ) {
      initializedFor.current = sessionProblem.problem_id;
      setProblem(sessionProblem);
      setCode(sessionProblem.starter_code);
      setResult(null);
      setError(null);
    }
  }, [sessionProblem]);

  useEffect(() => {
    if (result && resultAnchor.current) {
      resultAnchor.current.focus();
    }
  }, [result]);

  const submit = useCallback(async () => {
    if (!sessionId || !problem || busy) return;
    if (!code.trim()) {
      setError("Write some code before submitting.");
      return;
    }
    if (code.length > MAX_CODE_CHARS) {
      setError(
        `That code is too long (${code.length} characters, max ${MAX_CODE_CHARS}). Shorten it and try again.`,
      );
      return;
    }
    const mine = ++requestId.current;
    setBusy(true);
    setError(null);
    try {
      const response = await api.submit(sessionId, problem.problem_id, code);
      if (requestId.current !== mine) return;
      setResult(response);
      if (response.variant_role === "transfer") {
        void refresh();
      }
    } catch (err: unknown) {
      if (requestId.current === mine) setError(friendlyError(err));
    } finally {
      // A stale (invalidated) response must not unlock the current request.
      if (requestId.current === mine) setBusy(false);
    }
  }, [sessionId, problem, code, busy, refresh]);

  const continueToTransfer = useCallback(() => {
    const next = result?.transfer_problem;
    if (!next) return;
    requestId.current += 1; // invalidate any in-flight submit
    initializedFor.current = next.problem_id;
    setProblem(next);
    setCode(next.starter_code);
    setResult(null);
    setError(null);
  }, [result]);

  const retry = useCallback(() => {
    requestId.current += 1; // invalidate any in-flight submit
    setResult(null);
    setError(null);
  }, []);

  if (status === "loading") {
    return <Loading text="Loading your problem…" />;
  }

  if (status === "failed" || !sessionId) {
    return (
      <Alert title="Couldn't start your session.">
        <p className="mt-1">{error ?? "Backend unreachable."}</p>
        <SecondaryButton onClick={() => void restart()} className="mt-3">
          Try again
        </SecondaryButton>
      </Alert>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div
        className="flex flex-wrap items-center gap-2"
        role="group"
        aria-label="Language track"
      >
        <span className="text-sm text-zinc-600 dark:text-zinc-300">
          Language:
        </span>
        {(["python", "java"] as const).map((track) => (
          <SecondaryButton
            key={track}
            onClick={() => void chooseLanguage(track)}
            className={
              (problem?.language ?? language) === track
                ? "border-teal-700 font-semibold"
                : undefined
            }
          >
            {track === "python" ? "Python" : "Java"}
          </SecondaryButton>
        ))}
        <span className="text-xs text-zinc-500 dark:text-zinc-400">
          Switching starts a fresh {(language === "java" ? "Java" : "Python")}{" "}
          session.
        </span>
      </div>
      {freshNotice && (
        <Alert tone="info" title="Fresh session started">
          <div className="mt-1 flex flex-wrap items-center gap-3">
            <p>{freshNotice}</p>
            <SecondaryButton onClick={dismissNotice} className="px-3 py-1">
              Dismiss
            </SecondaryButton>
          </div>
        </Alert>
      )}

      <div className="grid items-start gap-6 lg:grid-cols-2">
        <div className="min-w-0">
          {problem && <ProblemPanel problem={problem} />}
        </div>
        <div className="min-w-0">
          {problem && (
            <CodeEditor
              code={code}
              busy={busy}
              sessionReady={sessionId !== null}
              onChange={setCode}
              onSubmit={() => void submit()}
              language={problem.language ?? language}
            />
          )}
        </div>
      </div>

      {error && problem && (
        <div
          className="rounded-xl border border-red-300 bg-red-50 p-4 text-sm text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-100"
          role="alert"
        >
          {error}
        </div>
      )}

      {result && problem && (
        <div ref={resultAnchor} tabIndex={-1}>
          <div className="rounded-xl border border-zinc-200 bg-white p-5 shadow-[0_1px_2px_rgba(0,0,0,0.04)] dark:border-zinc-800 dark:bg-zinc-950">
            <section aria-label="Result" aria-live="polite">
              <ResultPanel
                result={result}
                conceptId={problem.concept_id}
                onRetry={retry}
                onContinue={continueToTransfer}
              />
            </section>
          </div>
        </div>
      )}
    </div>
  );
}
