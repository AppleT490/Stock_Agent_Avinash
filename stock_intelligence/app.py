"""EquityLens: research dashboard, not a trading system."""
import json
import re
import requests
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path
from datetime import date, timedelta, datetime, timezone
import pandas as pd
import streamlit as st
import yfinance as yf
from market_data import CATEGORIES, ETF_CATEGORIES, num, percent, price_history, history_return, recent_news, valid_ticker, price_drop_in_hour

HERE=Path(__file__).resolve().parent
CONFIG=json.loads((HERE/'config.json').read_text())
st.set_page_config(page_title='EquityLens',layout='wide',page_icon='📈')
st.title('EquityLens')
st.caption('Beyond the Price. Understand the Business. · v1.4')
st.caption('Research only. Prices, fundamentals and news may be delayed or unavailable; no trading advice.')
if 'tickers' not in st.session_state:st.session_state.tickers=CONFIG['tickers'][:50].copy()

with st.sidebar:
    st.header('Stock watchlist (max 50)')
    new=st.text_input('Add ticker',placeholder='e.g. AVGO').strip().upper()
    if st.button('Add ticker'):
        if not valid_ticker(new):st.warning('Enter a valid ticker')
        elif new in st.session_state.tickers:st.warning('Already added')
        elif len(st.session_state.tickers)>=50:st.warning('Maximum 50')
        elif new in ETF_CATEGORIES:st.warning('ETF tracking is coming later; add stocks here')
        else:st.session_state.tickers.append(new);st.rerun()
    st.write(f'{len(st.session_state.tickers)} / 50')
    rem=st.selectbox('Remove ticker',['—']+st.session_state.tickers)
    if st.button('Remove selected') and rem!='—':st.session_state.tickers.remove(rem);st.rerun()
    st.download_button('Export watchlist',pd.DataFrame({'Ticker':st.session_state.tickers}).to_csv(index=False),'watchlist.csv','text/csv')
    st.info('Watchlist changes last only for this session. No email notifications or email credentials are used.')

@st.cache_data(ttl=3600,show_spinner=False)
def stock_data(t):
    r={'Ticker':t,'Company':t,'Category':CATEGORIES.get(t,'Unclassified')}
    try:
        obj=yf.Ticker(t)
        hist=price_history(t,period='5y')
        info=obj.info or {}
        r['Company']=info.get('shortName') or info.get('longName') or t
        r['Category']=CATEGORIES.get(t) or info.get('industry') or info.get('sector') or 'Unclassified'
        close=hist['Close'].dropna() if not hist.empty else pd.Series(dtype=float)
        if not close.empty:
            latest=float(close.iloc[-1]);r['Price']=num(latest)
            r['1W %']=percent(latest,close.iloc[-6]) if len(close)>5 else None
            r['1M %']=percent(latest,close.iloc[-22]) if len(close)>21 else None
            r['YTD %']=history_return(close,date(close.index[-1].year,1,1))
            r['3Y %']=history_return(close,close.index[-1].date()-timedelta(days=365*3))
            r['1D %']=percent(latest,close.iloc[-2]) if len(close)>1 else None
            r['As of']=str(close.index[-1].date())
        r.update({'P/E':num(info.get('trailingPE')),'Forward P/E':num(info.get('forwardPE')),
            'P/S':num(info.get('priceToSalesTrailing12Months')),
            'Revenue (TTM)':num(info.get('totalRevenue'),0),
            'Revenue Growth YoY %':num(info.get('revenueGrowth')*100) if isinstance(info.get('revenueGrowth'),(float,int)) else None,
            'Market Cap':num(info.get('marketCap'),0),'Free Cash Flow':num(info.get('freeCashflow'),0),
            'Cash':num(info.get('totalCash'),0),'Debt':num(info.get('totalDebt'),0),
            '52W High':num(info.get('fiftyTwoWeekHigh')),'52W Low':num(info.get('fiftyTwoWeekLow')),
            'Currency':info.get('currency','')})
        r['_loaded']=bool(len(close))
    except Exception:r['_loaded']=False
    return r

