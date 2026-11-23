"""Stock Agent Avinash: research dashboard, not a trading system."""
import json
from pathlib import Path
from datetime import date, timedelta, datetime, timezone
import pandas as pd
import streamlit as st
import yfinance as yf
from market_data import CATEGORIES, ETF_CATEGORIES, num, percent, price_history, history_return, recent_news, valid_ticker, price_drop_in_hour

HERE=Path(__file__).resolve().parent
CONFIG=json.loads((HERE/'config.json').read_text())
st.set_page_config(page_title='Stock Agent Avinash',layout='wide',page_icon='📈')
st.title('📈 Stock Agent Avinash')
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

if st.button('Refresh data'):stock_data.clear();st.rerun()
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
    ('Negative', 'High', ('fraud', 'scam', 'accounting irregularit', 'sec investigation', 'criminal investigation', 'bankrupt', 'chapter 11', 'restatement', 'class action', 'data breach', 'cyberattack', 'indict', 'subpoena', 'sanction', 'contract cancell', 'project cancell', 'regulatory rejection')),
    ('Financial', 'High', ('share offering', 'public offering', 'stock offering', 'dilution', 'convertible notes', 'going concern', 'liquidity crisis', 'guidance cut', 'cuts guidance', 'revenue miss', 'earnings miss', 'debt default', 'capital raise')),
    ('Positive', 'High', ('major contract', 'multibillion', 'billion-dollar deal', 'regulatory approval', 'fda approval', 'wins contract', 'signs contract', 'new partnership', 'strategic partnership', 'project approval', 'raises guidance')),
    ('Financial', 'Medium', ('earnings', 'revenue', 'cash flow', 'debt', 'financing', 'acquisition', 'merger', 'guidance', 'dividend', 'buyback', 'quarterly results')),
    ('Negative', 'Medium', ('lawsuit', 'investigation', 'probe', 'recall', 'delay', 'downgrade', 'layoff', 'regulatory concern')),
    ('Positive', 'Medium', ('contract', 'partnership', 'expansion', 'new project', 'launch', 'breakthrough', 'approval', 'upgrade')),
]

def classify_headline(title):
    text = title.lower()
    for category, priority, terms in NEWS_RULES:
        if any(term in text for term in terms):
            return category, priority
    return 'Other', 'Review'

@st.cache_data(ttl=900, show_spinner=False)
def scan_company_news(ticker):
    return recent_news(ticker, limit=12)

with important:
    st.subheader('🚨 Important — Stock Intelligence Monitor')
    st.caption('Manual, on-demand scan. No email, account login, passwords, or background monitoring. Free news feeds may be incomplete or delayed.')
    st.write('Scan the full watchlist for potentially significant headlines, price drops, and upcoming earnings — even if a stock price has not moved.')
    c1,c2,c3=st.columns([2,1,1])
    with c1:
        scan_tickers=st.multiselect('Stocks to scan', st.session_state.tickers, default=st.session_state.tickers, key='important_scan')
    with c2:
        category_filter=st.selectbox('News category', ['All','Positive','Negative','Financial','Other'])
    with c3:
        impact_filter=st.selectbox('Priority', ['All','High','Medium','Review'])
    run_scan=st.button('🔎 Refresh Important Updates',type='primary')
    if run_scan:
        if not scan_tickers:
            st.warning('Select at least one stock.')
        else:
            findings=[]; errors=[]
            progress=st.progress(0, text='Checking stock updates...')
            for i,ticker in enumerate(scan_tickers):
                rule=CONFIG.get('overrides',{}).get(ticker,{})
                try:
                    movement=scan_price_alert(ticker)
                    threshold=float(rule.get('drop_percent',CONFIG.get('default_drop_percent',5)))
                    if movement and movement['change_pct']<=-threshold:
                        findings.append({'Ticker':ticker,'Category':'Price drop','Priority':'High',
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
                    for article in scan_company_news(ticker):
                        category,priority=classify_headline(article['title'])
                        findings.append({'Ticker':ticker,'Category':category,'Priority':priority,
                            'Headline':article['title'],'Published':article.get('published',''),
                            'Source':'News link','URL':article['url'],
                            'Notes':'Headline keyword match only; check source and publication date'})
                except Exception: errors.append(ticker+' news')
                progress.progress((i+1)/len(scan_tickers),text=f'Checked {i+1}/{len(scan_tickers)} stocks')
            progress.empty()
            # Deduplicate provider-repeated stories while retaining a ticker association.
            unique={}
            for item in findings:
                key=(item['Ticker'],item['URL'] or item['Headline'])
                unique[key]=item
            st.session_state.important_findings=list(unique.values())
            st.session_state.important_errors=errors
            st.session_state.important_checked=datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
            st.session_state.important_scanned=len(scan_tickers)
    if 'important_checked' in st.session_state:
        st.caption(f"Last completed check: {st.session_state.important_checked} · {st.session_state.important_scanned} stocks requested")
        findings=st.session_state.get('important_findings',[])
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
                    st.caption(f"{item['Published'] or 'Publication time unavailable'} · {item['Notes']}")
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
        overview,financials,details,events,alerts=st.tabs(['Overview','Financials','Company detail','Milestones & earnings','Alerts'])
        with overview:
            columns=['Ticker','Company','Category','Price','1W %','1M %','YTD %','3Y %','Market Cap','Currency','As of']
            overview_df = pd.DataFrame(rows).reindex(columns=columns)
            overview_df['Market Cap'] = overview_df['Market Cap'].map(compact_amount)
            st.dataframe(overview_df,hide_index=True,use_container_width=True)
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
            st.info('Earnings reminders can be checked manually in the Important tab when the data provider supplies a future date. A comprehensive verified milestone calendar is not yet implemented.')
        with alerts:
            st.info('Email notifications are disabled. Use the 🚨 Important tab to manually check price-drop alerts, upcoming earnings and recent headlines.')
            st.caption('The Important tab performs on-demand checks only; no background monitoring or persistent alert history is enabled.')
    else:st.info('Add a stock in the sidebar.')
with etfs:
    st.subheader('ETF Intelligence — Coming Soon')
    st.write('This separate tab is reserved for ETF performance, holdings, expense ratios, AUM, distributions and ETF-specific alerts. No ETF monitoring is active yet.')
