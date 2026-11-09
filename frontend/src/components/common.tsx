import type { ReactNode } from "react";
import type { Article, EvidenceLink, Version } from "../types";

const formatter = new Intl.DateTimeFormat("tr-TR", {
  dateStyle: "medium", timeStyle: "short", timeZone: "Europe/Istanbul",
});
export const dateTime = (value: string | null) => value ? formatter.format(new Date(value)) : "—";
export const scoreText = (value: number | null) => value === null ? "—" : value.toFixed(2).replace(".", ",");
export const scopeText = (version: Pick<Version, "scope">) => version.scope === "full" ? "Tam metin" : "Başlık / özet";
export const decisionText: Record<string, string> = {
  automatic: "Otomatik", confirmed: "Onaylandı", moved: "Elle taşındı", excluded: "Grup dışında",
};
export const statusText: Record<string, string> = {
  queued: "Sırada", running: "Toplanıyor", success: "Tamamlandı", partial: "Kısmi başarı",
  failed: "Başarısız", cancelled: "İptal edildi",
};

export function Heading({ label, title, children }: { label: string; title: string; children?: ReactNode }) {
  return <header className="page-heading"><p className="eyebrow">{label}</p><h1>{title}</h1>{children}</header>;
}
export function Empty({ children }: { children: ReactNode }) {
  return <div className="notice">{children}</div>;
}
export function Result<T>({ result, children }: {
  result: { data?: T; error?: string; reload: () => void }; children: (data: T) => ReactNode;
}) {
  if (result.error) return <div className="notice alert" role="alert">{result.error}{" "}
    <button type="button" onClick={result.reload}>Yeniden dene</button></div>;
  if (result.data === undefined) return <p className="notice" role="status">Yükleniyor…</p>;
  return <>{children(result.data)}</>;
}
export function Badge({ children, tone = "" }: { children: ReactNode; tone?: string }) {
  return <span className={"badge " + tone}>{children}</span>;
}
export function External({ url, children }: { url: string; children: ReactNode }) {
  try {
    const parsed = new URL(url);
    if (["http:", "https:"].includes(parsed.protocol) && !parsed.username && !parsed.password) {
      return <a href={parsed.href} target="_blank" rel="noopener noreferrer">{children} ↗</a>;
    }
  } catch { /* Display rejected URLs as text. */ }
  return <span>{children}</span>;
}
export function Reported({ value, raw, state }: { value: string | null; raw: string | null; state: string }) {
  if (value) return <time dateTime={value}>{dateTime(value)}</time>;
  if (state === "missing") return <>Bildirilmedi</>;
  return <span className="uncertain">{state === "uncertain" ? "Saat dilimi belirsiz" : "Geçersiz tarih"}{raw && <> · {raw}</>}</span>;
}
export function Times({ article, version }: { article: Article; version: Version }) {
  return <dl className="facts">
    <div><dt>Bildirilen yayın</dt><dd><Reported value={version.published} raw={version.published_raw} state={version.published_state} /></dd></div>
    <div><dt>Bildirilen güncelleme</dt><dd><Reported value={version.updated} raw={version.updated_raw} state={version.updated_state} /></dd></div>
    <div><dt>Sistemde ilk görülme</dt><dd>{dateTime(article.first_seen)}</dd></div>
    <div><dt>Sürümün toplandığı zaman</dt><dd>{dateTime(version.collected_at)}</dd></div>
  </dl>;
}
export function Links({ items, articles }: { items: EvidenceLink[]; articles: Article[] }) {
  if (!items.length) return <Empty>Bu kapsamda kaydedilmiş bağlantı yok.</Empty>;
  return <ul className="records">{items.map(item => {
    const source = articles.find(a => a.version.id === item.version_id);
    return <li key={item.id}>
      <Badge tone={item.kind === "explicit" ? "green" : ""}>{item.kind === "explicit" ? "Açık kaynak etiketi" : "Bağlantı"}</Badge>
      <strong><External url={item.url}>{item.text || item.url}</External></strong>
      {source && <small>Bağlantıyı veren yayın · {source.source.name}</small>}
      {item.context && <p>{item.context}</p>}
      {item.target_ids.map(id => <a key={id} href={"#/haber/" + id}>Toplanan hedef haber #{id}</a>)}
    </li>;
  })}</ul>;
}

