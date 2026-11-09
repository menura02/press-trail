"""Idempotent synthetic examples. This command performs no HTTP requests."""
from sqlalchemy import select

from .analysis import analysis_lock
from .collectors import Entry
from .db import Session
from .models import Article, Source
from .worker import store

WATER = ("Kurgusal Ardıç ilçesinde belediye, yağışların ardından barajın doluluk oranının "
         "yüzde kırk sekize ulaştığını açıkladı. Ölçümler salı sabahı tamamlandı. "
         "Su yönetimi ekibi hafta sonuna kadar günlük ölçüm yayımlayacak.")
WATER_UPDATED = WATER + "\n\nGüncelleme: 13 Mayıs 2025 tarihli ek ölçümde doluluk %49 olarak açıklandı."
MARKET = ("Kurgusal İncir mahallesinde üretici pazarı pazar günü istasyon meydanına taşınıyor. "
          "Yerel üreticiler meyve ve sebze tezgâhlarını sabah sekizde açacak.")


def seed():
    with Session.begin() as db:
        analysis_lock(db)
        examples = [
            ("Ardıç Bülteni · Örnek", "ardic.example.invalid", "baraj", "Ardıç barajında su seviyesi yükseldi",
             "2025-05-13T09:15:00+03:00", WATER),
            ("Vadi Notları · Örnek", "vadi.example.invalid", "olcum", "Ardıç barajında yeni su seviyesi ölçümü",
             "2025-05-13T10:05:00+03:00", WATER),
            ("İncir Postası · Örnek", "incir.example.invalid", "pazar", "Üretici pazarı istasyon meydanına taşınıyor",
             "2025-05-13 11:00:00", MARKET),
        ]
        for name, host, slug, title, published, body in examples:
            base = f"https://{host}"
            feed_url = base + "/rss.xml"
            source = db.scalar(select(Source).where(Source.url == feed_url))
            if source is None:
                source = Source(name=name, url=feed_url, demo=True, active=False)
                db.add(source)
                db.flush()
            if not source.demo or db.scalar(select(Article.id).where(Article.source_id == source.id).limit(1)):
                continue
            url = base + "/" + slug
            entry = Entry(url, slug, title, body.split(". ")[0] + ".", published, None)
            links = []
            if slug == "olcum":
                links = [{"url": "https://ardic.example.invalid/baraj", "text": "Kaynak",
                          "context": "İlk ölçüm bültenine bağlantı.", "kind": "explicit"}]
            store(db, source, entry, body, links)
            if slug == "baraj":
                entry.updated_raw = "2025-05-13T11:20:00+03:00"
                store(db, source, entry, WATER_UPDATED, links)
    print("Kurgusal örnek veri hazır.")


if __name__ == "__main__":
    seed()

