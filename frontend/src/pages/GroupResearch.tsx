import { useState, type FormEvent } from "react";
import { Badge, Empty, Result } from "../components/common";
import { Feedback, Pager, ResearchPanel, ReviewControl, usePaged, useResearchAction } from "../components/ResearchCommon";
import { api, downloadHtml, json } from "../services/api";
import type { ClaimPair, DiffOption, Finding } from "../researchTypes";
import { FindingEvidence } from "./Evolution";

function ClaimTable({ items, saved = false }: { items: Finding[]; saved?: boolean }) {
  return <table className="claim-table">
    <caption className="sr-only">İki kaynak iddiasının yan yana karşılaştırması</caption>
    <thead><tr><th scope="col">İlk kaynak</th><th scope="col">İkinci kaynak</th></tr></thead>
    <tbody><tr>{items.map(item => <td key={item.id}>
      <FindingEvidence item={item} context={saved} />
      {saved && <a href={"#/bulgu/" + item.id}>Adayı ve notlarını aç</a>}
    </td>)}</tr></tbody>
  </table>;
}

export function GroupClaims({ id }: { id: number }) {
  const claims = usePaged<Finding>("/clusters/" + id + "/claims");
  const pairs = usePaged<ClaimPair>("/clusters/" + id + "/claim-comparisons");
  const [selected, setSelected] = useState<Finding[]>([]);
  const action = useResearchAction();
  const distinct = selected.length === 2 && selected[0].version.article_id !== selected[1].version.article_id;
  return <ResearchPanel title="İddia karşılaştırma">
    <div className="form">
      <p className="muted">Farklı yayınlardan iki aday seçin. Sayılar farklı tarihleri veya kapsamları anlatabilir. Eşleştirme, birlikte inceleme kararıdır.</p>
      {selected.length > 0 && <div className="actions" aria-label="Seçili adaylar">{selected.map(item =>
        <button type="button" key={item.id} onClick={() => setSelected(list => list.filter(x => x.id !== item.id))}>
          #{item.id} · {item.source} ×
        </button>)}</div>}
      {selected.length === 2 && <ClaimTable items={selected} />}
      {selected.length === 2 && !distinct && <p className="muted">İki farklı haberden aday seçin.</p>}
      <div className="actions"><button type="button" className="primary" disabled={!distinct || action.busy}
        onClick={() => void action.run(async () => {
          await api("/clusters/" + id + "/claim-comparisons", json("POST", { left_id: selected[0].id, right_id: selected[1].id }));
          setSelected([]);
          pairs.reload();
        }, "Aday eşleştirmesi kaydedildi.")}>Eşleştirme oluştur</button></div>
      <Feedback value={action.feedback} />
      <details className="research-details"><summary>Eşleştirmek için aday seç</summary>
        <Result result={claims}>{data => data.items.length ? <ul className="records">{data.items.map(item => {
          const checked = selected.some(x => x.id === item.id);
          return <li key={item.id}>
            <label className="check claim-choice"><input type="checkbox" checked={checked} disabled={selected.length === 2 && !checked}
              onChange={e => setSelected(e.target.checked ? [...selected, item] : selected.filter(x => x.id !== item.id))} />
              <span>#{item.id} · {item.source} · {item.quote}</span>
            </label>
            <a href={"#/bulgu/" + item.id}>Kaynağı ve adayı aç</a>
          </li>;
        })}</ul> : <Empty>Bu grubun üye haberlerinde henüz iddia adayı yok.</Empty>}</Result>
        <Pager {...claims} />
      </details>
    </div>
    <Result result={pairs}>{data => data.items.length ? <div className="claim-compare">{data.items.map(pair =>
      <article className="claim-pair" key={pair.id}>
        <div className="row-line"><strong>Eşleştirme #{pair.id}</strong>
          <Badge>{pair.method.startsWith("manual") ? "Araştırmacı oluşturdu" : "Otomatik eşleştirme önerisi"}</Badge></div>
        {!pair.current_group && <p className="notice">Üyelik sonradan değişti. Bu kayıt, eşleştirmenin yapıldığı grupta saklanıyor.</p>}
        <ClaimTable items={[pair.left, pair.right]} saved />
        <ReviewControl status={pair.status} path={"/claim-comparisons/" + pair.id + "/review"} onSaved={pairs.reload} />
      </article>)}</div> : <Empty>Kaydedilmiş eşleştirme yok.</Empty>}</Result>
    <Pager {...pairs} />
  </ResearchPanel>;
}

