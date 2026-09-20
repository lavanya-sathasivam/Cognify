import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { SiteHeader } from "../components/layout";
import { SessionProvider } from "../components/session";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Cognify",
  description: "Adaptive programming learning: problem, code, feedback, retry.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <SessionProvider>
          <div className="flex min-h-full flex-col bg-zinc-50 text-zinc-950 dark:bg-black dark:text-zinc-50">
            <SiteHeader />
            <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 px-4 py-6 sm:px-6">
              {children}
            </main>
            <footer className="border-t border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
              <p className="mx-auto w-full max-w-6xl px-4 py-4 text-xs text-zinc-500 sm:px-6 dark:text-zinc-400">
                Cognify — adaptive programming practice in Python and Java.
                Your code runs on the server; feedback is based on your actual
                attempts.
              </p>
            </footer>
          </div>
        </SessionProvider>
      </body>
    </html>
  );
}
