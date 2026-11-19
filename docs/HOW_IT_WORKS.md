# How it works

## The problem

A small company's knowledge is spread over mailboxes, a bank, an invoicing tool, a notetaker, a downloads folder and somebody's head. An AI assistant can do single tasks well, and then forgets. Nothing checks every day whether an invoice arrived, a client asked for something, or a tax date is nine days away.

## The idea

Put the company's memory in plain files, give every kind of fact one home, and have an agent run the same two checklists on a schedule: one every evening, one every Monday. The agent reads the sources, files what arrived, updates the registers, and writes the owner one page for the next morning.

## Five things that make it hold

**1. Routines are files.** `00_Brain/SCHEDULES/daily.md` is the whole daily routine. You can read what the agent will do, change it in a text editor, and see when it changed. The scheduler's prompt is one sentence.

**2. An answer sheet.** Every evening ends with twelve questions answered Yes, No or Not read: did an invoice arrive, was one paid, do we owe a reply, is a deadline close, which sources were not read. It takes ten seconds to read and it is the same every day.

**3. Honest gaps.** If the mail connector was signed out, the answer to "did an invoice arrive" is "not read", not "no". If an amount is not on a document, it is `unknown`. Every figure carries its source and a certainty label.

**4. Legal entities kept apart.** If you have more than one company, no line, sum or currency column ever holds two. The code enforces it where it can; the rules cover the rest.

**5. It maintains and improves itself, on approval.** The daily run ends with one block of work on itself, a different one each weekday. Tuesday it evaluates: which sources it failed to read, which questions it could not answer, where the owner corrected it, and whether its own search finds the right file for a list of standing questions. Wednesday it enriches: digests for new documents, one knowledge note, the stalest client file. Thursday it cleans up: folds closed months into rollups, prepares register rollovers, lists loose files. Friday it audits itself. Saturday it "dreams": reads the whole week and writes down patterns, wrong notes, unclear rules and routine changes. Sunday it turns all of that into at most five proposals with the exact change. The owner answers yes or no; Monday it applies the yeses, and the next Tuesday's score shows whether the change worked. Nothing is deleted, and no rule changes without a written yes.

## What a day looks like

As pictures: `docs/DIAGRAMS.md`, diagrams 2 (a day), 3 (the daily run) and 9 (the week the brain spends on itself).

Evening: the run tests its sources, reads the mail in every folder, matches bank messages to invoices, files the day's meetings, ranks deadlines, files new downloads, writes the daily log and `TODO.md`, refreshes the index, and appends one entry to the routine log.

Morning: the owner opens `TODO.md`. At most seven actions, the costliest first, each with the reason and the file.

## What the agent may not do

Send, reply, pay, submit anything to an authority, post, delete. It drafts, puts documents in their place and reports. People act.

## Modular

Finance and operations stay in this private folder. A go-to-market brain, an outreach brain or a client project brain can live in its own repository and be linked under `Repos/`; the core's routines run theirs. See `00_Brain/SYSTEM/MODULAR_BRAINS.md`.
