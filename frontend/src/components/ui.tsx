import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from 'react'

export function Button({ className = '', variant = 'primary', ...props }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'outline' }) {
  const look = variant === 'primary'
    ? 'bg-emerald-600 text-white hover:bg-emerald-700'
    : 'border border-slate-300 bg-white text-slate-800 hover:bg-slate-50'
  return (
    <button
      className={`inline-flex h-12 items-center justify-center rounded-xl px-5 text-base font-medium transition disabled:opacity-50 ${look} ${className}`}
      {...props}
    />
  )
}

export function Input({ className = '', ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={`h-12 w-full rounded-xl border border-slate-300 bg-white px-4 text-base outline-none focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/20 ${className}`}
      {...props}
    />
  )
}

export function Screen({ children }: { children: ReactNode }) {
  return (
    <main className="min-h-dvh bg-slate-50 px-4 py-8 text-slate-900">
      <div className="mx-auto flex w-full max-w-md flex-col gap-4">{children}</div>
    </main>
  )
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-2xl bg-white p-6 shadow-sm ring-1 ring-slate-200 ${className}`}>{children}</div>
}
