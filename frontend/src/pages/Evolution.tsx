import { useState, type FormEvent, type SyntheticEvent } from "react";
import { Badge, dateTime, Empty, External, Heading, Reported, Result, scopeText } from "../components/common";
import { Feedback, fieldText, NotesPanel, Pager, ResearchPanel, ReviewControl, usePaged, useResearchAction } from "../components/ResearchCommon";
import { useApi } from "../hooks/useApi";
import { api, json } from "../services/api";
import type { Changes, Field, Finding, ParagraphDiff, VersionDiff, VersionEvidence } from "../researchTypes";
import type { ArticleDetail, Version } from "../types";

export function VersionPicker({ article }: { article: ArticleDetail }) {
  const [before, setBefore] = useState(article.versions[1]?.id ?? article.versions[0].id);
  const [after, setAfter] = useState(article.versions[0].id);
  const action = useResearchAction();

  function compare(event: FormEvent) {
    event.preventDefault();
    void action.run(async () => {
      const result = await api<{ id: number }>("/articles/" + article.id + "/diffs",
        json("POST", { before_id: before, after_id: after }));
      location.hash = "#/fark/" + result.id;
    }, "");
  }

  return <ResearchPanel title="Sürümleri karşılaştır">
    {article.versions.length < 2 ? <Empty>Karşılaştırma için iki toplanmış sürüm gerekir.</Empty> :
      <div className="form"><form className="research-form" onSubmit={compare}>
        <div className="compare-grid">
          {([[before, setBefore, "İlk sürüm"], [after, setAfter, "İkinci sürüm"]] as const).map(([value, update, label]) =>
            <label key={label}>{label}<select value={value} onChange={e => update(Number(e.target.value))}>
              {article.versions.map(v => <option key={v.id} value={v.id}>#{v.id} · {dateTime(v.collected_at)}</option>)}
            </select></label>)}
        </div>
        <button className="primary" disabled={before === after || action.busy}>Sürüm farklarını aç</button>
      </form><Feedback value={action.feedback} /></div>}
  </ResearchPanel>;
}

const changeLabels = { added: "Eklendi", removed: "Kaldırıldı", changed: "Değişti", moved: "Taşındı" };
const diffPending = (diff: VersionDiff) => !diff.completed_at;

function SourceVersion({ version, label }: { version: VersionEvidence; label: string }) {
  return <div className="research-evidence">
    <strong>{label} · <a href={"#/haber/" + version.article_id + "/" + version.id}>Sürüm #{version.id}</a></strong>
    <p>{version.title}</p>
    <small>Toplama · {dateTime(version.collected_at)}</small>
    <small>Bildirilen yayın · <Reported value={version.published} raw={version.published_raw} state={version.published_state} /></small>
    <small>{scopeText(version)} · {version.extractor}</small>
  </div>;
}

function Delta({ label, values, links = false }: { label: string; values: Changes<string>; links?: boolean }) {
  if (!values.added.length && !values.removed.length) return null;
  return <div className="research-stack"><strong>{label}</strong>
    {([["removed", "Kaldırıldı"], ["added", "Eklendi"]] as const).map(([key, title]) =>
      values[key].length > 0 && <div key={key}>
        <Badge tone={key === "added" ? "amber" : ""}>{title}</Badge>
        <ul className="research-delta-list">{values[key].map((value, index) =>
          <li key={index}>{links ? <External url={value}>{value}</External> : value}</li>)}</ul>
      </div>)}
  </div>;
}

function Paragraph({ change, field }: { change: ParagraphDiff; field: Field }) {
  return <div className="diff-item">
    <div><Badge tone={change.kind === "added" ? "amber" : ""}>{changeLabels[change.kind]}</Badge></div>
    <div className="compare-grid">
      {([["before", "Önce", change.before_index], ["after", "Sonra", change.after_index]] as const).map(([key, label, index]) =>
        <div className={"diff-side " + key} key={key}>
          <strong>{label}{field === "body" && index !== null ? " · Paragraf " + index : ""}</strong>
          <p>{change[key] || "—"}</p>
        </div>)}
    </div>
    {change.words && change.words.length > 0 && <details><summary>Kelime farklarını göster</summary>
      <ul className="diff-tokens">{change.words.map((word, index) => <li key={index}>
        {word.before && <span>Kaldırıldı <del>{word.before}</del> </span>}
        {word.after && <span>Eklendi <ins>{word.after}</ins></span>}
      </li>)}</ul>
      {change.word_limit && <p className="muted">Kelime karşılaştırması ilk 1.200 belirteçle sınırlı.</p>}
    </details>}
    {change.sentences && <details><summary>Cümle farklarını göster</summary><Delta label="Cümleler" values={change.sentences} /></details>}
  </div>;
}

export function DiffPage({ id }: { id: string }) {
  const result = useApi<VersionDiff>("/diffs/" + id, diffPending);
  return <Result result={result}>{diff => <>
    <a className="back" href={"#/haber/" + diff.article_id}>← Haber detayına dön</a>
    <Heading label={"EVRİM / " + diff.id} title="Sürüm farkları">
      <p>{diff.result?.content_changed ? "Bu iki kontrol arasında değişti. Kesin değişiklik anı bilinmiyor." :
        "Karşılaştırma, seçilen iki toplama kaydına dayanır."}</p>
    </Heading>
    <ResearchPanel title="Kaynak sürümleri"><div className="form compare-grid">
      <SourceVersion version={diff.before} label="Önceki kayıt" /><SourceVersion version={diff.after} label="Sonraki kayıt" />
    </div></ResearchPanel>
    {diff.result ? <DiffResults diff={diff.result} method={diff.method} /> :
      <p className="notice" role="status">Fark analizi sırada. Toplama işçisi tamamladığında burada görünecek.</p>}
    <NotesPanel kind="diff" id={diff.id} title="Sürüm farkı notları" />
  </>}</Result>;
}

function DiffResults({ diff, method }: { diff: NonNullable<VersionDiff["result"]>; method: string }) {
  return <>
    <p className="notice">Analiz yöntemi · {method}
      {(diff.extractor_changed || diff.scope_changed) && <><br /><strong>Toplama koşulları farklı.</strong> Çıkarıcı veya kapsam değişikliği metin farklarını etkileyebilir.</>}
    </p>
    {!Object.keys(diff.fields).length && !diff.links.added.length && !diff.links.removed.length &&
      <Empty>Kaydedilmiş metinde ve bağlantılarda fark yok.</Empty>}
    {(Object.entries(diff.fields) as [Field, NonNullable<VersionDiff["result"]>["fields"][Field]][]).map(([field, details]) => {
      const signals = diff.signals[field];
      if (!details) return null;
      return <ResearchPanel key={field} title={fieldText[field]}>
        <div className="form">
          {details.format_only && <p><Badge>Yalnızca boşluk / biçim farkı</Badge></p>}
          {details.formatted > 0 && <p className="muted">{details.formatted} eşleşen paragrafta boşluk / biçim farkı var.</p>}
          {details.truncated && <p className="muted">Paragraf incelemesi her sürümün ilk 500 paragrafıyla sınırlı.</p>}
          {details.paragraphs.map((change, index) => <Paragraph key={index} change={change} field={field} />)}
          {signals && !details.format_only && <div className="research-stack">
            <Delta label="Sayısal ifadeler" values={signals.numbers} />
            <Delta label="Tarihler" values={signals.dates} />
            <Delta label="Alıntılar" values={signals.quotes} />
          </div>}
        </div>
      </ResearchPanel>;
    })}
    <ResearchPanel title="Kaynak bağlantısı farkları"><div className="form">
      {diff.links.added.length || diff.links.removed.length ? <Delta label="Bağlantılar" values={diff.links} links /> : <p className="muted">Eklenen veya kaldırılan bağlantı yok.</p>}
    </div></ResearchPanel>
  </>;
}

function sourceIndex(value: string, offset: number) {
  let rawOffset = offset;
  for (const match of value.matchAll(/\r\n/g)) {
    if (match.index >= rawOffset) break;
    rawOffset++;
  }
  return rawOffset;
}

function ManualFinding({ version, onSaved }: { version: Version; onSaved: () => void }) {
  const [field, setField] = useState<Field>(version.body ? "body" : version.summary ? "summary" : "title");
  const [selection, setSelection] = useState<{ start: number; end: number; quote: string }>();
  const action = useResearchAction();
  const value = version[field] ?? "";

  function capture(event: SyntheticEvent<HTMLTextAreaElement>) {
    const input = event.currentTarget;
    const from = sourceIndex(value, input.selectionStart);
    const to = sourceIndex(value, input.selectionEnd);
    const quote = value.slice(from, to);
    if (quote.trim()) {
      const start = Array.from(value.slice(0, from)).length;
      setSelection({ start, end: start + Array.from(quote).length, quote });
    } else {
      setSelection(undefined);
    }
  }

  return <form className="research-form" onSubmit={e => {
    e.preventDefault();
    if (selection) void action.run(async () => {
      await api("/versions/" + version.id + "/findings", json("POST", { field, ...selection }));
      onSaved();
    }, "İddia adayı kaydedildi.");
  }}>
    <label>Alıntı alanı<select value={field} onChange={e => { setField(e.target.value as Field); setSelection(undefined); }}>
      {(Object.keys(fieldText) as Field[]).filter(key => version[key]).map(key =>
        <option value={key} key={key}>{fieldText[key]}</option>)}</select></label>
    <label>Kaynak metninden cümle seçin
      <textarea readOnly rows={4} value={value} onSelect={capture} />
    </label>
    {selection && <blockquote className="source-quote">{selection.quote}</blockquote>}
    {selection && Array.from(selection.quote).length > 2400 && <p className="muted">Alıntıyı 2.400 karaktere kısaltın.</p>}
    <button className="primary" disabled={!selection || Array.from(selection.quote).length > 2400 || action.busy}>Seçimi iddia adayı olarak kaydet</button>
    <Feedback value={action.feedback} />
  </form>;
}

export function FindingEvidence({ item, context = false }: { item: Finding; context?: boolean }) {
  const { numbers, dates, quotes } = item.signals;
  return <div className="research-evidence">
    <div className="row-line"><strong>{item.source}</strong>
      <Badge tone={item.demo ? "amber" : ""}>{item.demo ? "Kurgusal örnek" : item.kind === "claim" ? "İddia adayı" : "Düzeltme / güncelleme adayı"}</Badge></div>
    <blockquote className="source-quote">{item.quote}</blockquote>
    <small><a href={"#/haber/" + item.version.article_id + "/" + item.version.id}>Kaynak sürüm #{item.version.id}</a>
      {" · "}<External url={item.url}>Yayın adresi</External>{" · "}{dateTime(item.version.collected_at)}</small>
    <small>Bildirilen yayın · <Reported value={item.version.published} raw={item.version.published_raw} state={item.version.published_state} /></small>
    <small>{fieldText[item.field]} · Karakter {item.start}–{item.end} · {item.method.startsWith("manual") ? "Elle seçildi" : "Otomatik öneri"} · {item.method}</small>
    {numbers.length > 0 && <p>Sayı / birim · {numbers.map(n => n.raw).join(" · ")}</p>}
    {dates.length > 0 && <p>Tarih · {dates.join(" · ")}</p>}
    {quotes.length > 0 && <p>Alıntı · {quotes.join(" · ")}</p>}
    {context && <details><summary>Kaynak bağlamı</summary><p className="body-text">{item.context}</p></details>}
  </div>;
}

export function VersionFindings({ version }: { version: Version }) {
  const result = usePaged<Finding>("/versions/" + version.id + "/findings", true);
  return <ResearchPanel title="İddia ve düzeltme adayları">
    <div className="form">
      <p className="muted">Otomatik bulgular inceleme adayıdır. Kaynak metninden kendi alıntınızı da seçebilirsiniz.</p>
      <details className="research-details"><summary>Elle iddia adayı seç</summary>
        <ManualFinding version={version} onSaved={result.reload} />
      </details>
    </div>
    <Result result={result}>{data => data.items.length ? <ul className="records">{data.items.map(item => <li key={item.id}>
      <FindingEvidence item={item} context />
      <ReviewControl status={item.status} path={"/findings/" + item.id + "/review"} onSaved={result.reload} />
      <a href={"#/bulgu/" + item.id}>Adayı aç ve not ekle</a>
    </li>)}</ul> : <Empty>Bu sürümde henüz aday bulunmuyor. Yeni sürümler işçi tarafından taranır.</Empty>}</Result>
    <Pager {...result} />
  </ResearchPanel>;
}

export function FindingPage({ id }: { id: string }) {
  const result = useApi<Finding>("/findings/" + id);
  return <Result result={result}>{item => <>
    <a className="back" href={"#/haber/" + item.version.article_id + "/" + item.version.id}>← Kaynak sürüme dön</a>
    <Heading label={"BULGU / " + item.id} title={item.kind === "claim" ? "İddia adayı" : "Düzeltme / güncelleme adayı"}>
      <p>İnceleme kararı adayın araştırmada kullanımını kaydeder.</p>
    </Heading>
    <ResearchPanel title="Kaynaktaki alıntı"><div className="form">
      <FindingEvidence item={item} context />
      <ReviewControl status={item.status} path={"/findings/" + item.id + "/review"} onSaved={result.reload} />
    </div></ResearchPanel>
    <NotesPanel kind="finding" id={item.id} title="Adaya ilişkin araştırmacı notları" />
  </>}</Result>;
}

