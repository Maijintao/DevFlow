import { clsx } from "clsx";

export function Card({ className, children }: { className?: string; children: React.ReactNode }) {
  return (
    <section className={clsx("surface-card border border-line bg-white p-4", className)}>
      {children}
    </section>
  );
}

export function PageTitle({ title, description }: { title: string; description: string }) {
  return (
    <div className="page-title mb-4 flex flex-col gap-1 pb-4">
      <h1 className="text-xl font-semibold tracking-normal text-ink md:text-2xl">{title}</h1>
      <p className="max-w-3xl text-sm leading-5 text-slate-600">{description}</p>
    </div>
  );
}

export function PrimaryButton({ children, className, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={clsx(
        "primary-button inline-flex items-center justify-center bg-accent px-4 py-2 text-sm font-bold text-white transition hover:bg-teal-700 disabled:cursor-not-allowed disabled:opacity-60",
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export function GhostButton({ children, className, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={clsx(
        "w-full rounded-md border border-line bg-white px-3 py-2 text-left text-sm text-slate-700 transition hover:border-teal-200 hover:bg-teal-50/70 hover:text-teal-900",
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}
