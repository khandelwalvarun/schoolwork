/**
 * Centralised icon set. lucide-react is tree-shakable so only the icons we
 * import here actually ship in the bundle. Default size 16, default stroke
 * 1.75 to match the surrounding 14 px text.
 *
 * Adding a new icon: import { X } from 'lucide-react' below, re-export it
 * with the chosen alias. Don't pass icon names from outside this module —
 * the indirection lets us swap libraries later without touching call sites.
 */
import {
  GraduationCap,
  Library,
  ListTree,
  StickyNote,
  Inbox,
  Bell,
  Settings,
  Files,
  HelpCircle,
  Calendar,
  CheckCheck,
  Search,
  Sun as SnoozeIcon,  // a clean snooze glyph isn't in lucide; reuse Sun
} from "lucide-react";

export const Icons = {
  Logo: GraduationCap,
  Library,
  Spelling: ListTree,
  Notes: StickyNote,
  Inbox,
  Bell,
  Settings,
  Files,
  Help: HelpCircle,
  Calendar,
  Check: CheckCheck,
  Search,
  Snooze: SnoozeIcon,
};

export type IconName = keyof typeof Icons;

export function Icon({
  name,
  size = 16,
  className = "",
  strokeWidth = 1.75,
  "aria-label": ariaLabel,
}: {
  name: IconName;
  size?: number;
  className?: string;
  strokeWidth?: number;
  "aria-label"?: string;
}) {
  const C = Icons[name];
  return (
    <C
      size={size}
      strokeWidth={strokeWidth}
      className={className}
      aria-hidden={ariaLabel ? undefined : true}
      aria-label={ariaLabel}
    />
  );
}
