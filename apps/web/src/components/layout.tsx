/** Site header + primary navigation (Step 20A, 21B language-aware). */
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSessionOptional } from "./session";
import { Badge } from "./ui";

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/learn", label: "Learn" },
  { href: "/practice", label: "Practice" },
  { href: "/progress", label: "Progress" },
  { href: "/history", label: "History" },
];

/** Current route, falling back to "/" outside Next router context (tests). */
function useCurrentRoute(): string {
  try {
    return usePathname() ?? "/";
  } catch {
    return "/";
  }
}

export function SiteHeader() {
  const pathname = useCurrentRoute();
  const track = useSessionOptional()?.language ?? "python";
  const label = track === "java" ? "Java" : "Python";
  return (
    <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-4 sm:px-6">
        <div className="flex items-baseline gap-2">
          <Link
            href="/"
            className="text-xl font-semibold tracking-tight text-zinc-950 dark:text-zinc-50"
          >
            Cognify
          </Link>
          <span className="hidden text-xs text-zinc-500 sm:inline dark:text-zinc-400">
            adaptive programming practice
          </span>
        </div>
        <nav aria-label="Primary" className="flex flex-wrap items-center gap-1">
          {LINKS.map((link) => {
            const current =
              link.href === "/"
                ? pathname === "/"
                : pathname === link.href ||
                  pathname.startsWith(`${link.href}/`);
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={current ? "page" : undefined}
                className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                  current
                    ? "bg-zinc-100 text-zinc-950 dark:bg-zinc-800 dark:text-zinc-50"
                    : "text-zinc-500 hover:bg-zinc-50 hover:text-zinc-800 dark:text-zinc-400 dark:hover:bg-zinc-900 dark:hover:text-zinc-100"
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
        <p className="ml-auto">
          <Badge tone="info">{label} track</Badge>
        </p>
      </div>
    </header>
  );
}
