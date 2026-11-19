# Sources — where the routines read

The daily run tests every row before it starts. An empty row means that source is reported as **not read**. No password, key or token is ever written here: only which tool or folder, and how to test it.

| Source | Tool or path | Cheap test | Used for |
|---|---|---|---|
| Company mailbox(es) | | | invoices, authority mail, client requests, replies owed |
| Bank notifications, per entity | | | money in and out |
| Invoicing tool, per entity | | | invoices, expenses |
| Bookkeeping tool, per entity | | | journals, tax returns |
| Meeting notetaker | | | meetings |
| Local recordings | | | meetings |
| Calendar | | | tomorrow and the next seven days |
| Downloads folder | | | receipts, scans, bank files |
| Ticket system | | | client promises |
| Shared store | `python3 tools/index/supabase_sync.py --verify` | counts only | the shared copy |

**Never read:** *(list here the mailboxes, labels and folders that are private or belong to someone else)*
