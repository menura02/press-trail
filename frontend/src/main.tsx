import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { Heading } from "./components/common";
import { Icon } from "./components/Icon";
import { Overview } from "./pages/Overview";
import { Sources } from "./pages/Sources";
import { GroupPage, Groups } from "./pages/Groups";
import { ArticlePage, Compare } from "./pages/Article";
import { Home } from "./pages/Home";
import { DiffPage, FindingPage } from "./pages/Evolution";
import { Updates } from "./pages/Updates";
import "./style.css";

const routes = [
  ["uygulama", "Genel görünüm", "overview"],
  ["kaynaklar", "Kaynaklar", "rss"],
  ["gruplar", "Haber grupları", "layers"],
  ["takip", "Takip", "bell"],
] as const;

function App() {
  const [hash, setHash] = useState(location.hash.startsWith("#/") ? location.hash : "#/");
  useEffect(() => {
    function navigate() {
      if (location.hash && !location.hash.startsWith("#/")) return;
      setHash(location.hash || "#/");
      window.scrollTo(0, 0);
      requestAnimationFrame(() => document.getElementById("icerik")?.focus({ preventScroll: true }));
    }
    window.addEventListener("hashchange", navigate);
    return () => window.removeEventListener("hashchange", navigate);
  }, []);
  const [, page, id, right] = hash.slice(1).split("/");
  if (!page) return <Home />;
  const section = ["grup", "haber", "karsilastir", "fark", "bulgu"].includes(page) ? "gruplar" : page;
  const numeric = (value: string) => /^[1-9]\d{0,14}$/.test(value);
  let content = <Heading label="Sayfa" title="Sayfa bulunamadı"><a href="#/uygulama">Genel görünüme dön</a></Heading>;
  if (page === "uygulama") content = <Overview />;
  if (page === "kaynaklar") content = <Sources />;
  if (page === "gruplar") content = <Groups />;
  if (page === "grup" && numeric(id)) content = <GroupPage id={id} />;
  if (page === "haber" && numeric(id)) content = <ArticlePage id={id} version={numeric(right) ? right : undefined} />;
  if (page === "karsilastir" && numeric(id) && numeric(right)) content = <Compare left={id} right={right} />;
  if (page === "fark" && numeric(id)) content = <DiffPage id={id} />;
  if (page === "bulgu" && numeric(id)) content = <FindingPage id={id} />;
  if (page === "takip") content = <Updates />;

  return <div className="workspace">
    <a className="skip" href="#icerik">İçeriğe geç</a>
    <aside className="sidebar">
      <a className="brand" href="#/uygulama" aria-label="PressTrail genel görünümü">
        <span className="brand-mark"><Icon name="radar" size={24} /></span>
        <span><strong>PressTrail</strong><small>HABER İSTİHBARATI</small></span>
      </a>
      <span className="nav-caption">ÇALIŞMA ALANI</span>
      <nav aria-label="Ana menü">{routes.map(([path, name, icon]) => <a key={path} href={"#/" + path}
        aria-current={section === path ? "page" : undefined}><Icon name={icon} />{name}</a>)}</nav>
      <div className="sidebar-foot"><span className="local-dot" /> Yerel çalışma alanı</div>
    </aside>
    <div className="work-main">
      <header className="topbar"><div className="shell masthead">
        <div className="breadcrumb"><a href="#/">Ana sayfa</a><Icon name="chevron" size={13} /><strong>{routes.find(([path]) => path === section)?.[1] ?? "Sayfa"}</strong></div>
        <div className="timezone"><Icon name="globe" size={16} /> İstanbul saati</div>
      </div></header>
      <main id="icerik" className="shell" tabIndex={-1}>{content}</main>
      <footer className="shell footer flex flex-wrap justify-between gap-3"><span>PressTrail</span><span>Europe/Istanbul</span></footer>
    </div>
  </div>;
}
createRoot(document.getElementById("root")!).render(<App />);
