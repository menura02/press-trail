import { Icon } from "../components/Icon";
import "./home.css";

const steps = [
  { title: "Kaynaklarını ekle", detail: "RSS ve Atom yayınlarını izle. Yeni kayıtlar geldikçe yayın zamanını ve ilk görülme anını ayrı kaydet.", icon: "rss" },
  { title: "Haberleri karşılaştır", detail: "Benzer metinleri gruplar halinde incele. İki haberi yan yana aç ve ortak bölümleri gör.", icon: "layers" },
  { title: "Bağlantıları takip et", detail: "Metindeki kaynak bağlantılarını ve haberin sürüm geçmişini incele.", icon: "activity" },
] as const;

function OpenProduct({ className = "" }: { className?: string }) {
  return <a className={"launch-link " + className} href="#/uygulama">Uygulamayı aç <Icon name="arrow" size={17} /></a>;
}

export function Home() {
  return <div className="home">
    <a className="skip" href="#icerik">İçeriğe geç</a>
    <header className="home-header"><div className="home-shell home-bar">
      <a className="home-brand" href="#/" aria-label="PressTrail ana sayfası"><span className="brand-mark"><Icon name="radar" size={23} /></span> PressTrail</a>
      <div className="home-header-actions"><a className="home-process-link" href="#nasil-calisir">Nasıl çalışır?</a><OpenProduct /></div>
    </div></header>
    <main id="icerik" className="home-shell home-main" tabIndex={-1}>
      <section className="home-hero" aria-labelledby="home-title">
        <div className="home-copy">
          <p className="home-kicker"><span /> AÇIK KAYNAK ARAŞTIRMASI</p>
          <h1 id="home-title">Bir haberin<br />izini <em>sür.</em></h1>
          <p>Bir haber ne zaman yayımlandı? Benzer metinler hangi yayınlarda görüldü? PressTrail zamanları, metinleri ve kaynak bağlantılarını bir araya getirir.</p>
          <OpenProduct className="launch-primary" />
        </div>
        <figure className="signal-figure">
          <div className="signal-caption"><span><Icon name="radar" size={16} /> YAYILIM HARİTASI</span><span>ŞEMATİK</span></div>
          <svg viewBox="0 0 520 350" aria-hidden="true" fill="none">
            <defs><pattern id="home-grid" width="26" height="26" patternUnits="userSpaceOnUse"><path d="M26 0H0V26" stroke="white" opacity=".1" /></pattern></defs>
            <path d="M0 0h520v350H0z" fill="url(#home-grid)" />
            <g stroke="var(--signal-pink)" opacity=".68">
              <circle cx="245" cy="172" r="56" /><circle cx="245" cy="172" r="105" /><circle cx="245" cy="172" r="153" />
              <path d="M0 172h520M245 0v350" strokeDasharray="4 7" />
              <path d="m245 172 106-89m-106 89L91 198m154-26 131 75" strokeWidth="1.6" />
            </g>
            <circle cx="245" cy="172" r="17" fill="var(--signal-pink)" />
            <circle cx="245" cy="172" r="7" fill="var(--ink)" />
            <g fill="white"><circle cx="351" cy="83" r="5" /><circle cx="91" cy="198" r="5" /><circle cx="376" cy="247" r="5" /></g>
            <g fill="white" fontSize="12" fontFamily="monospace" letterSpacing="1"><text x="365" y="76">YAYIN</text><text x="31" y="222">METİN</text><text x="389" y="269">BAĞLANTI</text></g>
          </svg>
          <figcaption>Yayın zamanı, metin benzerliği ve açık bağlantı ayrı ayrı incelenir.</figcaption>
        </figure>
      </section>
      <section className="home-process" id="nasil-calisir" aria-labelledby="process-title">
        <div className="process-intro"><p className="home-kicker"><span /> İNCELEME AKIŞI</p><h2 id="process-title">Nasıl çalışır?</h2></div>
        <ol>{steps.map(({ title, detail, icon }, index) => <li key={title}>
          <span className="step-number">0{index + 1}</span><Icon name={icon} />
          <h3>{title}</h3><p>{detail}</p>
        </li>)}</ol>
      </section>
    </main>
    <footer className="home-shell home-footer"><strong>PressTrail</strong><span>Yerel haber araştırma alanı</span><OpenProduct /></footer>
  </div>;
}

