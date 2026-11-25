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
st.caption('Beyond the Price. Understand the Business. · v1.5')
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
    st.info('Research ticker selection is temporary. Public market data only.')

def number(v):
    try:
        x=float(v)
        return x if pd.notna(x) and abs(x)!=float('inf') else None
    except (TypeError,ValueError): return None

def pct_value(v):
    x=number(v)
    return x*100 if x is not None else None

def profitability(eps):
    x=number(eps)
    return 'Unavailable' if x is None else 'Profitable' if x>0 else 'Loss-making' if x<0 else 'Break-even'

def decimal(v):
    x=number(v)
    return f'{x:,.2f}' if x is not None else 'N/A'

def pe_display(pe,eps):
    e=number(eps); p=number(pe)
    if e is not None and e<=0: return 'N/M — loss' if e<0 else 'N/M — zero EPS'
    return decimal(p) if p is not None and p>0 else 'N/A — unavailable'

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
        r.update({'EPS (TTM)':num(info.get('trailingEps')), 'Forward EPS':num(info.get('forwardEps')),
            'Profit Margin %':pct_value(info.get('profitMargins')), 'Gross Margin %':pct_value(info.get('grossMargins')),
            'Financial Currency':info.get('financialCurrency',''), 'Net Income (TTM)':num(info.get('netIncomeToCommon'),0)})
        r['Profitability']=profitability(r.get('EPS (TTM)'))
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
important,stocks,screener,etfs=st.tabs(['🚨 Important','📊 Stocks','Stock Screener','🧺 ETFs (Coming Soon)'])

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

@st.cache_data(ttl=3600,show_spinner=False)
def quarterly_data(ticker):
    obj=yf.Ticker(ticker); series={}; issues=[]
    specs=[('quarterly_income_stmt',{'Revenue':['Total Revenue'],'Net income':['Net Income'],'Gross profit':['Gross Profit'],'Diluted average shares':['Diluted Average Shares']}),
           ('quarterly_cashflow',{'Operating cash flow':['Operating Cash Flow'],'Free cash flow':['Free Cash Flow'],'Capital expenditure':['Capital Expenditure']}),
           ('quarterly_balance_sheet',{'Cash and short-term investments':['Cash Cash Equivalents And Short Term Investments'],'Cash equivalents':['Cash And Cash Equivalents'],'Debt':['Total Debt'],'Outstanding shares':['Ordinary Shares Number']})]
    for attr,fields in specs:
        try:
            frame=getattr(obj,attr)
            if frame is None or frame.empty: raise ValueError('empty')
            for label,names in fields.items():
                for name in names:
                    if name in frame.index:
                        v=frame.loc[name]
                        if isinstance(v,pd.DataFrame): v=v.iloc[0]
                        v=pd.to_numeric(v,errors='coerce'); v.index=pd.to_datetime(v.index,errors='coerce').normalize()
                        series[label]=v[~v.index.duplicated(keep='first')]; break
        except Exception: issues.append(attr+' unavailable')
    df=pd.DataFrame(series).sort_index().dropna(how='all') if series else pd.DataFrame()
    if not df.empty:
        if 'Free cash flow' not in df and {'Operating cash flow','Capital expenditure'}<=set(df.columns):
            df['Free cash flow']=df['Operating cash flow']-df['Capital expenditure'].abs()
        if {'Gross profit','Revenue'}<=set(df.columns): df['Gross margin %']=100*df['Gross profit']/df['Revenue'].where(df['Revenue']>0)
    return df,issues

def risk_checks(df,r):
    results=[]
    def add(label,status,detail): results.append({'Indicator':label,'Status':status,'Evidence':detail})
    def vals(col): return df[col].dropna() if col in df else pd.Series(dtype=float)
    def pair(col):
        v=vals(col)
        if len(v)<2 or not 60<=(v.index[-1]-v.index[-2]).days<=120:return None
        return float(v.iloc[-2]),float(v.iloc[-1])
    growth=number(r.get('Revenue Growth YoY %'))
    add('Revenue growth YoY','Unavailable' if growth is None else 'Warning' if growth<0 else 'No flag',decimal(growth)+'%' if growth is not None else 'Missing provider growth')
    for col,label,rule in [('Net income','Increasing losses',lambda a,b:b<0 and b<a),('Debt','Rising debt',lambda a,b:b>a),('Outstanding shares','Share dilution indicator',lambda a,b:b>a),('Gross margin %','Margin deterioration',lambda a,b:b<a)]:
        p=pair(col)
        add(label,'Unavailable' if p is None else 'Warning' if rule(*p) else 'No flag',f'{compact_amount(p[0])} → {compact_amount(p[1])} (QoQ)' if p else 'Two consecutive quarters required')
    f=vals('Free cash flow').tail(4)
    consecutive=len(f)==4 and all(60<=d.days<=120 for d in f.index.to_series().diff().dropna())
    add('Persistent negative FCF','Unavailable' if not consecutive else 'Warning' if (f<0).all() else 'No flag',f'{int((f<0).sum())}/4 negative quarters' if consecutive else 'Four consecutive quarters required')
    cash=vals('Cash and short-term investments')
    if cash.empty: cash=vals('Cash equivalents')
    burn=-float(f.mean()) if consecutive else None
    runway=None
    if burn is not None and burn>0 and not cash.empty and cash.index[-1]==f.index[-1] and cash.iloc[-1]>=0: runway=float(cash.iloc[-1])/burn*3
    add('Estimated cash runway','Unavailable' if runway is None else 'High risk' if runway<12 else 'No flag',f'{runway:.1f} months; average quarterly FCF burn {compact_amount(burn)}' if runway is not None else 'Requires net FCF burn and aligned cash data')
    return results

