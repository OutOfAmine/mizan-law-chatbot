"""Downloads the 3 official PDFs (adala.justice.gov.ma) into ../data/raw, the folder ingest.py reads."""
import urllib.request
from pathlib import Path

from ingest import DOCS, RAW

RAW.mkdir(parents=True, exist_ok=True)
for doc in DOCS:
    out = RAW / doc["file"]
    if out.exists():
        print("already here:", out.name)
        continue
    print("downloading", out.name, "...")
    urllib.request.urlretrieve(doc["url"], out)
print("done:", RAW)
