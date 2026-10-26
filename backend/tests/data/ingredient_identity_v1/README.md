# Unicode identity reference inputs

Copyright Unicode, Inc. Unicode data use is governed by
`backend/app/db/ddl/Unicode-LICENSE.txt`; source URLs and SHA256 values are in
`sources.json`. Inputs are gzip-compressed with mtime=0, without edits.

`corpus.jsonl.gz` contains the independently generated Python UCD15 reference
NFC/key/21-bit outputs, 45078 vectors. Uncompressed SHA256:
`97ede630ec9c6324f866a731cd311d693dcf437ac5ac42a1cffa66560a1013b9`.
It was carried from the hash-verified final SQL prototype. `reproduce.py`
reconstructs it exactly from the included official inputs, with deterministic
seed 20520261023; it does not import app configuration, connect or modify files.
Unicode16 cases are interpreted under the frozen Unicode15 policy, including
previously unassigned characters, rather than expecting native Unicode16 NFC.
Production does not import these test data or use Python casefold for identity.
