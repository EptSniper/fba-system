import { KeyRound, Settings2, ShieldCheck } from "lucide-react";
import { PageHeader, Panel } from "@/components/ui";
import { ThemeControls } from "@/components/theme-controls";
import { KeyManager } from "@/components/key-manager";

const GUARDRAILS = [
  { label: "Humans approve every purchase", detail: "The system recommends; it never buys. No auto-buy path exists anywhere in scout/ or scout_pro/." },
  { label: "Allowed ≠ profitable", detail: "Eligibility/compliance and ROI are checked independently — a pass on one never implies the other." },
  { label: "Honest empty states", detail: "No fake data. A disconnected system says so; an empty list stays empty." },
  { label: "No secrets in the browser", detail: "Typed key values post directly to a same-origin API route that writes them to server-side .env files — never localStorage, never a third party, never echoed back." },
  { label: "Single source of truth", detail: "Every threshold traces to learning-hub/data/ai-brain.json — never a second hardcoded copy." },
];

export default function SettingsPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader eyebrow="System" title="Settings" description="Appearance, API keys, and the operating rules this console never breaks." />

      <Panel title="Appearance" icon={<Settings2 size={16} />}>
        <ThemeControls />
      </Panel>

      <Panel
        title="API Keys & Connections"
        icon={<KeyRound size={16} />}
        right="written to real .env files · live-testable"
      >
        <KeyManager />
      </Panel>

      <Panel title="Guardrails" icon={<ShieldCheck size={16} />} right="non-negotiable · locked">
        <ul className="flex flex-col divide-y divide-line">
          {GUARDRAILS.map((g) => (
            <li key={g.label} className="flex items-center gap-3 py-2.5">
              <div className="flex-1">
                <div className="text-[13px] font-medium text-ink">{g.label}</div>
                <div className="mt-0.5 text-[11px] text-muted">{g.detail}</div>
              </div>
              <span className="shrink-0 border border-profit/40 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-[0.08em] text-profit">
                locked
              </span>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
