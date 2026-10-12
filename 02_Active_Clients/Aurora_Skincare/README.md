# Aurora Skincare — Reference Tenant (Fictional)

This is not a real client. It exists so a new buyer can see the whole
Growth Engine loop working end to end — folder shape, `.env` contract,
STRATEGY.md/CLAUDE.md format, and a real signal → brief → task handoff —
without having to invent all of it from a blank folder.

**What actually runs live, with zero credentials:**
- `content-engine` — fully functional today. It reads `content-idea` signals
  from `signals/` and drafts a brief + task into `02_Content/`. A sample
  signal is included in `signals/` so `python run_loop.py content-engine
  --client Aurora_Skincare` produces real output on first run.

**What needs real credentials to go live:**
- `ad-intel` — calls the live Google Ads API. Copy `.env.example` to `.env`
  and fill in real `GOOGLE_ADS_*` values (see that file for what each key
  is and where to get it) to make this tenant's ad-intel loop real instead
  of a placeholder.

**To clone this pattern for a real client:**
1. Copy this folder, rename it to the client's name (that name becomes
   their tenant slug everywhere — signals, tasks, logs).
2. Replace `STRATEGY.md` and `CLAUDE.md` with the real client's context.
3. Copy `.env.example` to `.env`, fill in their real platform credentials.
4. Delete the sample signal in `signals/` — it's demo data only.
