import { Camera, CircleHelp, Eye, MapPin, ShoppingBag, Sparkles, Ticket, UserPlus, Users, Zap, type LucideIcon } from 'lucide-react'

const ICONS: Record<string, LucideIcon> = {
  quiz: CircleHelp,
  selfie: Camera,
  action: Zap,
  purchase: ShoppingBag,
  registration: UserPlus,
  networking: Users,
  crazy: Sparkles,
  attention: Eye,
  territory: MapPin,
  pre: Ticket,
}

export function TaskIcon({ type, className = '' }: { type: string; className?: string }) {
  const Icon = ICONS[type] ?? Zap
  return <Icon className={className} aria-hidden />
}