def compact_amount(value):
    """Display large amounts without changing their underlying numeric values."""
    if value is None or pd.isna(value):
        return 'N/A'
    try:
        value = float(value)
    except (ValueError, TypeError):
        return 'N/A'
    for threshold, suffix in ((1e12, 'T'), (1e9, 'B'), (1e6, 'M'), (1e3, 'K')):
        if abs(value) >= threshold:
            return f'{value / threshold:,.2f}{suffix}'
    return f'{value:,.2f}'

if st.button('Refresh data'):st.cache_data.clear();st.rerun()
important,stocks,etfs=st.tabs(['🚨 Important','📊 Stocks','🧺 ETFs (Coming Soon)'])

@st.cache_data(ttl=300, show_spinner=False)
def scan_price_alert(ticker):
    try:
        return price_drop_in_hour(ticker)
    except Exception:
        return None

@st.cache_data(ttl=3600, show_spinner=False)
def next_earnings_date(ticker):
    try:
        cal=yf.Ticker(ticker).calendar
        if not isinstance(cal,dict):
            return None
        dates=cal.get('Earnings Date') or cal.get('EarningsDate')
        if not dates:
            return None
        if not isinstance(dates,(list,tuple)):
            dates=[dates]
        for d in dates:
            parsed=pd.to_datetime(d,errors='coerce')
            if pd.notna(parsed):
                day=parsed.date()
                if day>=date.today():
                    return day
    except Exception:
        pass
    return None

# News classifications are keyword-based leads for review, NOT verified events or price predictions.
NEWS_RULES = [
    ('Mixed', 'High', ('ceo reinstat', 'reinstated as ceo', 'returns as ceo', 'returns as nvidia ceo', 'ceo returns', 'ceo is back', 'ceo resign', 'ceo step', 'ceo fired', 'chief executive resign', 'chief executive reinstat', 'ceo departure', 'appoints new ceo', 'ceo ousted', 'ceo replacement', 'ceo change')),
    ('Negative', 'High', ('fraud', 'scam', 'accounting irregularit', 'sec investigation', 'criminal investigation', 'bankrupt', 'chapter 11', 'restatement', 'class action', 'data breach', 'cyberattack', 'indict', 'subpoena', 'sanction', 'contract cancell', 'project cancell', 'regulatory rejection')),
    ('Financial', 'High', ('share offering', 'public offering', 'stock offering', 'dilution', 'convertible notes', 'going concern', 'liquidity crisis', 'guidance cut', 'cuts guidance', 'revenue miss', 'earnings miss', 'debt default', 'capital raise')),
    ('Positive', 'High', ('major contract', 'multibillion', 'billion-dollar deal', 'regulatory approval', 'fda approval', 'wins contract', 'signs contract', 'new partnership', 'strategic partnership', 'project approval', 'raises guidance')),
    ('Financial', 'Medium', ('earnings', 'revenue', 'cash flow', 'debt', 'financing', 'acquisition', 'merger', 'guidance', 'dividend', 'buyback', 'quarterly results')),
    ('Negative', 'Medium', ('lawsuit', 'investigation', 'probe', 'recall', 'delay', 'downgrade', 'layoff', 'regulatory concern')),
    ('Positive', 'Medium', ('contract', 'partnership', 'expansion', 'new project', 'launch', 'breakthrough', 'approval', 'upgrade')),
]

def classify_headline(title):
    text = title.lower()
    if re.search(r'\b(ceo|chief executive)\b',text) and re.search(r'\b(return\w*|reinstat\w*|resign\w*|appoint\w*|oust\w*|fired|departure|steps down|back)\b',text):
        return 'Mixed', 'High'
    for category, priority, terms in NEWS_RULES:
        if any(term in text for term in terms):
            return category, priority
    return 'Other', 'Review'

ALIASES = {'NVDA':['Nvidia','Jensen Huang'], 'AMD':['AMD','Advanced Micro Devices','Lisa Su'], 'NBIS':['Nebius'], 'CRWV':['CoreWeave'], 'ORCL':['Oracle'], 'OKLO':['Oklo'], 'AAOI':['Applied Optoelectronics'], 'APLD':['Applied Digital'], 'FLNC':['Fluence Energy'], 'IREN':['IREN','Iris Energy'], 'VRT':['Vertiv'], 'PGY':['Pagaya'], 'SOUN':['SoundHound'], 'UBER':['Uber'], 'GOOGL':['Alphabet','Google'], 'AVGO':['Broadcom'], 'RKLB':['Rocket Lab'], 'PLTR':['Palantir'], 'NET':['Cloudflare'], 'NOW':['ServiceNow'], 'BE':['Bloom Energy'], 'GEV':['GE Vernova'], 'CEG':['Constellation Energy'], 'VST':['Vistra'], 'QBTS':['D-Wave'], 'QUBT':['Quantum Computing Inc'], 'BABA':['Alibaba']}
@st.cache_data(ttl=3600,show_spinner=False)
def company_profile(ticker):
    try: return yf.Ticker(ticker).info or {}
    except Exception: return {}

