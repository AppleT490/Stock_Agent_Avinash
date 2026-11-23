# Stock Intelligence Dashboard

## Deploy online
1. Create a GitHub repository and upload `app.py` and `requirements.txt` to its root.
2. Open https://share.streamlit.io and sign in with GitHub.
3. Select **Create app** > **Yup, I have an app**, choose the repository, main branch and `app.py`.
4. Click Deploy. Your dashboard receives a `streamlit.app` URL.

## Run locally (optional)
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Notes
- Yahoo Finance via yfinance is an unofficial data source, suitable for prototyping, not guaranteed for production or commercial redistribution.
- Data can be delayed, missing or inaccurate. Verify with issuer filings and a licensed data provider before making investment decisions.
- Watchlist state is session-only in this MVP. Persistence, validated earnings dates and news ingestion are planned improvements.
