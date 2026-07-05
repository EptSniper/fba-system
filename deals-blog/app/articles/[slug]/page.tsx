import Link from "next/link";
import { notFound } from "next/navigation";
import { ARTICLES, getArticle } from "@/lib/articles";

export function generateStaticParams() {
  return ARTICLES.map((a) => ({ slug: a.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const article = getArticle(slug);
  if (!article) return {};
  return { title: `${article.title} — Honest Deal Guides`, description: article.dek };
}

function renderBody(body: string[]) {
  return body.map((block, i) => {
    if (block.startsWith("## ")) {
      return <h2 key={i}>{block.slice(3)}</h2>;
    }
    if (block.startsWith("- ")) {
      return (
        <li key={i} style={{ marginLeft: "1.25rem" }}>
          {block.slice(2)}
        </li>
      );
    }
    return <p key={i}>{block}</p>;
  });
}

export default async function ArticlePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const article = getArticle(slug);
  if (!article) notFound();

  return (
    <main className="wrap article">
      <Link href="/" className="back-link">
        ← All guides
      </Link>
      <h1>{article.title}</h1>
      <p className="dek">{article.dek}</p>
      <div className="meta" style={{ marginBottom: "1.5rem" }}>
        {article.minutes} min read
      </div>
      {renderBody(article.body)}
      <footer>Honest Deal Guides — original guides, no scraped content, no fake bylines.</footer>
    </main>
  );
}
