# Deploying the public demo (Streamlit Community Cloud)

The public app runs in **demo mode**:
- It shows *The Last Reel*, an original fictional 8-episode microdrama written for this project, with results from real pipeline, agent and story runs saved in `demo/studio_demo.db`.
- No confidential company data is in this repository, and none is uploaded.
- Processing jobs are turned off, and the copilot answers **offline** (rule-based, from the same data), so a public link can never use your AI quota.

Demo mode switches on automatically when there is no private database. That is always the case in the cloud.

## Steps (about 10 minutes)

1. **Make the public repository.** On GitHub, create a **new, empty, public** repo, for example `ai-promo-intelligence-studio`, with no README, licence or .gitignore. Then push the clean snapshot. It has a single commit and no history, so earlier private commits never become public:
   ```powershell
   git remote add public https://github.com/<you>/ai-promo-intelligence-studio.git
   git push public public-release:main
   ```
2. **Sign in** at https://share.streamlit.io with your GitHub account and allow access to the repo.
3. **Create the app:** click **Create app** → *Deploy a public app from GitHub*.
   - Repository: `<you>/ai-promo-intelligence-studio`, branch `main`
   - Main file path: `frontend/app.py`
   - App URL: choose a short name, e.g. `ai-promo-studio`
   - **Advanced settings → Python version: 3.12**
   - **Secrets: leave empty.** No API key is needed for the demo.
4. Click **Deploy**. The first build takes a few minutes. Then open the URL and check:
   - the intro plays
   - the top bar says *Public demo · fictional show*
   - the dashboard's 3D charts appear
5. Put the URL in your report.

## Notes

- **Sleeping app:** free apps sleep after a few days without visitors. The first visit wakes it in about 30 seconds.
- **Reviews and chats reset:** reviews and copilot chats made on the public app live in a temporary copy of the database. They reset when the app restarts.
- **Live AI on the public app (optional, not recommended):** add `GROQ_API_KEY` **and** `STUDIO_DEMO_ALLOW_AI = "true"` under *Secrets*. Anyone with the link could then spend your free daily quota.
- **Running the full studio locally** (with the private data in `data/` and `outputs/`):
  ```powershell
  .venv\Scripts\python -m streamlit run frontend\app.py
  ```
  To force demo mode locally: `$env:STUDIO_DEMO = "1"` before that command.
- **Rebuilding the demo:** run `python demo/make_demo_show.py`, then `python src/run.py --input demo/scripts/the_last_reel`, then rebuild `demo/studio_demo.db` with `studio_cli` (`import`, `agents`, `story`) and `STUDIO_DB=demo/studio_demo.db`.
