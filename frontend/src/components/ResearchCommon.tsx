import { useId, useRef, useState, type FormEvent, type ReactNode } from "react";
import { api, json } from "../services/api";
import { useApi } from "../hooks/useApi";
import type { Field, Note, NoteKind, NoteStatus, Page, Review, WatchKind } from "../researchTypes";
import { Badge, dateTime, Empty, Result } from "./common";
import "./research.css";

const PAGE_SIZE = 10;
export const fieldText: Record<Field, string> = { title: "Başlık", summary: "Özet", body: "Haber metni" };
export const reviewText: Record<Review, string> = { pending: "İnceleme bekliyor", confirmed: "Onaylandı", rejected: "Reddedildi" };
const noteStates: Record<NoteStatus, string> = { open: "Açık", reviewed: "İncelendi", resolved: "Tamamlandı" };

export function usePaged<T>(path: string, poll = false) {
  const [offset, setOffset] = useState(0);
  const result = useApi<Page<T>>(path + (path.includes("?") ? "&" : "?") + "limit=" + PAGE_SIZE + "&offset=" + offset, poll);
  return { ...result, offset, previous: () => setOffset(Math.max(0, offset - PAGE_SIZE)), next: () => setOffset(offset + PAGE_SIZE) };
}

export function Pager({ data, offset, previous, next }: {
  data?: { more: boolean }; offset: number; previous: () => void; next: () => void;
}) {
  if (!offset && !data?.more) return null;
  return <div className="actions research-pagination">
    <button type="button" disabled={!offset} onClick={previous}>Önceki</button>
    <span className="muted">Sayfa {offset / PAGE_SIZE + 1}</span>
    <button type="button" disabled={!data?.more} onClick={next}>Sonraki</button>
  </div>;
}

export function useResearchAction() {
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ text: string; error: boolean }>();
  async function run(task: () => Promise<void>, message = "Kaydedildi.") {
    setBusy(true);
    setFeedback(undefined);
    try {
      await task();
      if (message) setFeedback({ text: message, error: false });
    } catch (error) {
      setFeedback({ text: (error as Error).message, error: true });
    } finally {
      setBusy(false);
    }
  }
  return { busy, feedback, run };
}

export function Feedback({ value }: { value?: { text: string; error: boolean } }) {
  return value ? <p className={"notice research-feedback " + (value.error ? "alert" : "")}
    role={value.error ? "alert" : "status"}>{value.text}</p> : null;
}

