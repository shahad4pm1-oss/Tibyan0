# Corpus coverage (2026-10-02)

Corpus version `c2-quran-hafs2.0u13+sahihayn-openiti-44e1c36+sp-dict-1448` (updated 2026-10-02 correction pass). Counts are from `scripts/validate_corpus.py` on the built database (all checks V01–V16 pass). **Full official coverage is NOT achieved**: see the blockers below and `OFFICIAL_SOURCE_INVENTORY.md`.

**Integrated:** Quran; Sahih al-Bukhari; Sahih Muslim (with documented gaps). **Not integrated:** Dorar Tafsir, Dorar Aqeedah, Dorar Fiqh, Dorar History, Dorar Hadith API verification, Bayyinat, the full Jamhara dictionary, general dawa.center content, general islamic-content.com content, other Sunnah collections.

| Source category | Official source | Records acquired | Records validated | Records indexed | Production status | Blocker if incomplete |
|---|---|---|---|---|---|---|
| Quran | KFGQPC Hafs v2.0 (via Quranpedia) | 6,236 ayat | 6,236 | 6,236 (`passages_fts`, LSA/FAISS) | PRODUCTION_ACTIVE | — (translations not added) |
| Hadith | Sahih al-Bukhari (approved by the package); data path OpenITI (Shamela 1681 file) | 7,380 numbered entries (7,389 numbers incl. shared) | 7,380 | 7,380 (`hadith_fts`) | LIMITED_PRODUCTION | Cross-check vs Shamela/Dorar PENDING; edition reuse PENDING VERIFICATION; 174 of 7,563 numbers not separate entries in the file |
| Hadith | Sahih Muslim (approved by the package); data path OpenITI (Shamela 1727 file) | 3,114 records = 2,922 numbered + 192 narrations unnumbered in the file | 3,114 | 3,114 (`hadith_fts`) | LIMITED_PRODUCTION | Same PENDING items; 111 of 3,033 numbers absent; unnumbered narrations cited by book + chapter with `hadith_number = null` (no invented numbers) |
| Hadith verification | Dorar Hadith | 0 | 0 | 0 | — | BLOCKED_BY_ACCESS |
| Tafsir | Dorar Tafseer | 0 | 0 | 0 | — | BLOCKED_BY_ACCESS |
| Aqeedah | Dorar Aqeeda | 0 | 0 | 0 | — | BLOCKED_BY_ACCESS |
| Fiqh | Dorar Feqhia | 0 | 0 | 0 | — | BLOCKED_BY_ACCESS |
| Seerah / history | Dorar History | 0 | 0 | 0 | — | BLOCKED_BY_ACCESS |
| Shubuhat | Bayyinat (dawa.center/file/7937) | 0 | 0 | 0 | — | BLOCKED_BY_ACCESS; terms «all rights reserved» (PENDING_REVIEW) |
| Terminology | Official Scientific Package Sample Glossary (p.8) | records = 10 (Arabic → English) | 10 | not a passage index | **NOT USED** since 2026-10-04 (still written to the `terms` table by the build; never looked up or shown) | The full terminology database (Jamhara) is not integrated |
| Terminology | Jamhara dictionary (islamic-content.com) | 0 | 0 | 0 | — | BLOCKED_BY_ACCESS, BLOCKED_BY_TERMS |
| Da'wah content | dawa.center, islamic-content.com | 0 | 0 | 0 | — | BLOCKED_BY_ACCESS, BLOCKED_BY_TERMS |

Totals: 16,730 passages (6,236 Quran + 10,494 hadith). Active source types: `quran`, `hadith`. (The `dictionary` source and its 10 terms remain in the database, unused.)

Hadith search status: **LIMITED_PRODUCTION** (only verbatim matches are attributed; the UI shows a limitation note on every hadith result). Claim analysis (LLM) is enabled for Quran results only. Hadith results show text, source, number, book, chapter and the package grading rule, with no claim verdict.
