import { Badge, dateTime, Empty, Result, statusText } from "../components/common";
import { Icon } from "../components/Icon";
import { useApi } from "../hooks/useApi";
import type { Group, GroupList, Run, Source } from "../types";

export function GroupRows({ groups }: { groups: Group[] }) {
  if (!groups.length) return <Empty>Gösterilecek haber grubu bulunamadı.</Empty>;
  return <ul className="records group-rows">{groups.map(group => <li key={group.id}>
    <span className="group-icon"><Icon name="layers" /></span>
    <div className="group-name"><a className="row-title" href={"#/grup/" + group.id}>{group.title}</a>
      <div className="group-meta"><span className="record-id">GRP-{String(group.id).padStart(3, "0")}</span>
        {group.demo && <Badge tone="amber">Örnek veri</Badge>}</div>
    </div>
    <span className="muted group-count">{group.count} haber <Icon name="chevron" size={14} /></span>
  </li>)}</ul>;
}
const errors: Record<string, string> = {
  timeout: "Zaman aşımı", http: "HTTP hatası", http_retry: "Geçici HTTP hatası", parse: "Ayrıştırma hatası",
  blocked_target: "Engellenen hedef", dns: "DNS hatası", transport: "Bağlantı hatası", robots: "Robots kuralı",
  access: "Erişim kısıtı", extract: "Ana metin çıkarılamadı", too_large: "Yanıt çok büyük",
  encoding: "Yanıt kodlaması", redirect_limit: "Yönlendirme sınırı", internal: "İşleme hatası",
  lease_expired: "İş sahipliği süresi doldu",
};
function errorText(value: string) {
  return value.split(",").map(part => {
    const [kind, count] = part.split(":");
    return (errors[kind] ?? kind) + (count ? " (" + count + ")" : "");
  }).join(", ");
}

export function RunRows({ runs, sources }: { runs: Run[]; sources: Source[] }) {
  if (!runs.length) return <Empty>Henüz toplama işi yok.</Empty>;
  return <ul className="records">{runs.map(run => <li key={run.id}>
    <div className="row-line">
      <strong>{sources.find(s => s.id === run.source_id)?.name ?? ("Kaynak #" + run.source_id)}</strong>
      <Badge tone={run.status === "failed" || run.status === "partial" ? "amber" : "green"}>{statusText[run.status]}</Badge>
    </div>
    <small>{dateTime(run.finished_at ?? run.started_at ?? run.created_at)} · {run.attempts} deneme</small>
    <p>{run.seen} kayıt · {run.versions} yeni sürüm · {run.skipped} atlanan{run.error && " · " + errorText(run.error)}</p>
  </li>)}</ul>;
}

export function Overview() {
  const sources = useApi<Source[]>("/sources", true);
  const runs = useApi<Run[]>("/runs", true);
  const groups = useApi<GroupList>("/clusters", true);
  return <>
    <header className="dashboard-hero">
      <div className="hero-radar" aria-hidden="true">
        <svg viewBox="0 0 380 240" fill="none">
          <defs><pattern id="radar-grid" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M24 0H0v24" stroke="var(--signal-pink)" strokeOpacity=".18" /></pattern></defs>
          <path fill="url(#radar-grid)" d="M0 0h380v240H0z" />
          <g stroke="var(--signal-pink)" strokeOpacity=".5">
            <circle cx="228" cy="121" r="34" /><circle cx="228" cy="121" r="67" /><circle cx="228" cy="121" r="102" />
            <path d="M110 121h236M228 3v236" strokeDasharray="3 5" />
            <path d="m228 121 66-77m-66 77-61 28m61-28 64 32" />
          </g>
          <g fill="var(--signal-pink)"><circle cx="228" cy="121" r="5" /><circle cx="294" cy="44" r="4" /><circle cx="167" cy="149" r="4" /><circle cx="292" cy="153" r="4" /></g>
        </svg>
      </div>
      <div className="hero-content"><p className="eyebrow"><Icon name="radar" size={16} /> HABER RADARI</p>
        <h1>Genel görünüm</h1>
        <p>Haberlerin yayılımını, ortak metin bölümlerini ve kaynak bağlantılarını izleyin.</p>
        <a className="button hero-action" href="#/gruplar">Haber gruplarını incele <Icon name="arrow" size={16} /></a>
      </div>
    </header>
    <div className="metrics" aria-label="Çalışma alanı özeti">
      <Metric icon="rss" label="Aktif kaynaklar" value={sources.data?.filter(s => s.active && !s.demo).length} note="Örnek kaynaklar hariç" />
      <Metric icon="layers" label="Son haber grupları" value={groups.data?.items.length} note={groups.data?.more ? "Son 50 grup gösteriliyor" : "Örnek veri dahil"} />
      <Metric icon="activity" label="Bekleyen işler" value={runs.data?.filter(r => r.status === "queued" || r.status === "running").length} note="Son 50 iş içinde" />
    </div>
    <div className="overview-grid">
      <section className="panel"><div className="section-head"><h2>Son haber grupları</h2><a href="#/gruplar">Tüm gruplar ↗</a></div>
        <Result result={groups}>{data => <GroupRows groups={data.items.slice(0, 7)} />}</Result>
      </section>
      <section className="panel"><div className="section-head"><h2>Kaynak durumu</h2><a href="#/kaynaklar">Yönet ↗</a></div>
        <Result result={sources}>{items => items.length ? <ul className="records">{items.map(s => <li key={s.id} className="row-line">
          <strong className="source-name"><span className="source-icon"><Icon name="rss" size={15} /></span>{s.name}</strong><Badge tone={s.demo ? "amber" : s.active ? "green" : ""}>{s.demo ? "Örnek veri" : s.active ? "Aktif" : "Duraklatıldı"}</Badge>
        </li>)}</ul> : <Empty>Henüz kaynak eklenmedi.</Empty>}</Result>
      </section>
    </div>
    <section className="panel"><div className="section-head"><h2>Son toplama işleri</h2></div>
      <Result result={runs}>{items => <RunRows runs={items.slice(0, 8)} sources={sources.data ?? []} />}</Result>
    </section>
  </>;
}

function Metric({ icon, label, value, note }: { icon: "rss" | "layers" | "activity"; label: string; value?: number; note: string }) {
  return <div className="metric">
    <span className="metric-icon"><Icon name={icon} /></span>
    <div><p>{label}</p><strong>{value ?? "—"}</strong><small>{note}</small></div>
  </div>;
}

