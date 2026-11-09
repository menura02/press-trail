"""Bounded comparisons of the text actually captured by the collector."""
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher

METHOD = "paragraph-word/nfc-space-v1"
MAX_PARAGRAPHS = 500
MAX_TOKENS = 1200
TOKEN = re.compile(r"\d+(?:[.,]\d+)*|[^\W\d_]+|[^\s]", re.UNICODE)
PARAGRAPH = re.compile(r"\n\s*\n")
SENTENCE = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÇĞİÖŞÜ0-9“\"'])")
NUMBER = re.compile(
    r"(?<![\w])(?P<value>%?\s*\d+(?:[.,]\d+)*)(?:\s*(?P<unit>"
    r"yüzde|kişi|oy|lira|TL|dolar|euro|milyar|milyon|bin|km|metre|kg|ton|saat|dakika|gün|yıl|adet|%)(?!\w))?",
    re.IGNORECASE,
)
DATE = re.compile(
    r"(?<!\w)(?:\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}[./]\d{2,4}|"
    r"\d{1,2}\s+(?:Ocak|Şubat|Mart|Nisan|Mayıs|Haziran|Temmuz|Ağustos|Eylül|Ekim|Kasım|Aralık)"
    r"(?:\s+\d{4})?)(?!\w)", re.IGNORECASE,
)
QUOTATION = re.compile(r'“[^”\n]+”|"[^"\n]+"|«[^»\n]+»')


def compact(text):
    return " ".join(unicodedata.normalize("NFC", text).split())


def expressions(text):
    dates = list(DATE.finditer(text))
    numbers = []
    for match in NUMBER.finditer(text):
        start = match.start("value") + len(match["value"]) - len(match["value"].lstrip())
        if any(date.start() <= start < date.end() for date in dates):
            continue
        value = match["value"].strip()
        unit = match["unit"] or ("%" if value.startswith("%") else None)
        numbers.append({"raw": match.group().strip(), "value": value.lstrip("%").strip(), "unit": unit})
    return {"numbers": numbers, "dates": [m.group() for m in dates],
            "quotes": [m.group() for m in QUOTATION.finditer(text)]}


def changed_items(left, right):
    def unmatched(a, b):
        return list((Counter(a) - Counter(b)).elements())
    return {"removed": unmatched(left, right), "added": unmatched(right, left)}


def words(left, right):
    a, b = TOKEN.findall(compact(left)), TOKEN.findall(compact(right))
    truncated = max(len(a), len(b)) > MAX_TOKENS
    a, b = a[:MAX_TOKENS], b[:MAX_TOKENS]
    changes = []
    for op, i, j, k, l in SequenceMatcher(None, a, b).get_opcodes():
        if op != "equal":
            changes.append({"kind": op, "before": " ".join(a[i:j]), "after": " ".join(b[k:l])})
    return changes, truncated


def paragraph_change(left, right, left_index, right_index):
    change = {"before": left, "after": right, "before_index": left_index, "after_index": right_index}
    if not left or not right:
        return {**change, "kind": "removed" if left else "added"}
    word_changes, truncated = words(left, right)
    old = [compact(s) for s in SENTENCE.split(left)]
    new = [compact(s) for s in SENTENCE.split(right)]
    return {**change, "kind": "changed", "words": word_changes, "word_limit": truncated,
            "sentences": changed_items(old, new)}


def related(left, right):
    a, b = ({word for word in TOKEN.findall(value) if any(c.isalnum() for c in word)}
            for value in (left, right))
    return bool(a & b) and len(a & b) / min(len(a), len(b)) >= .25


def text_diff(left, right, *, match_all=False):
    if left == right:
        return None
    if compact(left) == compact(right):
        return {"format_only": True, "paragraphs": [], "truncated": False, "formatted": 0}
    original_a = [p.strip() for p in PARAGRAPH.split(left) if p.strip()]
    original_b = [p.strip() for p in PARAGRAPH.split(right) if p.strip()]
    raw_a, raw_b = original_a[:MAX_PARAGRAPHS], original_b[:MAX_PARAGRAPHS]
    a, b = list(map(compact, raw_a)), list(map(compact, raw_b))
    matching = SequenceMatcher(None, a, b, autojunk=False)
    aligned_a, aligned_b = set(), set()
    formatted = 0
    for i, j, length in matching.get_matching_blocks():
        aligned_a.update(range(i, i + length))
        aligned_b.update(range(j, j + length))
        formatted += sum(raw_a[i + n] != raw_b[j + n] for n in range(length))
    unmatched_b = {p: j for j, p in enumerate(b) if j not in aligned_b}
    unique_a, unique_b = Counter(a), Counter(b)
    moves = {i: unmatched_b[p] for i, p in enumerate(a) if i not in aligned_a
             and unique_a[p] == unique_b[p] == 1 and p in unmatched_b}
    moved_to = set(moves.values())
    formatted += sum(raw_a[i] != raw_b[j] for i, j in moves.items())
    changes = [{"kind": "moved", "before": raw_a[i], "after": raw_b[j],
                "before_index": i + 1, "after_index": j + 1} for i, j in moves.items()]
    for op, i, j, k, l in matching.get_opcodes():
        if op == "equal":
            continue
        deleted = [index for index in range(i, j) if index not in moves]
        added = [index for index in range(k, l) if index not in moved_to]
        for index in range(max(len(deleted), len(added))):
            x = deleted[index] if index < len(deleted) else None
            y = added[index] if index < len(added) else None
            if x is not None and y is not None and not match_all and not related(a[x], b[y]):
                changes.append(paragraph_change(raw_a[x], "", x + 1, None))
                changes.append(paragraph_change("", raw_b[y], None, y + 1))
            else:
                changes.append(paragraph_change(raw_a[x] if x is not None else "",
                                                raw_b[y] if y is not None else "",
                                                x + 1 if x is not None else None,
                                                y + 1 if y is not None else None))
    truncated = max(len(original_a), len(original_b)) > MAX_PARAGRAPHS
    return {"format_only": False, "paragraphs": changes, "truncated": truncated, "formatted": formatted}


def compare_versions(before, after, before_links, after_links):
    fields = {key: difference for key in ("title", "summary", "body")
              if (difference := text_diff(getattr(before, key), getattr(after, key), match_all=key == "title")) is not None}
    signals = {}
    for field in fields:
        left = expressions(getattr(before, field))
        right = expressions(getattr(after, field))
        signals[field] = {
            "numbers": changed_items([item["raw"] for item in left["numbers"]],
                                     [item["raw"] for item in right["numbers"]]),
            "dates": changed_items(left["dates"], right["dates"]),
            "quotes": changed_items(left["quotes"], right["quotes"]),
        }
    removed = sorted(set(before_links) - set(after_links))
    added = sorted(set(after_links) - set(before_links))
    return {"fields": fields, "signals": signals, "links": {"removed": removed, "added": added},
            "extractor_changed": before.extractor != after.extractor,
            "scope_changed": before.scope != after.scope,
            "content_changed": bool(removed or added or any(not f["format_only"] for f in fields.values()))}

