import { useState, type FormEvent } from "react";
import { Badge, dateTime, Empty, External, Heading, Result } from "../components/common";
import { useApi } from "../hooks/useApi";
import { api, json } from "../services/api";
import type { Run, Source, SourceInput } from "../types";
import { RunRows } from "./Overview";

const initial: SourceInput = { name: "", url: "", language: "tr", interval_minutes: 60, full_text: false, active: true };
const inputFrom = ({ name, url, language, interval_minutes, full_text, active }: Source): SourceInput =>
  ({ name, url, language, interval_minutes, full_text, active });

export function Sources() {
  const sources = useApi<Source[]>("/sources", true);
  const runs = useApi<Run[]>("/runs", true);
  const [editing, setEditing] = useState<number | null>(null);
  const [form, setForm] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error?: boolean }>();
  const change = <K extends keyof SourceInput>(key: K, value: SourceInput[K]) => setForm(f => ({ ...f, [key]: value }));

  async function action(work: () => Promise<unknown>, success: string) {
    setBusy(true);
    setMessage(undefined);
    try { await work(); setMessage({ text: success }); sources.reload(); runs.reload(); }
    catch (error) { setMessage({ text: (error as Error).message, error: true }); }
    finally { setBusy(false); }
  }

  function save(event: FormEvent) {
    event.preventDefault();
    void action(async () => {
      await api<Source>(editing ? "/sources/" + editing : "/sources", json(editing ? "PUT" : "POST", form));
      setEditing(null);
      setForm(initial);
    }, "Kaynak kaydedildi.");
  }

  return <>
    <Heading label="02 / Toplama" title="Kaynaklar"><p>RSS ve Atom adreslerini, kontrol aralığını ve toplama kapsamını yönetin.</p></Heading>
    {message && <p className={"notice " + (message.error ? "alert" : "")} role={message.error ? "alert" : "status"}>{message.text}</p>}
    <div className="overview-grid">
      <section className="panel">
        <div className="section-head"><h2>Kayıtlı yayınlar</h2></div>
        <Result result={sources}>{items => items.length ? <ul className="records">{items.map(s => <li key={s.id}>
          <div className="row-line"><strong>{s.name}</strong><Badge tone={s.demo ? "amber" : s.active ? "green" : ""}>{s.demo ? "Örnek veri" : s.active ? "Aktif" : "Duraklatıldı"}</Badge></div>
          <small><External url={s.url}>{s.url}</External></small>
          <p>{s.interval_minutes} dk · {s.full_text ? "Tam metin denensin" : "Başlık / özet"}
            {s.active && !s.demo && " · Sonraki kontrol " + dateTime(s.next_check)}</p>
          {!s.demo && <div className="actions">
            <button disabled={busy} onClick={() => { setEditing(s.id); setForm(inputFrom(s)); document.getElementById("source-name")?.focus(); }}>Düzenle</button>
            <button disabled={busy} onClick={() => void action(() => api("/sources/" + s.id,
              json("PUT", { ...inputFrom(s), active: !s.active })), s.active ? "Kaynak duraklatıldı." : "Kaynak etkinleştirildi.")}>{s.active ? "Duraklat" : "Etkinleştir"}</button>
            <button className="primary" disabled={busy || !s.active} onClick={() => void action(() => api("/sources/" + s.id + "/runs",
              { method: "POST" }), "Toplama işi sıraya alındı.")}>Şimdi kontrol et</button>
          </div>}
        </li>)}</ul> : <Empty>İlk kaynağı ekleyerek başlayın.</Empty>}</Result>
      </section>
      <section className="panel">
        <div className="section-head"><h2>{editing ? "Kaynağı düzenle" : "Kaynak ekle"}</h2></div>
        <form className="form" onSubmit={save}>
          <label>Yayın adı<input id="source-name" required maxLength={120} value={form.name} onChange={e => change("name", e.target.value)} /></label>
          <label>RSS / Atom adresi<input type="url" required maxLength={1600} value={form.url} placeholder="https://ornek.org/rss.xml" onChange={e => change("url", e.target.value)} /></label>
          <label>Kontrol aralığı (dakika)<input type="number" min={5} max={1440} required value={form.interval_minutes || ""} onChange={e => change("interval_minutes", Number(e.target.value))} /></label>
          <label className="check"><input type="checkbox" checked={form.full_text} onChange={e => change("full_text", e.target.checked)} /> Erişilebilen sayfalardan tam metin al</label>
          <div className="actions"><button disabled={busy} className="primary">Kaydet</button>{editing && <button type="button" onClick={() => { setEditing(null); setForm(initial); }}>Vazgeç</button>}</div>
        </form>
      </section>
    </div>
    <section className="panel"><div className="section-head"><h2>Toplama geçmişi</h2></div>
      <Result result={runs}>{items => <RunRows runs={items} sources={sources.data ?? []} />}</Result>
    </section>
  </>;
}
