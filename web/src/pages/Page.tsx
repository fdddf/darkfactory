import type { ReactNode } from 'react'

export default function Page({ title, sub, actions, children }: {
  title: string; sub?: ReactNode; actions?: ReactNode; children: ReactNode
}) {
  return (
    <div className="min-h-full flex flex-col bg-canvas">
      <header className="h-16 shrink-0 px-7 flex items-center justify-between gap-6
                         border-b border-line bg-surface sticky top-0 z-10">
        <div className="min-w-0">
          <h1 className="text-[16px] font-semibold tracking-tight">{title}</h1>
          {sub && <div className="text-[11.5px] text-muted-fg truncate">{sub}</div>}
        </div>
        <div className="flex items-center gap-2 shrink-0">{actions}</div>
      </header>
      <div className="p-7 flex-1">{children}</div>
    </div>
  )
}