def company_aliases(ticker):
    info=company_profile(ticker)
    names=list(ALIASES.get(ticker,[]))
    for key in ('shortName','longName'):
        name=info.get(key,'') or ''
        name=re.sub(r'\s+(Inc\.?|Corporation|Corp\.?|Ltd\.?|Limited|PLC|Class [A-Z])\s*$', '', name, flags=re.I).strip(' ,.')
        if len(name)>3: names.append(name)
    if len(ticker)>=3 and ticker not in ('NOW','NET','TER','SERV'): names.append(ticker)
    return list(set(names))

def identify(title, aliases):
    hits=[]
    for ticker,names in aliases.items():
        positions=[m.start() for name in names if (m:=re.search(r'(?<!\w)'+re.escape(name)+r'(?!\w)',title,re.I))]
        if positions: hits.append((min(positions),ticker))
    return [t for _,t in sorted(hits)]

@st.cache_data(ttl=900, show_spinner=False)
def scan_company_news(ticker, name):
    articles=recent_news(ticker,limit=20)
    for item in articles: item['source']='Yahoo Finance feed'
    errors=[]
    if not articles: errors.append('Yahoo feed empty/unavailable')
    try:
        response=requests.get('https://news.google.com/rss/search',params={'q':f'"{name}" stock when:30d','hl':'en-US','gl':'US','ceid':'US:en'},timeout=10)
        response.raise_for_status()
        for node in ET.fromstring(response.content).findall('./channel/item')[:35]:
            title=node.findtext('title',''); url=node.findtext('link',''); source=node.findtext('source','Google News')
            if title and url.startswith('https://'):
                articles.append({'title':title,'url':url,'published':node.findtext('pubDate',''),'source':source+' via Google News'})
    except Exception: errors.append('Google News unavailable')
    return articles,errors

def published_date(value):
    try: return pd.to_datetime(value,utc=True,errors='coerce')
    except Exception: return pd.NaT

