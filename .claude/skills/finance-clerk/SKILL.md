---
name: finance-clerk
description: Keep the money of each legal entity in order — bank signals, invoices open and paid, payables, journals, receipts, month close — with certainty labels and never mixing entities. Use for daily items 7 to 11, weekly Part B, or "cash position", "who owes us", "what do we have to pay", "reconcile", "close the month".
---

# Money

Read `finance/AGENTS.md` first.

1. One legal entity at a time. Never a combined total, never a converted amount.
2. A bank movement becomes a journal line only with its proof: the bank message or statement is the `source`, the certainty is `proof` or `statement`.
3. Match a payment to an invoice by amount, currency, counterparty and reference. A partial match is not a match: say what differs.
4. A cost with no receipt is listed as a missing receipt, with who can supply it.
5. Month close per entity: journal complete, receipts gap listed, the tax return **prepared** for the person who files it, one report in `finance/reports/<yyyy>/<yyyy-mm>/`.
6. A tax or legal judgement is a question for the adviser, written as a question.
7. Never back-date, never fabricate, never remove a line.
