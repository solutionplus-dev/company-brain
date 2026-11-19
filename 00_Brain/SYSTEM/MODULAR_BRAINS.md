# Modular brains

One company, several brains. The core (this folder: finance and operations) stays private on the owner's computer. Other brains live in their own repositories so the people who work on them can have them without seeing the books.

| Brain | Where | Who has it | Scope in the store |
|---|---|---|---|
| Core: finance, operations, clients, meetings | this folder; no public remote | the owner | `finance`, `ops` |
| Go-to-market and sales | its own repository, linked at `Repos/<name>` | the team | `gtm` |
| Outreach | its own repository | the team | `outreach` |
| Design system and templates | its own repository | the team | `design`, `templates` |
| One per client project | its own repository, linked at `Repos/clients/<slug>` | the people on that project | `client:<slug>` |

Rules:

1. **Links, never copies.** A brain is reached through a link under `Repos/`. A copied brain is two brains by Friday.
2. **One home per fact across brains too.** The core owns billing entity, contracts, invoices, payments and profitability. A client brain owns scope, plan, deliverables, decisions and risks of that project. A code repository owns build facts.
3. **The core's routines are the scheduler.** Each linked brain keeps `schedules/daily.md` and `schedules/weekly.md`; the core's runs execute them and report.
4. **A linked brain decides for itself whether it may leave the computer.** It carries a `brain/DATA_HANDLING.md` with its data class and `sync: yes` or `sync: no`. The sync refuses a brain without that file, and any brain marked confidential or special-category.
5. **No client data in a template.** A template repository holds structure only.
