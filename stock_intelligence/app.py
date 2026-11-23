"""Stock Agent Avinash: research dashboard, not a trading system."""
import json
from pathlib import Path
from datetime import date, timedelta
import pandas as pd
import streamlit as st
import yfinance as yf
from market_data import CATEGORIES, ETF_CATEGORIES, num, percent, price_history, history_return, recent_news, valid_ticker

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
    st.info('Dashboard watchlist edits are session-only. Automated email monitoring uses config.json in GitHub. Update that file to change monitored tickers.')

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
stocks,etfs=st.tabs(['📊 Stocks','🧺 ETFs (Coming Soon)'])
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
            st.info('Earnings reminders are supported by the scheduled alert script when a confirmed future earnings date is available from the data provider. A comprehensive verified milestone calendar is not yet implemented.')
        with alerts:
            st.write('**Automatic email monitoring:** rolling 60-minute price declines, default 5%, including available extended-hours bars.')
            st.write('**Configured stocks:** '+', '.join(CONFIG['tickers']))
            st.write('**OKLO:** 5% drop threshold, 7-day earnings reminder, revenue slowdown and major-news monitoring configured.')
            st.caption('Email requires GitHub Actions and private email secrets. Revenue and major-news alerts are experimental; no automatic alerts for them until reliable change detection is implemented.')
            statefile=HERE/'alert_state.json'
            if statefile.exists():
                try:
                    state=json.loads(statefile.read_text()); history=state.get('history',[])
                    if history:st.dataframe(pd.DataFrame(history[-100:][::-1]),hide_index=True,use_container_width=True)
                    else:st.info('No alerts recorded yet.')
                except Exception:st.info('Alert history currently unavailable.')
            else:st.info('No alert history yet. Scheduled monitoring has not recorded an event.')
    else:st.info('Add a stock in the sidebar.')
with etfs:
    st.subheader('ETF Intelligence — Coming Soon')
    st.write('This separate tab is reserved for ETF performance, holdings, expense ratios, AUM, distributions and ETF-specific alerts. No ETF monitoring is active yet.')
