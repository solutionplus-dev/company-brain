---
name: brain-query
description: Answer any question about the company (clients, money, meetings, decisions, documents, people, deadlines, today's priorities) from the brain, citing the file. Use for "what did we agree with", "when did", "how much", "where is", "who is", "what's the status of", "what should I do today".
---

# Answering from the brain

1. Search first: `scripts/brain ask "<question>"`; for dated or money facts `scripts/brain records kind=… company=…`.
2. Open the file the search returns and read the passage. The index finds; the file answers.
3. For a legal or finance fact, open the original, not its digest.
4. Answer with the path, the date of the source and a certainty label. Two sources that disagree: show both and add an `OP-` row; do not choose.
5. Not found is an answer: say what was searched and what would settle it. Never fill a gap from memory.
