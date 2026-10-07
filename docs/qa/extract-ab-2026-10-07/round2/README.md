# Round 2: section context (spec 0005, slice 1)

The same 40 questions were asked again through the same v2 answer pipeline version after the backend began sending each chunk's section path to the answer model. In these files, arm `v1` is the round 1 v2 answer and arm `v2` is the round 2 answer; `blind_key.json` maps X/Y to them.

Correctness labels were given blind: all 80 answers are correct or correctly declined. "Supported" was judged with one rule for both rounds: the cited chunk, plus its section path only when that path was sent to the model, contains the question's subject and value.

| Category | Round 1 supported | Round 2 supported |
|---|---|---|
| C3 headings | 0/6 | 6/6 |
| All answerable | 24/34 | 30/34 |

The four remaining unsupported answers are q04 (chunk boundary) and q10–q12 (a table header that does not carry onto page 2). Both are listed as out of scope in spec 0005. Round 2 generation cost: $0.0248.