with important:
    st.subheader('🚨 Important — Stock Intelligence Monitor')
    st.caption('Manual, on-demand scan. No background monitoring. Free news feeds may be incomplete or delayed.')
    st.write('Scan the full watchlist for potentially significant headlines, price gains or drops, and upcoming earnings — even if a stock price has not moved.')
    c1,c2,c3=st.columns([2,1,1])
    with c1:
        scan_tickers=st.multiselect('Stocks to scan', st.session_state.tickers, default=st.session_state.tickers, key='important_scan')
    with c2:
        category_filter=st.selectbox('News category', ['All','Positive','Negative','Financial','Mixed','Other','Price gain','Price drop','Earnings'])
    with c3:
        impact_filter=st.selectbox('Priority', ['All','High','Medium','Review'])
    date_filter=st.selectbox('News age',['7 days','24 hours','30 days','All retrieved'])
    company_filter=st.selectbox('Filter results by company',['All']+st.session_state.tickers)
    run_scan=st.button('🔎 Refresh Important Updates',type='primary')
    if run_scan:
        if not scan_tickers:
            st.warning('Select at least one stock.')
        else:
            findings=[]; errors=[]
            scan_company_news.clear(); scan_price_alert.clear(); next_earnings_date.clear()
            aliases={t:company_aliases(t) for t in st.session_state.tickers}
            progress=st.progress(0, text='Checking stock updates...')
            for i,ticker in enumerate(scan_tickers):
                rule=CONFIG.get('overrides',{}).get(ticker,{})
                try:
                    movement=scan_price_alert(ticker)
                    threshold=float(rule.get('drop_percent',CONFIG.get('default_drop_percent',5)))
                    if movement and abs(movement['change_pct'])>=threshold:
                        findings.append({'Ticker':ticker,'Category':'Price gain' if movement['change_pct']>0 else 'Price drop','Priority':'High',
                            'Headline':f"{movement['change_pct']:.2f}% over approximately 1 hour (threshold {threshold:g}%)",
                            'Published':movement['as_of'],'Source':'Intraday price data','URL':'',
                            'Notes':'Price movement only; no verified cause identified'})
                except Exception: errors.append(ticker+' price')
                try:
                    earnings=next_earnings_date(ticker)
                    days=int(rule.get('earnings_reminder_days',CONFIG.get('earnings_reminder_days',7)))
                    if earnings is not None and 0<=(earnings-date.today()).days<=days:
                        findings.append({'Ticker':ticker,'Category':'Earnings','Priority':'Medium',
                            'Headline':f"Provider-listed earnings date: {earnings.isoformat()}",
                            'Published':date.today().isoformat(),'Source':'Yahoo Finance calendar','URL':'',
                            'Notes':'Estimated date; verify with company investor relations'})
                except Exception: errors.append(ticker+' earnings')
                try:
                    name=company_profile(ticker).get('shortName') or ticker
                    articles,issues=scan_company_news(ticker,name)
                    errors.extend(ticker+' '+issue for issue in issues)
                    for article in articles:
                        matches=identify(article['title'],aliases)
                        category,priority=classify_headline(article['title'])
                        primary=matches[0] if matches else 'Unverified'
                        findings.append({'Ticker':primary,'Category':category,'Priority':priority if matches else 'Review',
                            'Headline':article['title'],'Published':article.get('published',''),
                            'Source':article.get('source','News feed'),'URL':article['url'],
                            'Notes':('Related: '+', '.join(matches[1:])+'. ' if len(matches)>1 else '')+('Headline company match; verify primary subject and claims.' if matches else 'Company not identified; feed association '+ticker+' only.')})
                except Exception: errors.append(ticker+' news')
                progress.progress((i+1)/len(scan_tickers),text=f'Checked {i+1}/{len(scan_tickers)} stocks')
            progress.empty()
            # Deduplicate provider-repeated stories while retaining a ticker association.
            unique={}
            for item in findings:
                key=(item['Ticker'],re.sub(r'[^a-z0-9 ]','',item['Headline'].lower().split(' - ')[0]))
                unique[key]=item
            st.session_state.important_findings=list(unique.values())
            st.session_state.important_errors=errors
            st.session_state.important_checked=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
            st.session_state.important_scanned=len(scan_tickers)
    if 'important_checked' in st.session_state:
        st.caption(f"Last completed check: {st.session_state.important_checked} · {st.session_state.important_scanned} stocks requested")
        findings=st.session_state.get('important_findings',[])
        days={'24 hours':1,'7 days':7,'30 days':30}.get(date_filter)
        def in_window(f):
            if not days or not f['URL']: return True
            stamp=published_date(f['Published'])
            return pd.notna(stamp) and pd.Timestamp.now(tz='UTC')-pd.Timedelta(days=days)<=stamp<=pd.Timestamp.now(tz='UTC')
        findings=[f for f in findings if in_window(f) and (company_filter=='All' or f['Ticker']==company_filter)]
        selected=[f for f in findings if (category_filter=='All' or f['Category']==category_filter) and
                  (impact_filter=='All' or f['Priority']==impact_filter)]
        priority_order={'High':0,'Medium':1,'Review':2}
        selected.sort(key=lambda f:(priority_order.get(f['Priority'],3),f['Ticker']))
        high=sum(f['Priority']=='High' for f in findings)
        st.metric('High-priority items to review',high)
        if selected:
            for item in selected:
                with st.container(border=True):
                    st.markdown(f"**{item['Ticker']}** · {item['Category']} · **{item['Priority']} priority**")
                    if item['URL']:
                        st.markdown(f"[{item['Headline']}]({item['URL']})")
                    else:
                        st.write(item['Headline'])
                    st.caption(f"{item['Published'] or 'Publication time unavailable'} · {item['Source']} · {item['Notes']}")
        else:
            st.info('No items match these filters. Missing feeds or delayed prices do not mean there were no significant developments.')
        if st.session_state.get('important_errors'):
            st.warning('Some data checks failed or were unavailable: '+', '.join(st.session_state.important_errors[:8]))
    else:
        st.info('Click “Refresh Important Updates” to scan your watchlist. No scan has been performed in this session.')
    st.caption('High/Medium are keyword-based REVIEW priorities, not verified impact or investment recommendations. Allegations are not established facts. Open linked sources before drawing conclusions. Revenue slowdown detection requires validated financial comparisons and is not active yet.')

