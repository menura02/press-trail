import { useState, type FormEvent } from "react";
import { Badge, dateTime, Empty, Heading, Links, Result, scopeText, scoreText, decisionText, Times } from "../components/common";
import { useApi } from "../hooks/useApi";
import type { Article, GroupDetail, GroupList, Source } from "../types";
import { GroupRows } from "./Overview";
import { WatchToggle } from "../components/ResearchCommon";
import { GroupClaims, ReportPanel } from "./GroupResearch";

export function Groups() {
  const sources = useApi<Source[]>("/sources");
  const [filters, setFilters] = useState("");
  const [offset, setOffset] = useState(0);
  const groups = useApi<GroupList>("/clusters?offset=" + offset + filters);
  const excluded = useApi<Article[]>("/articles?decision=excluded");
  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    const params = new URLSearchParams();
    values.forEach((value, key) => { if (String(value).trim()) params.set(key, String(value).trim()); });
    setOffset(0);
    setFilters(params.size ? "&" + params : "");
  }
  return <>
    <Heading label="03 / Metin analizi" title="Haber grupları"><p>Yayın, başlık ve bilinen yayın tarihi üzerinden aday grupları bulun.</p></Heading>
    <section className="panel">
      <form className="filters" onSubmit={search}>
        <label>Başlık<input name="q" type="search" maxLength={150} placeholder="Örn. su seviyesi" /></label>
        <label>Yayın<select name="source_id"><option value="">Tüm yayınlar</option>{sources.data?.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
        <label>Başlangıç<input name="start" type="date" /></label>
        <label>Bitiş<input name="end" type="date" /></label>
        <button className="primary">Filtrele</button>
      </form>
      <Result result={groups}>{data => <>
        <GroupRows groups={data.items} />
        {(offset > 0 || data.more) && <div className="actions form">
          <button disabled={!offset} onClick={() => setOffset(offset - 50)}>Önceki</button>
          <button disabled={!data.more} onClick={() => setOffset(offset + 50)}>Sonraki</button>
        </div>}
      </>}</Result>
    </section>
    <section className="panel"><div className="section-head"><h2>Grup dışındaki haberler</h2></div>
      <Result result={excluded}>{items => items.length ? <ul className="records">{items.map(a => <li key={a.id}><a href={"#/haber/" + a.id}>{a.version.title}</a><small>{a.source.name}</small></li>)}</ul> : <Empty>Elle gruptan çıkarılmış haber yok.</Empty>}</Result>
    </section>
  </>;
}

function GroupContent({ group }: { group: GroupDetail }) {
  const [selected, setSelected] = useState<number[]>([]);
  const articles = group.articles;
  const earliest = articles.find(a => a.version.published);
  const firstSeen = [...articles].sort((a, b) => Date.parse(a.first_seen) - Date.parse(b.first_seen))[0];
  const picked = selected.filter(id => articles.some(a => a.id === id));
  return <>
    <Heading label={"GRUP / " + String(group.id).padStart(3, "0")} title={group.title}>
      {articles.some(a => a.source.demo) && <Badge tone="amber">Kurgusal örnek veri</Badge>}
      <p>{articles.length} haber · Zamanlar İstanbul saatine göre gösterilir.</p>
      <WatchToggle kind="cluster" id={group.id} />
    </Heading>
    <div className="overview-grid">
      <section className="panel"><div className="section-head"><h2>Toplanan kaynaklar arasında en erken bildirilen yayın</h2></div>
        <div className="form">{earliest ? <><strong>{earliest.source.name}</strong><p>{dateTime(earliest.version.published)}</p></> : <p>Bilinen yayın zamanı yok.</p>}</div></section>
      <section className="panel"><div className="section-head"><h2>Sistemde ilk görülme</h2></div>
        <div className="form">{firstSeen ? <><strong>{firstSeen.source.name}</strong><p>{dateTime(firstSeen.first_seen)}</p></> : <p>Üye haber yok.</p>}</div></section>
    </div>
    <section className="panel">
      <div className="section-head"><h2>Yayın zaman çizelgesi</h2>{picked.length === 2 && <a className="button primary" href={"#/karsilastir/" + picked.join("/")}>Karşılaştır</a>}</div>
      {articles.length ? <><p className="panel-note">Bilinen yayın zamanına göre sıralanır. Karşılaştırma için iki haber seçin.</p>
        <ol className="records timeline">{articles.map(a => <li key={a.id}>
          <div className="row-line"><a className="row-title" href={"#/haber/" + a.id}>{a.version.title || "(Başlıksız)"}</a><Badge>{scopeText(a.version)}</Badge></div>
          <small>{a.source.name} · {decisionText[a.membership?.decision ?? ""]} · {a.membership?.method}</small>
          {a.membership?.score != null && <small>Gruba eklenirken en düşük üye benzerliği · {scoreText(a.membership.score)}</small>}
          <Times article={a} version={a.version} />
          {articles.length > 1 && <label className="check"><input type="checkbox" checked={picked.includes(a.id)}
            disabled={picked.length === 2 && !picked.includes(a.id)} onChange={e => setSelected(e.target.checked ? [...picked, a.id] : picked.filter(id => id !== a.id))} /> Karşılaştırmaya ekle</label>}
        </li>)}</ol></> : <Empty>Bu grubun üye haberi yok.</Empty>}
    </section>
    <section className="panel"><div className="section-head"><h2>Metinden çıkarılan bağlantılar</h2></div>
      <Links items={group.links} articles={articles} /></section>
    <GroupClaims id={group.id} />
    <ReportPanel id={group.id} />
  </>;
}

export function GroupPage({ id }: { id: string }) {
  const result = useApi<GroupDetail>("/clusters/" + id);
  return <><a className="back" href="#/gruplar">← Haber grupları</a><Result result={result}>{group => <GroupContent key={group.id} group={group} />}</Result></>;
}
