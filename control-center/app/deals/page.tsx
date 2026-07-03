import { Tag, Store } from "lucide-react";
import { getDeals } from "@/lib/data";
import { money, pct } from "@/lib/format";
import { Panel, Badge, EmptyState, ConnBadge, DataNote, ActionLink } from "@/components/ui";

export default function DealsPage() {
  const d = getDeals();
  return (
    <div className="flex flex-col gap-5">
      <header className="flex items-center justify-between">
        <h1 className="text-lg font-medium">Deals · always-on sourcing</h1>
        <ConnBadge connected={d.connected} />
      </header>

      <div className="flex flex-wrap gap-2">
        <ActionLink href="/find" tone="primary">Analyze a manual deal</ActionLink>
        <ActionLink href="/tools">Open sourcing tools</ActionLink>
      </div>

      <Panel title="The rule" icon={<Tag size={16} />}>
        <p className="text-sm text-muted">{d.principle}</p>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {d.watchedRetailers.map((r) => (
            <span key={r} className="inline-flex items-center gap-1 rounded-md bg-panel2 px-2 py-0.5 text-xs text-muted">
              <Store size={12} aria-hidden /> {r}
            </span>
          ))}
        </div>
      </Panel>

      <Panel
        title="Today's profitable deals"
        right={<DataNote source={d.source} updated={d.updated} />}
      >
        {d.today.length ? (
          <ul className="flex flex-col divide-y divide-line text-sm">
            {d.today.map((t, i) => (
              <li key={i} className="flex items-center justify-between py-2.5">
                <span>
                  <span className="text-muted">{t.retailer}</span> · {t.item}
                </span>
                <span className="num flex items-center gap-3">
                  {money(t.dealPrice)} → {money(t.amazonPrice)}
                  {typeof t.roi === "number" ? <Badge tone="success">roi {pct(t.roi)}</Badge> : null}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState
            icon={<Tag size={20} />}
            title="No deals tracked yet"
            hint={d.reason ?? "Connect a deal API (FMTC/LinkMyDeals) — see ai-system/deal-sourcing-system.md."}
          />
        )}
      </Panel>
    </div>
  );
}
