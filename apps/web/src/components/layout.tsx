/** Site header + primary navigation (Step 20A). */
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

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
  return (
    <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <div className="mx-auto flex w-full max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-6 py-4">
        <Link
          href="/"
          className="text-xl font-semibold tracking-tight text-zinc-950 dark:text-zinc-50"
        >
          Cognify
        </Link>
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
        <p className="ml-auto text-sm text-zinc-500 dark:text-zinc-400">
          current language: Python
        </p>
      </div>
    </header>
  );
}
