import { useState } from "react";
import { Badge, dateTime, Empty, Heading, Result } from "../components/common";
import { Feedback, Pager, ResearchPanel, usePaged, useResearchAction, WatchToggle } from "../components/ResearchCommon";
import { api, json } from "../services/api";
import type { Notification, WatchItem } from "../researchTypes";

const eventLabels = { group_join: "Gruba haber eklendi", version_changed: "Toplanan içerik değişti", correction: "Düzeltme / güncelleme adayı" };

function NotificationList({ unread }: { unread: boolean }) {
  const result = usePaged<Notification>("/notifications?unread=" + unread, true);
  const action = useResearchAction();
  return <>
    <Feedback value={action.feedback} />
    <Result result={result}>{data => data.items.length ? <ul className="records">{data.items.map(item => {
      const href = item.diff_id ? "#/fark/" + item.diff_id : item.finding_id ? "#/bulgu/" + item.finding_id :
        "#/haber/" + item.article_id + "/" + item.version_id;
      return <li key={item.id}>
        <div className="row-line"><strong>{eventLabels[item.kind]}</strong>
          <Badge tone={item.read_at ? "" : "amber"}>{item.read_at ? "Okundu" : "Okunmadı"}</Badge></div>
        <p><a href={href}>{item.title || "İlgili bulguyu aç"}</a></p>
        {item.cluster_id && <small>Olay anındaki grup · <a href={"#/grup/" + item.cluster_id}>{item.cluster_title || "Grup #" + item.cluster_id}</a></small>}
        <small>{dateTime(item.created_at)}</small>
        <div className="actions"><button type="button" disabled={action.busy} onClick={() => void action.run(async () => {
          await api("/notifications/" + item.id, json("PUT", { read: !item.read_at }));
          result.reload();
        }, "")}>{item.read_at ? "Okunmadı olarak işaretle" : "Okundu olarak işaretle"}</button></div>
      </li>;
    })}</ul> : <Empty>{unread ? "Okunmamış bildirim yok." : "Henüz bildirim yok."}</Empty>}</Result>
    <Pager {...result} />
  </>;
}

export function Updates() {
  const [unread, setUnread] = useState(false);
  const watches = usePaged<WatchItem>("/watch", true);
  return <>
    <Heading label="05 / TAKİP" title="Takip ve bildirimler">
      <p>Takip ettiğiniz haber ve gruplardaki yeni gözlemleri inceleyin.</p>
    </Heading>
    <ResearchPanel title="Bildirimler" action={<label className="check"><input type="checkbox" checked={unread}
      onChange={e => setUnread(e.target.checked)} /> Yalnızca okunmamışlar</label>}>
      <NotificationList key={String(unread)} unread={unread} />
    </ResearchPanel>
    <ResearchPanel title="Takip listesi">
      <Result result={watches}>{data => data.items.length ? <ul className="records">{data.items.map(item => <li key={item.id}>
        <div className="row-line"><a href={(item.target_kind === "cluster" ? "#/grup/" : "#/haber/") + item.target_id}>
          {item.title || "Kayıt #" + item.target_id}</a><WatchToggle kind={item.target_kind} id={item.target_id} /></div>
        <small>{item.target_kind === "cluster" ? "Haber grubu" : "Haber"} · {dateTime(item.created_at)}</small>
      </li>)}</ul> : <Empty>Bir haber veya grup sayfasından takibe başlayabilirsiniz.</Empty>}</Result>
      <Pager {...watches} />
    </ResearchPanel>
  </>;
}

