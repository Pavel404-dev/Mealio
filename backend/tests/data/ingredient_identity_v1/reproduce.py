"""Reproduce frozen reference corpus, with Python 3.12 / UCD 15; no DB/network.

Usage: python backend/tests/data/ingredient_identity_v1/reproduce.py
Verifies committed corpus bytes; never overwrites fixtures or production SQL.
"""

import gzip
import hashlib
import json
import random
import unicodedata as u
from pathlib import Path

ROOT = Path(__file__).resolve().parent
assert u.unidata_version == "15.0.0"
metadata = json.loads((ROOT / "sources.json").read_text())
sources = {}
for name, meta in metadata.items():
    raw = gzip.decompress((ROOT / (name + ".txt.gz")).read_bytes())
    assert hashlib.sha256(raw).hexdigest() == meta["sha256"]
    sources[name] = raw.decode()


def chars(s):
    return "".join(chr(int(cp, 16)) for cp in s.split())


def data(name):
    result = {}
    start = None
    for line in sources[name].splitlines():
        fields = line.split(";")
        cp = int(fields[0], 16)
        value = (fields[2], int(fields[3]), fields[5])
        if fields[1].endswith(", First>"):
            start = cp
        elif fields[1].endswith(", Last>"):
            result.update((i, value) for i in range(start, cp + 1))
            start = None
        else:
            result[cp] = value
    return result


fold = {}
for line in sources["CaseFolding15"].splitlines():
    fields = line.split("#")[0].strip().split(";")
    if len(fields) > 2 and fields[1].strip() in ("C", "F"):
        fold[chars(fields[0])] = chars(fields[2])
w = "".join(chr(i) for i in range(0x110000) if chr(i).isspace())
d15, d16 = data("UnicodeData15"), data("UnicodeData16")
corpus = set(
    [
        "",
        "Straße",
        "STRASSE",
        "İ",
        "i\u0307",
        "I",
        "ı",
        "Σςσ",
        "\u13a0\uab70",
        "\ufb03",
        "МОЛОКО",
        "ЇЖА",
        "ĽUĽOK",
        "Café",
        "Cafe\u0301",
        "100%",
        "under_score",
        "a\\b",
        "a-b",
        "ab",
        w,
        " Chicken" + w + "Breast ",
        "\u1100\u1161\u11a8",
        "\U00010d69\u0323",
        "a\U00010d69\u0323",
        "\ue000\u0301",
        "\uffff",
        "\U0010ffff",
    ]
)
corpus.update(fold)
corpus.update(fold.values())
for version in ("15", "16"):
    for line in sources["NormalizationTest" + version].splitlines():
        line = line.split("#")[0].strip()
        if line and not line.startswith("@"):
            corpus.update(chars(x) for x in line.split(";")[:5])
new = [
    cp
    for cp, v in d16.items()
    if cp not in d15 and (v[1] or (v[2] and not v[2].startswith("<")))
]
for cp in new:
    for left in ("", "a", "\u03b1", "\u1100", "\u0323"):
        for right in ("", "\u0323", "\u0301\u0323", "\u1161", "\U00010d69\u0315"):
            corpus.add(left + chr(cp) + right)
for c in w + "\u200b\ufeff\u180e":
    corpus.update([c, "a" + c + "b", c + "A" + c])
rng = random.Random(20520261023)
pool = (
    list(fold)
    + list(w)
    + list(map(chr, range(0x300, 0x370)))
    + list(map(chr, new))
    + ["a", "%", "_", "\\"]
)
for _ in range(5000):
    corpus.add("".join(rng.choices(pool, k=rng.randint(1, 40))))
corpus.add("\U0001d160" * 255)
assert len(corpus) == 45070
extra = [
    "A" * 600,
    "\U0001d160" * 600,
    "\u0100",
    "\u0200",
    "\U00100000",
    "\U00100000\u0100",
    "A\u0100",
    None,
]
lines = []
for i, s in enumerate(sorted(corpus) + extra):
    n = None if s is None else u.normalize("NFC", s)
    k = None if s is None else u.normalize("NFC", " ".join(n.split()).casefold())
    e = None if k is None else "".join(f"{ord(c):021b}" for c in k)
    lines.append(
        json.dumps(
            dict(i=i, s=s, n=n, k=k, e=e), ensure_ascii=True, separators=(",", ":")
        )
        + "\n"
    )
raw = "".join(lines).encode()
assert raw == gzip.decompress((ROOT / "corpus.jsonl.gz").read_bytes())
print(
    json.dumps(
        {
            "vectors": len(lines),
            "unicode": u.unidata_version,
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    )
)
