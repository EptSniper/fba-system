import {
  LayoutDashboard,
  PenLine,
  Target,
  Tag,
  ListChecks,
  Wallet,
  Package,
  MessageSquareText,
  Store,
  Gauge,
  Library,
  Wrench,
  BrainCircuit,
  Settings2,
  type LucideIcon,
} from "lucide-react";

export type NavItem = { href: string; label: string; icon: LucideIcon; group: string };

// One source of truth for navigation — used by the sidebar and the mobile nav.
export const NAV: NavItem[] = [
  { href: "/", label: "Today", icon: LayoutDashboard, group: "Command" },
  { href: "/log", label: "Log", icon: PenLine, group: "Command" },
  { href: "/find", label: "Find", icon: Target, group: "Sourcing" },
  { href: "/deals", label: "Deals", icon: Tag, group: "Sourcing" },
  { href: "/leads", label: "Pipeline", icon: ListChecks, group: "Sourcing" },
  { href: "/money", label: "Money", icon: Wallet, group: "Operations" },
  { href: "/inventory", label: "Inventory", icon: Package, group: "Operations" },
  { href: "/amazon", label: "Amazon Ops", icon: Store, group: "Operations" },
  { href: "/ask", label: "Ask", icon: MessageSquareText, group: "Knowledge" },
  { href: "/knowledge", label: "Sources", icon: Library, group: "Knowledge" },
  { href: "/intelligence", label: "Scout Intelligence", icon: Gauge, group: "System" },
  { href: "/brain", label: "Brain", icon: BrainCircuit, group: "System" },
  { href: "/tools", label: "Tools", icon: Wrench, group: "System" },
  { href: "/settings", label: "Settings", icon: Settings2, group: "System" },
];

export const NAV_GROUPS = ["Command", "Sourcing", "Operations", "Knowledge", "System"] as const;
