# System of records — one home per fact

Every kind of fact has exactly one owning file. Everything else links to it and never restates the value. When two files disagree, the owning file is right until evidence says otherwise, and the disagreement becomes an `OP-` row.

| Fact | Owning file | Who writes it |
|---|---|---|
| Who the company is; its legal entities | `brain.config.json` | the owner |
| What must happen on a date | `00_Brain/DEADLINES.md` | daily run adds; weekly run checks |
| What comes back every month, quarter, year | `finance/OBLIGATIONS.md` | weekly run; any run on evidence |
| Open actions | `00_Brain/OPEN_LOOPS.md` | any run adds; ticked only with evidence |
| What was decided | `00_Brain/DECISIONS.md` | the meeting procedure; the owner |
| What the brain advises | `00_Brain/RECOMMENDATIONS.md` | daily and weekly runs only |
| What the brain itself still has to do | `00_Brain/SYSTEM/BRAIN_TODO.md` | the weekday blocks of the daily run |
| Contradictions and decisions nobody may take alone | `00_Brain/OPEN_POINTS.md` | any run adds; weekly run closes on evidence |
| People and roles | `00_Brain/PEOPLE.md` | any run on evidence |
| Where each source is read | `00_Brain/SOURCES.md` | the owner |
| A client's billing entity, stage | `01_Clients/CLIENTS.json` | the owner's decision, entered by a run |
| A client's contract, scope, risks | `01_Clients/<slug>/CLIENT.md` | client procedure |
| A client's state today | `01_Clients/<slug>/STATUS.md` | daily run |
| That a meeting happened | `02_Meetings/registry.json` | meeting procedure |
| What was said in it | the meeting's `notes.md` (and `transcript.md`) | meeting procedure |
| Money that moved | `finance/ledger/<CODE>/journal_<yyyy>.csv` | finance procedure, with a source document per line |
| An invoice or receipt | the PDF under `Entity_<CODE>/` | filed by the daily run; never edited |
| The pipeline | `03_Sales/PIPELINE_NOW.md` | weekly run |
| Positioning, ideal customer, voice | `04_Marketing/BASE/` | the owner approves; runs draft |
| What runs when | `00_Brain/SCHEDULES/*.md` | the owner; the brain proposes |
| What each run did | `00_Brain/SCHEDULES/ROUTINE_LOG.md` | every run, append only |

A digest (`<name>.digest.md`) is a reading aid beside an original. It never owns a fact.