with stocks:
    if st.session_state.tickers:
        with st.spinner('Loading stock research data...'):
            rows=[stock_data(t) for t in st.session_state.tickers]
        a,b,c=st.columns(3)
        a.metric('Tracked stocks',len(rows));b.metric('Loaded prices',sum(r.get('_loaded',False) for r in rows));c.metric('Unavailable',sum(not r.get('_loaded',False) for r in rows))
        overview,financials,details,events,alerts,trends,flags,analysts=st.tabs(['Overview','Financials','Company detail','Milestones & earnings','Business & Risks','Quarterly Trends','Financial Red Flags','Analyst Expectations'])
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
            st.dataframe(styled,hide_index=True,use_container_width=True,column_config={'Price':st.column_config.NumberColumn(format='%.2f')})
            st.caption('Price changes use adjusted daily closing prices (not intraday). YTD/3Y are price returns; three-year returns require sufficient history. Data may be delayed.')
        with financials:
            cols=['Ticker','P/E','Forward P/E','P/S','EPS (TTM)','Forward EPS','Profitability','Profit Margin %','Gross Margin %','Revenue (TTM)','Revenue Growth YoY %','Net Income (TTM)','Free Cash Flow','Cash','Debt','52W High','52W Low','Currency','Financial Currency']
            financials_df = pd.DataFrame(rows).reindex(columns=cols)
            financials_df['P/E']=[pe_display(r.get('P/E'),r.get('EPS (TTM)')) for r in rows]
            financials_df['Forward P/E']=[pe_display(r.get('Forward P/E'),r.get('Forward EPS')) for r in rows]
            for amount_col in ['Revenue (TTM)','Net Income (TTM)','Free Cash Flow','Cash','Debt']:
                financials_df[amount_col]=financials_df[amount_col].map(compact_amount)
            for col in ['P/S','EPS (TTM)','Forward EPS','Profit Margin %','Gross Margin %','Revenue Growth YoY %','52W High','52W Low']:
                financials_df[col]=financials_df[col].map(decimal)
            st.dataframe(financials_df.fillna('N/A'),hide_index=True,use_container_width=True)
            st.caption('Yahoo Finance fundamentals. N/M means non-meaningful P/E due to nonpositive EPS; N/A means unavailable. Financial currency may differ from trading currency. Forward EPS is an estimate.')
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
        with trends:
            t=st.selectbox('Company',st.session_state.tickers,key='trend_company')
            if st.button('Load quarterly financials',key='load_trends'): st.session_state.trend_loaded=t
            if st.session_state.get('trend_loaded')==t:
                df,issues=quarterly_data(t)
                if df.empty: st.info('Quarterly financial data unavailable.')
                else:
                    recent=df.tail(4); currency=company_profile(t).get('financialCurrency','Unavailable')
                    st.caption(f'Yahoo Finance quarterly statements · Financial currency: {currency} · latest available period: {recent.index[-1].date()}')
                    display=recent.T.copy(); display.columns=[str(d.date()) for d in display.columns]
                    st.dataframe(display.map(compact_amount),use_container_width=True)
                    for field in ['Revenue','Net income','Gross margin %','Free cash flow','Cash and short-term investments','Debt','Outstanding shares']:
                        if field in recent and recent[field].notna().any():
                            st.markdown('**'+field+'**'); st.bar_chart(recent[field])
                if issues: st.warning('; '.join(issues))
        with flags:
            t=st.selectbox('Company',st.session_state.tickers,key='flag_company')
            if st.button('Check financial red flags'): st.session_state.flags_loaded=t
            if st.session_state.get('flags_loaded')==t:
                df,issues=quarterly_data(t); r=next(x for x in rows if x['Ticker']==t)
                report=pd.DataFrame(risk_checks(df,r))
                def flag_color(v): return 'color: #dc2626' if v in ('Warning','High risk') else 'color: #16a34a' if v=='No flag' else 'color: #888888'
                st.dataframe(report.style.map(flag_color,subset=['Status']),hide_index=True,use_container_width=True)
                st.caption('Research flags, not credit ratings. Share count changes can reflect splits or other corporate actions; verify issuance in filings. Cash runway is a rough historical FCF extrapolation, not a forecast; excludes future funding and debt maturities.')
                if issues: st.warning('; '.join(issues))
        with analysts:
            t=st.selectbox('Company',st.session_state.tickers,key='analyst_company')
            if st.button('Load analyst expectations'): st.session_state.analyst_loaded=t
            if st.session_state.get('analyst_loaded')==t:
                info=company_profile(t); r=next(x for x in rows if x['Ticker']==t)
                target=number(info.get('targetMeanPrice')); price=number(r.get('Price'))
                c1,c2,c3=st.columns(3)
                c1.metric('Latest daily price',decimal(price)); c2.metric('Mean analyst target',decimal(target)); c3.metric('Implied change',f'{(target/price-1)*100:+.2f}%' if target is not None and price is not None and price>0 else 'N/A')
                st.write('Low / median / high target: '+ ' / '.join(decimal(info.get(k)) for k in ['targetLowPrice','targetMedianPrice','targetHighPrice']))
                st.write('Analyst count: '+str(info.get('numberOfAnalystOpinions') or 'N/A')+' · Consensus: '+str(info.get('recommendationKey') or 'N/A'))
                try:
                    rec=yf.Ticker(t).recommendations_summary
                    if rec is not None and not rec.empty: st.dataframe(rec,hide_index=True,use_container_width=True)
                    else: st.info('Rating breakdown unavailable.')
                except Exception: st.info('Rating breakdown unavailable.')
                st.caption('Yahoo Finance analyst estimates; individual target dates unavailable. Targets are opinions, not forecasts guaranteed to occur. Prices and targets use provider trading currency.')
    else:st.info('Add a stock in the sidebar.')
