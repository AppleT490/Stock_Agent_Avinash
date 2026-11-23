"""Shared stock metadata and conservative price/news helpers."""
from datetime import datetime, timezone
import math
import yfinance as yf

CATEGORIES = {
    'NVDA':'AI (GPU Chips)', 'AMD':'AI (CPUs & GPUs)', 'AVGO':'AI Infrastructure (Semiconductors)',
    'SNDK':'Storage (Flash Memory)', 'MU':'AI Infrastructure (Memory Chips)',
    'OKLO':'Energy (Advanced Nuclear)', 'SMR':'Energy (Small Modular Reactors)',
    'LEU':'Energy (Nuclear Fuel)', 'UUUU':'Energy (Uranium)', 'BWXT':'Energy (Nuclear Technology)',
    'IREN':'AI Infrastructure (Data Centers)', 'CRWV':'AI Infrastructure (Cloud Computing)',
    'NBIS':'AI Infrastructure (Cloud Computing)', 'APLD':'AI Infrastructure (Data Centers)',
    'VRT':'AI Infrastructure (Power & Cooling)', 'AAOI':'AI Infrastructure (Optical Networking)',
    'ANET':'AI Infrastructure (Networking)', 'PENG':'AI Infrastructure (Memory & Computing)',
    'ORCL':'Software (Cloud & Databases)', 'GOOGL':'Technology (Search & Cloud)',
    'BABA':'Technology (E-commerce & Cloud)', 'PLTR':'AI (Data Analytics)',
    'SOUN':'AI (Voice Software)', 'NOW':'Software (Enterprise Automation)',
    'NET':'Cloud (Security & Networking)', 'PGY':'Fintech (Lending Technology)',
    'BE':'Energy (Fuel Cells)', 'GEV':'Energy (Power Equipment)',
    'VST':'Energy (Electricity Generation)', 'CEG':'Energy (Electricity & Nuclear)',
    'FLNC':'Energy (Battery Storage)', 'SERV':'Robotics (Autonomous Delivery)',
    'TER':'Robotics (Automation & Testing)', 'NTLA':'Biotechnology (Gene Editing)',
    'CRSP':'Biotechnology (Gene Editing)', 'BEAM':'Biotechnology (Gene Editing)',
    'BNTX':'Biotechnology (Immunotherapy)', 'VCYT':'Biotechnology (Diagnostics)',
    'PEPG':'Biotechnology (RNA Therapeutics)', 'CGEM':'Biotechnology (Oncology)',
    'QBTS':'Quantum Computing (Annealing)', 'QUBT':'Quantum Computing (Photonics)',
    'RKLB':'Space (Launch & Satellites)', 'UBER':'Technology (Mobility & Delivery)',
    'VST':'Energy (Electricity Generation)', 'CEG':'Energy (Nuclear & Electricity)',
}
ETF_CATEGORIES = {
    'VOO':'US Large-Cap', 'VXUS':'International Stocks', 'SMH':'Semiconductors',
    'ROBO':'Robotics', 'UFO':'Space', 'BUG':'Cybersecurity', 'XBI':'Biotechnology',
    'NLR':'Nuclear Energy', 'FIW':'Water', 'EPI':'India', 'WQTM':'Quantum Computing',
    'QTUM':'Quantum Computing', 'IYT':'Transportation'
}

def valid_ticker(t):
    return bool(t) and len(t) <= 15 and all(c.isalnum() or c in '.^-' for c in t)

def percent(current, previous):
    try:
        if previous is None or float(previous) <= 0: return None
        return round((float(current)/float(previous)-1)*100,2)
    except (TypeError,ValueError,ZeroDivisionError): return None

def num(v, digits=2):
    try:
        f=float(v)
        return round(f,digits) if math.isfinite(f) else None
    except (ValueError,TypeError): return None

def price_history(ticker, period='5y', interval='1d', prepost=False):
    return yf.Ticker(ticker).history(period=period,interval=interval,auto_adjust=True,prepost=prepost)

def history_return(close, start_date):
    """Return since first available close on/after start date, or None if insufficient history."""
    if close.empty: return None
    candidates=close[close.index.date >= start_date]
    if candidates.empty or close.index[0].date()>start_date: return None
    return percent(close.iloc[-1],candidates.iloc[0])

def recent_news(ticker, limit=5):
    """Only return links and titles actually supplied by the provider."""
    try: raw=yf.Ticker(ticker).news or []
    except Exception: return []
    result=[]
    for item in raw:
        content=item.get('content',item) or {}
        title=content.get('title')
        link=(content.get('canonicalUrl') or content.get('clickThroughUrl') or {})
        url=link.get('url') if isinstance(link,dict) else link
        if not url: url=content.get('link')
        if title and isinstance(url,str) and url.startswith('https://'):
            result.append({'title':title,'url':url,'published':content.get('pubDate') or ''})
        if len(result)>=limit:break
    return result

def price_drop_in_hour(ticker, now=None):
    """Compare most recent 5m bar with nearest available bar at/before 60 minutes ago.

    Refuse stale prices and long gaps; after-hours prices only if provider supplies bars.
    """
    import pandas as pd
    now=now or datetime.now(timezone.utc)
    hist=price_history(ticker,period='2d',interval='5m',prepost=True)
    if hist.empty or 'Close' not in hist:return None
    close=hist['Close'].dropna().sort_index()
    if close.empty:return None
    timestamps=close.index.tz_convert('UTC')
    latest=timestamps[-1]
    # Bars may be timestamped at the start of a five-minute period.
    if (pd.Timestamp(now)-latest).total_seconds()>15*60:return None
    target=latest-pd.Timedelta(minutes=60)
    candidates=close[timestamps<=target]
    if candidates.empty:return None
    baseline_ts=candidates.index[-1].tz_convert('UTC')
    if (target-baseline_ts).total_seconds()>10*60:return None
    last=num(close.iloc[-1],4); baseline=num(candidates.iloc[-1],4)
    change=percent(last,baseline)
    if change is None:return None
    return {'ticker':ticker,'price':last,'baseline':baseline,'change_pct':change,
            'as_of':latest.isoformat(),'baseline_as_of':baseline_ts.isoformat()}
