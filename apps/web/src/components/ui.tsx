/** Reusable presentational primitives (Step 20A).
 *
 * Real UI concepts only: cards, buttons, alerts, status. No intelligence
 * lives here — these components render whatever text and state callers
 * pass in.
 */
import type { ReactNode } from "react";
import { levelLabel } from "../app/lib/copy";

export function Card({
  children,
  label,
  className = "",
}: {
  children: ReactNode;
  label?: string;
  className?: string;
}) {
  return (
    <section
      aria-label={label}
      className={`rounded-xl border border-zinc-200 bg-white p-5 shadow-[0_1px_2px_rgba(0,0,0,0.04)] dark:border-zinc-800 dark:bg-zinc-950 ${className}`}
    >
      {children}
    </section>
  );
}

export function PageHeading({
  title,
  intro,
}: {
  title: string;
  intro?: string;
}) {
  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      {intro && (
        <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
          {intro}
        </p>
      )}
    </div>
  );
}

export function PrimaryButton({
  children,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...rest}
      className={`rounded-lg bg-teal-800 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-teal-700 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-teal-200 dark:text-teal-950 dark:hover:bg-teal-100 ${rest.className ?? ""}`}
    >
      {children}
    </button>
  );
}

export function SecondaryButton({
  children,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      {...rest}
      className={`rounded-lg border border-zinc-300 bg-white px-4 py-2 text-sm font-medium text-zinc-800 transition-colors hover:bg-zinc-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-100 dark:hover:bg-zinc-900 ${rest.className ?? ""}`}
    >
      {children}
    </button>
  );
}

export function Alert({
  tone = "error",
  title,
  children,
}: {
  tone?: "error" | "info" | "success";
  title?: string;
  children: ReactNode;
}) {
  const tones: Record<string, string> = {
    error:
      "border-red-300 bg-red-50 text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-100",
    info: "border-teal-200 bg-teal-50 text-teal-950 dark:border-teal-800 dark:bg-teal-950 dark:text-teal-100",
    success:
      "border-emerald-300 bg-emerald-50 text-emerald-950 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-100",
  };
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={`rounded-xl border p-4 text-sm ${tones[tone]}`}
    >
      {title && <p className="font-medium">{title}</p>}
      <div className={title ? "mt-1" : ""}>{children}</div>
    </div>
  );
}

export function Loading({ text = "Loading…" }: { text?: string }) {
  return (
    <p className="text-sm text-zinc-500 dark:text-zinc-400" role="status">
      {text}
    </p>
  );
}

export function EmptyState({
  title,
  body,
  action,
}: {
  title: string;
  body: string;
  action?: ReactNode;
}) {
  return (
    <Card label={title}>
      <h2 className="text-base font-semibold">{title}</h2>
      <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
        {body}
      </p>
      {action && <div className="mt-4">{action}</div>}
    </Card>
  );
}

/** Human level label for a backend mastery band. Never shows raw numbers. */
export function LevelLabel({ band }: { band: string }) {
  return (
    <span className="inline-flex items-center rounded-full border border-zinc-200 bg-zinc-100 px-2.5 py-0.5 text-xs font-medium text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200">
      {levelLabel(band)}
    </span>
  );
}

/** Small ✓ / ✗ / ! marker with text (meaning never carried by color alone). */
export function Mark({ kind }: { kind: "pass" | "fail" | "warn" }) {
  const glyph = kind === "pass" ? "✓" : kind === "fail" ? "✗" : "!";
  const style =
    kind === "pass"
      ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200"
      : kind === "fail"
        ? "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-200"
        : "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200";
  return (
    <span
      aria-hidden="true"
      className={`inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-bold ${style}`}
    >
      {glyph}
    </span>
  );
}