function ReportFindings({ id, kind, selected, onToggle }: {
  id: number; kind: "claim" | "correction"; selected: number[]; onToggle: (value: number) => void;
}) {
  const result = usePaged<Finding>("/clusters/" + id + "/claims?kind=" + kind);
  return <details className="research-details">
    <summary>{kind === "claim" ? "İddia alıntılarını seç" : "Düzeltme / güncelleme alıntılarını seç"}</summary>
    <Result result={result}>{data => data.items.length ? <ul className="records">{data.items.map(item =>
      <li key={item.id}><label className="check claim-choice"><input type="checkbox" checked={selected.includes(item.id)}
        disabled={selected.length >= 20 && !selected.includes(item.id)} onChange={() => onToggle(item.id)} />
        <span>#{item.id} · {item.source} · {item.quote}</span></label></li>)}</ul> : <Empty>Seçilebilecek aday yok.</Empty>}</Result>
    <Pager {...result} />
  </details>;
}

function toggled(ids: number[], id: number) {
  return ids.includes(id) ? ids.filter(x => x !== id) : [...ids, id];
}

export function ReportPanel({ id }: { id: number }) {
  const diffs = usePaged<DiffOption>("/clusters/" + id + "/diffs");
  const [findingIds, setFindingIds] = useState<number[]>([]);
  const [diffIds, setDiffIds] = useState<number[]>([]);
  const [recent, setRecent] = useState(true);
  const [notes, setNotes] = useState(true);
  const action = useResearchAction();

  function exportReport(event: FormEvent) {
    event.preventDefault();
    void action.run(() => downloadHtml("/clusters/" + id + "/report", {
      finding_ids: findingIds, diff_ids: diffIds, recent_diffs: recent, include_notes: notes,
    }, "iz-surucusu-grup-" + id + ".html"), "HTML indirmesi başlatıldı.");
  }

  return <ResearchPanel title="HTML araştırma raporu">
    <div className="form">
      <p className="muted">Rapor grup üyelerini, kaynak bağlantılarını ve gözlem zamanlarını içerir. Eklemek istediğiniz fark ve alıntıları seçin.</p>
      <form className="research-form" onSubmit={exportReport}>
        <fieldset className="report-selection"><legend>Rapor kapsamı</legend>
          <label className="check"><input type="checkbox" checked={recent} onChange={e => setRecent(e.target.checked)} /> Son 10 tamamlanan farkı dahil et</label>
          <label className="check"><input type="checkbox" checked={notes} onChange={e => setNotes(e.target.checked)} /> Kapsamdaki araştırmacı notlarını dahil et</label>
        </fieldset>
        <ReportFindings id={id} kind="claim" selected={findingIds} onToggle={key => setFindingIds(list => toggled(list, key))} />
        <ReportFindings id={id} kind="correction" selected={findingIds} onToggle={key => setFindingIds(list => toggled(list, key))} />
        <details className="research-details"><summary>Belirli sürüm farklarını seç</summary>
          <Result result={diffs}>{data => data.items.length ? <ul className="records">{data.items.map(item =>
            <li key={item.id}><label className="check claim-choice">
              <input type="checkbox" checked={diffIds.includes(item.id)} disabled={diffIds.length >= 20 && !diffIds.includes(item.id)}
                onChange={() => setDiffIds(list => toggled(list, item.id))} />
              <span>{item.title} · #{item.before_id} → #{item.after_id}</span>
            </label><a href={"#/fark/" + item.id}>Farkı aç</a></li>)}</ul> : <Empty>Tamamlanmış fark yok.</Empty>}</Result>
          <Pager {...diffs} />
        </details>
        <p className="muted">{findingIds.length} alıntı · {diffIds.length} fark seçildi</p>
        <button className="primary" disabled={action.busy}>HTML raporunu indir</button>
      </form>
      <Feedback value={action.feedback} />
    </div>
  </ResearchPanel>;
}

