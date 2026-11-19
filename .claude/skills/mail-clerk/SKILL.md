---
name: mail-clerk
description: Read the company mailboxes for the daily run — invoices and receipts, registered-office post, authority and tax mail, client requests, replies owed, unsent drafts. Read-only; never sends, labels or moves. Use for daily items 1 to 6 or "what's in the mail", "do we owe a reply".
---

# Reading the mail

1. Every folder: inbox, sent, drafts, junk. Authority and tool notices often land in junk.
2. For each message that matters: id, sender (role), date and time, what it asks, by when, attachment names.
3. An attachment that is an invoice, receipt or letter is copied to its home with a `.digest.md`; the entity is the name printed on it.
4. A reply is "owed" when a message older than 24 hours has no answer in sent mail. A draft that was never sent is listed with what it says.
5. A message with a login link or a code: one line that it arrived; the link or code is never copied.
6. Never send, reply, label, move, mark as read or delete.