export function ResearchPanel({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  const heading = useId();
  return <section className="panel research-panel" aria-labelledby={heading}>
    <div className="section-head"><h2 id={heading}>{title}</h2>{action}</div>
    {children}
  </section>;
}

export function WatchToggle({ kind, id }: { kind: WatchKind; id: number }) {
  const path = "/watch/" + kind + "/" + id;
  const result = useApi<{ watching: boolean }>(path);
  const action = useResearchAction();
  return <div className="watch-control">
    <Result result={result}>{value => <button type="button" className="watch-button"
      disabled={action.busy} aria-pressed={value.watching} onClick={() => void action.run(async () => {
        await api(path, json("PUT", { watching: !value.watching }));
        result.reload();
      }, value.watching ? "Takip bırakıldı." : "Takip listesine eklendi.")}>
      {value.watching ? "Takibi bırak" : "Takip et"}
    </button>}</Result>
    <Feedback value={action.feedback} />
  </div>;
}

export function ReviewControl({ status, path, onSaved }: { status: Review; path: string; onSaved: () => void }) {
  const action = useResearchAction();
  return <>
    <div className="actions review-control"><Badge tone={status === "pending" ? "amber" : ""}>{reviewText[status]}</Badge>
      {(Object.keys(reviewText) as Review[]).filter(next => next !== status).map(next =>
        <button type="button" key={next} disabled={action.busy} onClick={() => void action.run(async () => {
          await api(path, json("PUT", { status: next }));
          onSaved();
        }, "İnceleme kararı kaydedildi.")}>
          {{ confirmed: "Onayla", rejected: "Reddet", pending: "İncelemeye geri al" }[next]}
        </button>)}
    </div>
    <Feedback value={action.feedback} />
  </>;
}

export function NotesPanel({ kind, id, title = "Araştırmacı notları" }: { kind: NoteKind; id: number; title?: string }) {
  const path = "/annotations/" + kind + "/" + id;
  const result = usePaged<Note>(path);
  const action = useResearchAction();
  const [editing, setEditing] = useState<Note>();
  const [deleting, setDeleting] = useState<number>();
  const [text, setText] = useState("");
  const [tags, setTags] = useState("");
  const [status, setStatus] = useState<NoteStatus>("open");
  const noteInput = useRef<HTMLTextAreaElement>(null);

  function select(note?: Note) {
    setEditing(note);
    setText(note?.text ?? "");
    setTags(note?.tags.join(", ") ?? "");
    setStatus(note?.status ?? "open");
    if (note) noteInput.current?.focus();
  }

  function save(event: FormEvent) {
    event.preventDefault();
    void action.run(async () => {
      const payload = { text, tags: tags.split(",").map(t => t.trim()).filter(Boolean), status };
      await api(editing ? "/annotations/" + editing.id : path, json(editing ? "PUT" : "POST", payload));
      select();
      result.reload();
    }, "Araştırmacı notu kaydedildi.");
  }

  return <ResearchPanel title={title}>
    <div className="form">
      <p className="muted">Kendi yorum ve gözlemleriniz bu bölümde saklanır.</p>
      <form className="research-form" onSubmit={save}>
        <label>{editing ? "Notu düzenle" : "Yeni araştırmacı notu"}
          <textarea ref={noteInput} value={text} maxLength={10000} required rows={3} onChange={e => setText(e.target.value)} /></label>
        <div className="compare-grid">
          <label>Etiketler (virgülle ayırın)<input value={tags} maxLength={500} onChange={e => setTags(e.target.value)} /></label>
          <label>Not durumu<select value={status} onChange={e => setStatus(e.target.value as NoteStatus)}>
            {Object.entries(noteStates).map(([key, value]) => <option key={key} value={key}>{value}</option>)}</select></label>
        </div>
        <div className="actions"><button className="primary" disabled={action.busy}>Notu kaydet</button>
          {editing && <button type="button" onClick={() => select()}>Düzenlemeyi bırak</button>}</div>
      </form>
      <Feedback value={action.feedback} />
    </div>
    <Result result={result}>{data => data.items.length ? <ul className="records">{data.items.map(note => <li key={note.id}>
      <div className="row-line"><Badge>{noteStates[note.status]}</Badge><small>Oluşturma {dateTime(note.created_at)} · Son düzenleme {dateTime(note.updated_at)}</small></div>
      <p className="body-text">{note.text}</p>
      {note.tags.length > 0 && <p className="research-tags">{note.tags.map(tag => <Badge key={tag}>{tag}</Badge>)}</p>}
      <div className="actions">
        <button type="button" onClick={() => select(note)}>Düzenle</button>
        {deleting === note.id ? <>
          <button type="button" disabled={action.busy} onClick={() => void action.run(async () => {
            await api<void>("/annotations/" + note.id, { method: "DELETE" });
            if (editing?.id === note.id) select();
            setDeleting(undefined);
            result.reload();
          }, "Not silindi.")}>Notu silmeyi onayla</button>
          <button type="button" onClick={() => setDeleting(undefined)}>Vazgeç</button>
        </> : <button type="button" onClick={() => setDeleting(note.id)}>Sil</button>}
      </div>
    </li>)}</ul> : <Empty>Bu kayda henüz not eklenmedi.</Empty>}</Result>
    <Pager {...result} />
  </ResearchPanel>;
}

