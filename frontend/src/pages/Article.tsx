import { useState, type FormEvent } from "react";
import { Badge, dateTime, decisionText, Empty, External, Heading, Links, Result, scopeText, scoreText, Times } from "../components/common";
import { useApi } from "../hooks/useApi";
import { api, json } from "../services/api";
import type { ArticleDetail, Comparison, Membership } from "../types";
import { NotesPanel, WatchToggle } from "../components/ResearchCommon";
import { VersionFindings, VersionPicker } from "./Evolution";

function ArticleContent({ article, reload, initialVersion }: { article: ArticleDetail; reload: () => void; initialVersion?: string }) {
  const [versionId, setVersionId] = useState(initialVersion ? Number(initialVersion) : undefined);
  const [target, setTarget] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error?: boolean }>();
  const version = article.versions.find(v => v.id === versionId) ?? article.versions[0];

  async function decide(decision: "confirmed" | "moved" | "excluded", cluster_id?: number) {
    setBusy(true);
    setMessage(undefined);
    try {
      await api<Membership>("/articles/" + article.id + "/membership", json("PUT", { decision, cluster_id }));
      setMessage({ text: "Grup kararı kaydedildi." });
      reload();
    } catch (error) { setMessage({ text: (error as Error).message, error: true }); }
    finally { setBusy(false); }
  }

  return <>
    <a className="back" href={article.membership?.cluster_id ? "#/grup/" + article.membership.cluster_id : "#/gruplar"}>← {article.membership?.cluster_id ? "Gruba dön" : "Haber grupları"}</a>
    <Heading label={"HABER / " + article.id} title={article.version.title || "(Başlıksız)"}>
      <p>{article.source.name} · <External url={article.url}>Yayın adresini aç</External></p>
      {article.source.demo && <Badge tone="amber">Kurgusal örnek veri</Badge>}
      <WatchToggle kind="article" id={article.id} />
    </Heading>
    <section className="panel">
      <div className="section-head"><h2>Sürüm geçmişi</h2><Badge>{article.versions.length} sürüm</Badge></div>
      <div className="form"><label>İncelenen sürüm<select value={version.id} onChange={e => setVersionId(Number(e.target.value))}>
        {article.versions.map((v, index) => <option key={v.id} value={v.id}>{dateTime(v.collected_at)} · #{v.id}{index === 0 ? " · Son sürüm" : ""}</option>)}</select></label>
        <div><Badge>{scopeText(version)}</Badge> <small>{version.extractor}</small></div>
        <Times article={article} version={version} />
        <h3>{version.title}</h3>
        {version.summary && <p>{version.summary}</p>}
        {version.body && <p className="body-text">{version.body}</p>}
      </div>
    </section>
    <VersionPicker article={article} />
    <VersionFindings key={version.id} version={version} />
    <section className="panel"><div className="section-head"><h2>Bu sürümdeki bağlantılar</h2></div>
      <Links items={article.links.filter(link => link.version_id === version.id)} articles={[]} /></section>
    <section className="panel"><div className="section-head"><h2>Araştırmacı kararı</h2></div>
      <div className="form">
        <p>{decisionText[article.membership?.decision ?? ""] ?? "Üyelik yok"}{article.membership?.cluster_id && <> · <a href={"#/grup/" + article.membership.cluster_id}>Grup #{article.membership.cluster_id}</a></>}</p>
        {message && <p className={"notice " + (message.error ? "alert" : "")} role={message.error ? "alert" : "status"}>{message.text}</p>}
        <div className="actions">
          <button disabled={busy || !article.membership?.cluster_id} onClick={() => void decide("confirmed")}>Üyeliği onayla</button>
          <button disabled={busy || !article.membership?.cluster_id} onClick={() => void decide("excluded")}>Gruptan çıkar</button>
          <button disabled={busy} onClick={() => void decide("moved")}>Yeni gruba ayır</button>
        </div>
        <form className="actions" onSubmit={(e: FormEvent) => { e.preventDefault(); void decide("moved", Number(target)); }}>
          <label>Hedef grup numarası<input required type="number" min="1" value={target} onChange={e => setTarget(e.target.value)} /></label>
          <button className="primary" disabled={busy}>Gruba taşı</button>
        </form>
      </div>
    </section>
    <NotesPanel kind="article" id={article.id} title="Habere ilişkin araştırmacı notları" />
    <NotesPanel key={version.id} kind="version" id={version.id} title={"Sürüm #" + version.id + " notları"} />
  </>;
}

export function ArticlePage({ id, version }: { id: string; version?: string }) {
  const result = useApi<ArticleDetail>("/articles/" + id);
  return <Result result={result}>{article => version && !article.versions.some(item => item.id === Number(version)) ?
    <Empty>Bu haber için istenen sürüm bulunamadı. <a href={"#/haber/" + article.id}>Haber detayını aç</a></Empty> :
    <ArticleContent key={article.id + "/" + (version ?? "")} article={article} reload={result.reload}
      initialVersion={version} />}</Result>;
}

export function Compare({ left, right }: { left: string; right: string }) {
  const result = useApi<Comparison>("/compare?left=" + left + "&right=" + right);
  const a = useApi<ArticleDetail>("/articles/" + left);
  const b = useApi<ArticleDetail>("/articles/" + right);
  return <>
    <a className="back" href={a.data?.membership?.cluster_id ? "#/grup/" + a.data.membership.cluster_id : "#/gruplar"}>← Gruba dön</a>
    <Heading label="04 / Karşılaştırma" title="Metin karşılaştırması"><p>Analiz, her iki haberin son toplanan sürümünü kullanır.</p>
      {(a.data?.source.demo || b.data?.source.demo) && <Badge tone="amber">Kurgusal örnek veri</Badge>}
    </Heading>
    <Result result={result}>{value => <>
      <div className="notice"><strong>Metin benzerliği · {scoreText(value.score)}</strong>
        <p>{value.score === null ? "Metinlerden en az biri puanlama için kısa." : value.method === "sha256-v1" ? "Analiz kapsamındaki içerik özeti birebir eşleşiyor." :
          "İki sürüm ortak TF-IDF uzayında karşılaştırıldı. Grup üyeliği puanı, gruplama anındaki aday kümesine göre hesaplanır."}</p>
        <small>Yöntem · {value.method} · Gruplama sürümü · {value.analysis_version}</small>
      </div>
      <div className="compare-grid">
        {[value.left, value.right].map((v, index) => <article className="panel" key={v.id}>
          <div className="section-head"><a href={"#/haber/" + [left, right][index]}>{[a.data?.source.name, b.data?.source.name][index] ?? "Haber detayı"}</a><Badge>{scopeText(v)}</Badge></div>
          <div className="form"><h2>{v.title}</h2><p className="body-text">{v.body || v.summary || v.title}</p></div>
        </article>)}
      </div>
      <section className="panel"><div className="section-head"><h2>Ortak metin bölümleri</h2></div>
        <p className="panel-note">İlk 2.500 sözcükte art arda eşleşen en az beş sözcüklük diziler.</p>
        {value.segments.length ? <ol className="records">{value.segments.map((s, index) =>
          <li key={index} className="compare-grid"><p><mark>{s.left}</mark></p><p><mark>{s.right}</mark></p></li>)}</ol> : <Empty>Bu kurala uyan ortak bölüm bulunamadı.</Empty>}
      </section>
    </>}</Result>
  </>;
}
