"""Full production build: Quran + Sahihayn + package terminology -> FTS -> validate -> embeddings/FAISS.

Stops at the first failure. usage: python scripts/build_corpus.py
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STEPS = ["fetch_quran.py", "ingest_quran.py", "fetch_hadith.py", "ingest_sahihayn.py", "ingest_dictionary.py",
         "build_fts.py", "validate_corpus.py", "build_embeddings.py"]


def main() -> int:
    for step in STEPS:
        print(f"\n== {step}")
        r = subprocess.run([sys.executable, str(HERE / step)], cwd=HERE.parent, check=False)
        if r.returncode != 0:
            print(f"BUILD FAILED at {step}")
            return r.returncode
    print("\nBUILD OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