with stocks:
    if st.session_state.tickers:
        with st.spinner('Loading stock research data...'):
            rows=[stock_data(t) for t in st.session_state.tickers]
        a,b,c=st.columns(3)
        a.metric('Tracked stocks',len(rows));b.metric('Loaded prices',sum(r.get('_loaded',False) for r in rows));c.metric('Unavailable',sum(not r.get('_loaded',False) for r in rows))
        overview,financials,details,events,alerts=st.tabs(['Overview','Financials','Company detail','Milestones & earnings','Business & Risks'])
        with overview:
            columns=['Ticker','Company','Category','Price','1D %','1W %','1M %','YTD %','3Y %','Market Cap','Currency']
            overview_df = pd.DataFrame(rows).reindex(columns=columns)
            overview_df['Market Cap'] = overview_df['Market Cap'].map(compact_amount)
            dates=sorted({r['As of'] for r in rows if r.get('As of')})
            st.caption('Latest price dates: '+(', '.join(dates) if dates else 'Unavailable')+' · cached up to 1 hour')
            returns=['1D %','1W %','1M %','YTD %','3Y %']
            def return_color(v):
                return 'color: #16a34a' if pd.notna(v) and v>0 else 'color: #dc2626' if pd.notna(v) and v<0 else 'color: #888888'
            styled=overview_df.style.map(return_color,subset=returns).format({c:'{:+.2f}%' for c in returns},na_rep='N/A')
            st.dataframe(styled,hide_index=True,use_container_width=True)
            st.caption('Price changes use adjusted daily closing prices (not intraday). YTD/3Y are price returns; three-year returns require sufficient history. Data may be delayed.')
        with financials:
            cols=['Ticker','P/E','Forward P/E','P/S','Revenue (TTM)','Revenue Growth YoY %','Free Cash Flow','Cash','Debt','52W High','52W Low']
            financials_df = pd.DataFrame(rows).reindex(columns=cols)
            for amount_col in ['Revenue (TTM)', 'Free Cash Flow', 'Cash', 'Debt']:
                financials_df[amount_col] = financials_df[amount_col].map(compact_amount)
            financials_df = financials_df.fillna('N/A')
            st.dataframe(financials_df,hide_index=True,use_container_width=True)
            st.caption('Fundamental figures come from Yahoo Finance and may be stale, missing or calculated on different reporting periods. N/A does not mean zero.')
        with details:
            selected=st.selectbox('Select company',st.session_state.tickers)
            r=next(row for row in rows if row['Ticker']==selected)
            st.subheader(f"{r.get('Company',selected)} ({selected})")
            st.write(f"**Category:** {r.get('Category','Unclassified')}")
            c1,c2=st.columns(2)
            for col,label,base in [(c1,'Change from 52-week high',r.get('52W High')),(c2,'Change from 52-week low',r.get('52W Low'))]:
                change=percent(r.get('Price'),base)
                col.metric(label,f'{change:+.2f}%' if change is not None else 'N/A')
            try:
                h=price_history(selected,period='1y')
                if not h.empty:st.line_chart(h['Close'],y_label='Adjusted closing price')
                else:st.info('Price chart unavailable')
            except Exception:st.info('Price chart unavailable')
            st.markdown('#### Why might this stock be moving?')
            st.info('Possible related headlines appear below. A price move cannot reliably be attributed to a headline without corroborating evidence. If no reliable catalyst is identified, the cause is unknown.')
            news=recent_news(selected)
            if news:
                for item in news:st.markdown(f"- [{item['title']}]({item['url']})" + (f" — {item['published']}" if item['published'] else ''))
            else:st.write('No recent linked news available from this provider. No verified catalyst identified.')
        with events:
            event_ticker=st.selectbox('Select company',st.session_state.tickers,key='event_company')
            earnings=next_earnings_date(event_ticker)
            e1,e2=st.columns(2)
            e1.metric('Next earnings (provider estimate)',str(earnings) if earnings else 'N/A')
            e2.metric('Days until earnings',(earnings-date.today()).days if earnings else 'N/A')
            st.caption('Verify dates with investor relations. Provider estimates may change.')
            if st.button('Load earnings history and milestone leads'):
                try:
                    history=yf.Ticker(event_ticker).get_earnings_dates(limit=12)
                    if history is not None and not history.empty:
                        st.dataframe(history[history.index.date<=date.today()].head(4),use_container_width=True)
                    else: st.info('Historical earnings unavailable.')
                except Exception: st.info('Historical earnings unavailable.')
                articles,issues=scan_company_news(event_ticker,company_profile(event_ticker).get('shortName') or event_ticker)
                st.markdown('#### Potential upcoming milestones — verify dates and status')
                matches=[a for a in articles if identify(a['title'],{event_ticker:company_aliases(event_ticker)}) and re.search(r'\b(plan\w*|expects?|scheduled|upcoming|target\w*|to launch|to build|to open|to report|will launch|will report)\b',a['title'],re.I)]
                for a in matches[:12]:
                    st.markdown(f"- [{a['title']}]({a['url']})")
                    st.caption(f"Published: {a['published']} · Event date/status not independently verified")
                if not matches: st.info('No upcoming milestone leads found. This is not a verified event calendar.')
                if issues: st.warning('; '.join(issues))
            st.link_button('Company news and investor information',f'https://finance.yahoo.com/quote/{event_ticker}/')
        with alerts:
            risk_ticker=st.selectbox('Select company',st.session_state.tickers,key='risk_company')
            profile=company_profile(risk_ticker)
            st.subheader('Business overview')
            summary=profile.get('longBusinessSummary','')
            st.write(' '.join(re.split(r'(?<=[.!?])\s+',summary)[:4]) if summary else 'Business description unavailable.')
            st.caption('Source: Yahoo Finance company profile; publication date unavailable.')
            st.subheader('Major challenges and future risks')
            risk_map={
                'NVDA':['Competition from custom accelerators and other chip designers','Export controls and geographic sales restrictions','Dependence on external chip manufacturing and large AI customers'],
                'AMD':['AI accelerator adoption and software ecosystem competition','External manufacturing capacity and supply constraints','Cyclical PC and server demand'],
                'CRWV':['Debt and refinancing needs','Large customer concentration','GPU depreciation and data center execution'],
                'NBIS':['Capital-intensive capacity expansion','Funding and dilution risk','Customer acquisition and utilization'],
                'APLD':['Construction delays and power availability','Project financing and tenant concentration'],
                'OKLO':['Licensing and regulatory approvals','Fuel supply and first-of-kind construction','Commercial deployment and funding uncertainty'],
                'FLNC':['Project execution and warranty costs','Battery supply chain and working capital','Competitive pricing and policy changes'],
                'IREN':['Power and GPU infrastructure execution','Funding and utilization','Bitcoin exposure where applicable'],
                'ORCL':['Cloud capital expenditure and debt','Cloud competition and capacity delivery'],
                'AAOI':['Optical component demand and customer concentration','Manufacturing ramp and margin pressure'],
                'PGY':['Credit losses and funding partner availability','Economic sensitivity and model performance'],
                'SOUN':['Commercial adoption and recurring revenue conversion','Operating losses and financing needs'],
                'UBER':['Driver classification and regulation','Competition and autonomous vehicle disruption'],
                'VRT':['Data center investment cycles','Supply chain and execution risks'],
            }
            risks=risk_map.get(risk_ticker,[])
            if risks:
                st.caption('Curated research questions, not verified current company disclosures.')
                for risk in risks: st.markdown('- '+risk)
            else: st.info('No curated company-specific risk summary yet. Review the latest annual report risk factors.')
            st.link_button('Find official SEC filings',f'https://www.sec.gov/edgar/search/#/q={risk_ticker}')
            if profile.get('website','').startswith('https://'): st.link_button('Company website',profile['website'])
    else:st.info('Add a stock in the sidebar.')
with etfs:
    st.subheader('ETF Intelligence — Coming Soon')
    st.write('This separate tab is reserved for ETF performance, holdings, expense ratios, AUM, distributions and ETF-specific alerts. No ETF monitoring is active yet.')
