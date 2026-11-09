"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { Activity, BookOpen, Boxes, ClipboardCheck, FolderGit2, GitBranch, LayoutDashboard, ListChecks, MessageSquareText } from "lucide-react";
import { apiGet, apiPatch, apiPost, apiPut } from "@/lib/api";

type Account = {
  id: string;
  username: string;
  name: string;
  avatar_url: string | null;
  github_login: string | null;
  is_admin: boolean;
  projects: { repo_id: string; role: string }[];
};

const navItems = [
  { href: "/", label: "工作台", icon: LayoutDashboard },
  { href: "/knowledge", label: "项目知识", icon: BookOpen },
  { href: "/rag", label: "知识问答", icon: MessageSquareText },
  { href: "/repos", label: "仓库管理", icon: FolderGit2 },
  { href: "/action-drafts", label: "操作草稿", icon: ClipboardCheck },
  { href: "/workflow-runs", label: "工作流记录", icon: Activity },
  { href: "/workspaces", label: "研发周报", icon: ListChecks },
  { href: "/code-graph", label: "代码图谱", icon: GitBranch },
  { href: "/evals", label: "效果评测", icon: Boxes }
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [account, setAccount] = useState<Account | null>(null);
  const [setup, setSetup] = useState(false);
  const [ready, setReady] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [name, setName] = useState("");
  const [avatar, setAvatar] = useState("");
  const [githubToken, setGithubToken] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [notice, setNotice] = useState("");
  const [repos, setRepos] = useState<{ id: string; full_name: string }[]>([]);
  const [selectedRepoId, setSelectedRepoId] = useState("");

  async function refreshAccount() {
    const result = await apiGet<Account>("/api/auth/me");
    setAccount(result);
    setName(result.name);
    setAvatar(result.avatar_url || "");
  }

  useEffect(() => {
    apiGet<{ setup_required: boolean }>("/api/auth/status")
      .then(async (status) => {
        setSetup(status.setup_required);
        if (!status.setup_required) await refreshAccount().catch(() => setAccount(null));
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "无法连接服务"))
      .finally(() => setReady(true));
  }, []);

  async function submitLogin(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await apiPost(setup ? "/api/auth/setup" : "/api/auth/login", { username, password });
      setPassword("");
      setSetup(false);
      await refreshAccount();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "登录失败");
    } finally {
      setBusy(false);
    }
  }

  async function saveProfile(event: FormEvent) {
    event.preventDefault();
    setError("");
    setNotice("");
    try {
      await apiPatch("/api/auth/profile", { name, avatar_url: avatar.trim() || null });
      await refreshAccount();
      setNotice("个人资料已保存");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存失败");
    }
  }

  async function saveGithubToken(event: FormEvent) {
    event.preventDefault();
    setError("");
    setNotice("");
    try {
      await apiPut("/api/auth/github-token", { token: githubToken });
      setGithubToken("");
      await refreshAccount();
      setNotice("GitHub 账号已关联");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "关联失败");
    }
  }

  async function logout() {
    await apiPost("/api/auth/logout", {});
    setAccount(null);
    setSettingsOpen(false);
  }

  async function savePassword(event: FormEvent) {
    event.preventDefault();
    setError("");
    setNotice("");
    try {
      await apiPut("/api/auth/password", { current_password: currentPassword, new_password: newPassword });
      setCurrentPassword("");
      setNewPassword("");
      setNotice("密码已更新");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "密码更新失败");
    }
  }

  async function useProjectToken() {
    setError("");
    setNotice("");
    try {
      await apiPost(`/api/auth/github-token/from-project/${selectedRepoId}`, {});
      await refreshAccount();
      setNotice("GitHub 账号已关联");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "关联失败");
    }
  }

  async function openSettings() {
    setSettingsOpen(true);
    setError("");
    setNotice("");
    if (account?.is_admin) {
      try {
        const items = await apiGet<{ id: string; full_name: string }[]>("/api/repos");
        setRepos(items);
        setSelectedRepoId(items[0]?.id || "");
      } catch (reason) {
        setError(reason instanceof Error ? reason.message : "读取项目失败");
      }
    }
  }

  if (!ready) return <main className="flex min-h-screen items-center justify-center bg-panel text-sm text-slate-600">正在读取账号信息...</main>;
  if (!account) return (
    <main className="flex min-h-screen items-center justify-center bg-panel p-5">
      <form onSubmit={submitLogin} className="w-full max-w-md rounded-xl bg-white p-8 shadow-sm">
        <div className="text-sm font-semibold text-accent">DevFlow AI</div>
        <h1 className="mt-3 text-2xl font-semibold text-ink">{setup ? "创建组长账号" : "登录"}</h1>
        <p className="mt-2 text-sm leading-6 text-slate-600">{setup ? "设置账号和密码，用于管理项目及成员。" : "使用组长分配的账号和密码进入项目。"}</p>
        <label className="mt-6 block text-sm font-medium text-ink">账号<input required value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" className="mt-2 h-10 w-full rounded-md border border-line px-3 outline-none focus:border-accent" /></label>
        <label className="mt-4 block text-sm font-medium text-ink">密码<input required type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete={setup ? "new-password" : "current-password"} className="mt-2 h-10 w-full rounded-md border border-line px-3 outline-none focus:border-accent" /></label>
        {error && <p role="alert" className="mt-4 text-sm text-rose-700">{error}</p>}
        <button type="submit" disabled={busy} className="primary-button mt-6 h-10 w-full rounded-md text-sm font-medium disabled:opacity-50">{busy ? "请稍候..." : setup ? "创建账号并进入" : "登录"}</button>
      </form>
    </main>
  );

  return (
    <main className="app-shell min-h-screen">
      <aside className="app-navigation">
        <Link href="/" className="app-brand" aria-label="DevFlow AI 首页">
          <Image src="/devflow-logo.png" alt="" width={2172} height={724} className="app-brand-image" priority />
        </Link>
        <nav className="app-nav-items" aria-label="主要导航">
          {navItems.map((item) => (
            <Link key={item.href} href={item.href} aria-current={pathname === item.href || (item.href !== "/" && pathname.startsWith(`${item.href}/`)) ? "page" : undefined} className="app-nav-link">
              <item.icon aria-hidden="true" className="h-4 w-4 shrink-0" />
              {item.label}
            </Link>
          ))}
        </nav>
        <button onClick={openSettings} className="mx-3 mt-auto flex items-center gap-2 rounded-md px-3 py-3 text-left text-sm text-slate-700 hover:bg-panel">
          {account.avatar_url ? <Image src={account.avatar_url} alt="" width={32} height={32} unoptimized referrerPolicy="no-referrer" className="h-8 w-8 rounded-full object-cover" /> : <span className="flex h-8 w-8 items-center justify-center rounded-full bg-panel font-semibold">{account.name.slice(0, 1).toUpperCase()}</span>}
          <span className="min-w-0 truncate">{account.name}</span>
        </button>
      </aside>
      <div className="app-content">{children}</div>
      {settingsOpen && <div className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/35 p-4">
        <section role="dialog" aria-modal="true" aria-label="账号设置" className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-xl bg-white p-6 shadow-xl">
          <div className="flex items-center justify-between gap-3"><h2 className="text-lg font-semibold text-ink">账号设置</h2><button onClick={() => setSettingsOpen(false)} className="rounded-md border border-line px-3 py-1.5 text-sm text-slate-600">关闭</button></div>
          <p className="mt-1 text-sm text-slate-500">账号：{account.username}</p>
          <form onSubmit={saveProfile} className="mt-6 space-y-3">
            <label className="block text-sm text-ink">昵称<input required value={name} onChange={(event) => setName(event.target.value)} className="mt-1.5 h-10 w-full rounded-md border border-line px-3" /></label>
            <label className="block text-sm text-ink">头像图片地址<input type="url" value={avatar} onChange={(event) => setAvatar(event.target.value)} placeholder="https://..." className="mt-1.5 h-10 w-full rounded-md border border-line px-3" /></label>
            <button className="rounded-md border border-line px-3 py-2 text-sm hover:bg-panel">保存个人资料</button>
          </form>
          <form onSubmit={saveGithubToken} className="mt-6 border-t border-line pt-5">
            <h3 className="text-sm font-semibold text-ink">GitHub 账号</h3>
            <p className="mt-1 text-sm text-slate-600">{account.github_login ? `已关联 ${account.github_login}` : "关联个人 Token 后，可以在项目中执行 GitHub 操作。"}</p>
            <input type="password" value={githubToken} onChange={(event) => setGithubToken(event.target.value)} placeholder="个人 GitHub Token" autoComplete="off" className="mt-3 h-10 w-full rounded-md border border-line px-3 text-sm" />
            <button disabled={!githubToken.trim()} className="primary-button mt-3 rounded-md px-3 py-2 text-sm disabled:opacity-50">关联账号</button>
          </form>
          {account.is_admin && !account.github_login && repos.length > 0 && <div className="mt-3 space-y-2">
            <p className="text-xs leading-5 text-slate-500">也可以使用连接项目时保存的 GitHub 账号。</p>
            <select aria-label="选择项目" value={selectedRepoId} onChange={(event) => setSelectedRepoId(event.target.value)} className="h-9 w-full rounded-md border border-line bg-white px-3 text-sm">{repos.map((repo) => <option key={repo.id} value={repo.id}>{repo.full_name}</option>)}</select>
            <button onClick={useProjectToken} disabled={!selectedRepoId} className="rounded-md border border-line px-3 py-2 text-sm hover:bg-panel disabled:opacity-50">关联项目的 GitHub 账号</button>
          </div>}
          <form onSubmit={savePassword} className="mt-6 space-y-2 border-t border-line pt-5">
            <h3 className="text-sm font-semibold text-ink">修改密码</h3>
            <input required type="password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} placeholder="当前密码" autoComplete="current-password" className="h-10 w-full rounded-md border border-line px-3 text-sm" />
            <input required type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} placeholder="新密码" autoComplete="new-password" className="h-10 w-full rounded-md border border-line px-3 text-sm" />
            <button className="rounded-md border border-line px-3 py-2 text-sm hover:bg-panel">更新密码</button>
          </form>
          {error && <p role="alert" className="mt-4 text-sm text-rose-700">{error}</p>}{notice && <p role="status" className="mt-4 text-sm text-slate-700">{notice}</p>}
          <button onClick={logout} className="mt-6 border-t border-line pt-4 text-sm text-slate-600 hover:text-ink">退出登录</button>
        </section>
      </div>}
    </main>
  );
}
