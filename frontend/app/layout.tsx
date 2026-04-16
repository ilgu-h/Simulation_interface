import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Simulation Interface",
  description: "Orchestrate STG, Chakra, and ASTRA-sim from one dashboard.",
};

const navItems = [
  { href: "/workload", label: "Workload" },
  { href: "/system", label: "System" },
  { href: "/model", label: "Model" },
  { href: "/validate", label: "Validate" },
  { href: "/run/test", label: "Run" },
  { href: "/results/test", label: "Results" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-zinc-950 text-zinc-100">
        <header className="border-b border-zinc-800 px-6 py-4">
          <div className="mx-auto flex max-w-6xl items-center justify-between">
            <Link href="/" className="text-lg font-semibold tracking-tight">
              Simulation Interface
            </Link>
            <nav className="flex gap-4 text-sm text-zinc-400">
              {navItems.map((item) => (
                <Link key={item.href} href={item.href} className="hover:text-zinc-100">
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-10">{children}</main>
      </body>
    </html>
  );
}
