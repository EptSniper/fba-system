import Link from "next/link";
import { ARTICLES } from "@/lib/articles";

export default function HomePage() {
  return (
    <main className="wrap">
      <p className="tagline">
        Five practical guides on shopping smarter — how to read a price chart, what actually
        changed in 2026 fees, how cashback stacking really works, when deals are real, and how to
        spot the ones that aren&apos;t.
      </p>
      <ul className="article-list">
        {ARTICLES.map((a) => (
          <li key={a.slug} className="article-card">
            <h2>
              <Link href={`/articles/${a.slug}`}>{a.title}</Link>
            </h2>
            <p>{a.dek}</p>
            <div className="meta">{a.minutes} min read</div>
          </li>
        ))}
      </ul>
      <footer>
        Honest Deal Guides publishes original, independently written guides. We are not
        affiliated with any retailer we discuss. Some pages may in the future include affiliate
        links to programs we participate in, disclosed where they appear.
      </footer>
    </main>
  );
}
