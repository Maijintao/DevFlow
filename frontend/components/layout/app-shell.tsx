"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, BookOpen, Boxes, ClipboardCheck, FolderGit2, GitBranch, LayoutDashboard, ListChecks, MessageSquareText } from "lucide-react";

const navItems = [
  { href: "/", label: "Workspace", icon: LayoutDashboard },
  { href: "/knowledge", label: "项目知识", icon: BookOpen },
  { href: "/rag", label: "RAG 工作室", icon: MessageSquareText },
  { href: "/repos", label: "Repos", icon: FolderGit2 },
  { href: "/action-drafts", label: "Drafts", icon: ClipboardCheck },
  { href: "/workflow-runs", label: "Runs", icon: Activity },
  { href: "/workspaces", label: "Reports", icon: ListChecks },
  { href: "/code-graph", label: "Code Graph", icon: GitBranch },
  { href: "/evals", label: "Evals", icon: Boxes }
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <main className="app-shell min-h-screen">
      <aside className="app-navigation">
        <Link href="/" className="app-brand" aria-label="DevFlow AI 首页">
          <span className="app-brand-mark">DF</span>
          <span>DevFlow AI</span>
        </Link>
        <nav className="app-nav-items" aria-label="主要导航">
          {navItems.map((item) => (
            <Link key={item.href} href={item.href} aria-current={pathname === item.href || (item.href !== "/" && pathname.startsWith(`${item.href}/`)) ? "page" : undefined} className="app-nav-link">
              <item.icon aria-hidden="true" className="h-4 w-4 shrink-0" />
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>
      <div className="app-content">{children}</div>
    </main>
  );
}
