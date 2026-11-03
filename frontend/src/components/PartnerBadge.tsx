import { Star } from 'lucide-react'

export function PartnerBadge({ name }: { name: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
      <Star className="size-3 fill-current" aria-hidden />
      {name}
    </span>
  )
}