with screener:
    st.subheader('Stock Screener')
    st.caption('Filters the current research watchlist only. Missing values are excluded when a corresponding filter is enabled. No personal investment information.')
    data=pd.DataFrame(rows) if st.session_state.tickers else pd.DataFrame()
    if data.empty: st.info('Add research tickers in the sidebar.')
    else:
        category=st.selectbox('Category',['All']+sorted(data['Category'].dropna().unique().tolist()),key='screen_category')
        a,b,c=st.columns(3)
        growth_on=a.checkbox('Filter revenue growth'); growth=a.number_input('Minimum YoY growth %',value=20.0,disabled=not growth_on)
        decline_on=b.checkbox('Filter decline from 52-week high'); decline=b.slider('Minimum decline %',0,100,30,disabled=not decline_on)
        pe_limit=c.selectbox('P/E',['Any','Below 15','Below 25','Below 50','Loss-making'])
        cap=st.selectbox('Market cap (USD only when filtered)',['Any','Below $1B','$1B–$10B','$10B–$100B','Above $100B'])
        profitable=st.checkbox('Profitable only'); positive_fcf=st.checkbox('Positive free cash flow'); net_cash=st.checkbox('Cash greater than debt')
        def numeric(col): return pd.to_numeric(data[col],errors='coerce') if col in data else pd.Series(float('nan'),index=data.index)
        high=numeric('52W High'); price=numeric('Price'); data['Below 52W High %']=(1-price/high.where(high>0))*100
        mask=pd.Series(True,index=data.index)
        if category!='All': mask &= data['Category']==category
        if growth_on: mask &= numeric('Revenue Growth YoY %')>=growth
        if decline_on: mask &= data['Below 52W High %']>=decline
        if pe_limit=='Loss-making': mask &= numeric('EPS (TTM)')<0
        elif pe_limit!='Any': mask &= (numeric('P/E')>0)&(numeric('P/E')<float(pe_limit.split()[-1]))
        if profitable: mask &= numeric('EPS (TTM)')>0
        if positive_fcf: mask &= numeric('Free Cash Flow')>0
        if net_cash: mask &= numeric('Cash')>numeric('Debt')
        if cap!='Any':
            m=numeric('Market Cap'); mask &= data.reindex(columns=['Currency'])['Currency'].eq('USD')
            mask &= {'Below $1B':m<1e9,'$1B–$10B':(m>=1e9)&(m<1e10),'$10B–$100B':(m>=1e10)&(m<1e11),'Above $100B':m>=1e11}[cap]
        result=data.loc[mask].reindex(columns=['Ticker','Category','Price','Currency','Market Cap','P/E','EPS (TTM)','Revenue Growth YoY %','Below 52W High %','Free Cash Flow','Cash','Debt','Financial Currency'])
        for col in ['Market Cap','Free Cash Flow','Cash','Debt']: result[col]=result[col].map(compact_amount)
        st.write(f'{len(result)} of {len(data)} stocks match')
        st.dataframe(result,hide_index=True,use_container_width=True,column_config={col:st.column_config.NumberColumn(format='%.2f') for col in ['Price','P/E','EPS (TTM)','Revenue Growth YoY %','Below 52W High %']})
with etfs:
    st.subheader('ETF Intelligence — Coming Soon')
    st.write('This separate tab is reserved for ETF performance, holdings, expense ratios, AUM, distributions and ETF-specific alerts. No ETF monitoring is active yet.')
