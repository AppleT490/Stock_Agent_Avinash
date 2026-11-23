import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime
st.set_page_config(page_title='Stock Intelligence',layout='wide',page_icon='📈')
st.title('📈 Stock Intelligence Dashboard')
st.caption('Research dashboard • Yahoo Finance data may be delayed, incomplete or unavailable. Not for trade execution.')
if 'tickers' not in st.session_state: st.session_state.tickers=['NVDA','NBIS','AMD','ORCL','CRWV']
with st.sidebar:
 st.header('Watchlist (max 25)')
 new=st.text_input('Add ticker',placeholder='e.g. AVGO').strip().upper()
 if st.button('Add ticker'):
  if not new: st.warning('Enter a ticker')
  elif new in st.session_state.tickers: st.warning('Already added')
  elif len(st.session_state.tickers)>=25: st.warning('Maximum 25')
  elif not all(c.isalnum() or c in '.^-' for c in new): st.warning('Invalid ticker')
  else: st.session_state.tickers.append(new); st.rerun()
 st.write(f'{len(st.session_state.tickers)} / 25')
 remove=st.selectbox('Remove ticker',['—']+st.session_state.tickers)
 if st.button('Remove selected') and remove!='—': st.session_state.tickers.remove(remove);st.rerun()
 st.download_button('Export watchlist',pd.DataFrame({'Ticker':st.session_state.tickers}).to_csv(index=False),'watchlist.csv','text/csv')
 st.info('For the first version, ticker changes last only for your current session. Persistent storage comes next.')
@st.cache_data(ttl=3600,show_spinner=False)
def fetch(t):
 try:
  obj=yf.Ticker(t); hist=obj.history(period='3mo',auto_adjust=False)
  info=obj.info or {}
  if hist.empty: return {'Ticker':t,'Status':'No price data'}
  closes=hist['Close'].dropna(); now=float(closes.iloc[-1]); week=float(closes.iloc[-6]) if len(closes)>5 else None; month=float(closes.iloc[-22]) if len(closes)>21 else None
  return {'Ticker':t,'Company':info.get('shortName') or t,'Price':round(now,2),'1W %':round((now/week-1)*100,2) if week else None,'1M %':round((now/month-1)*100,2) if month else None,'P/E':info.get('trailingPE'),'Forward P/E':info.get('forwardPE'),'Revenue (TTM)':info.get('totalRevenue'),'Currency':info.get('currency',''),'As of':str(closes.index[-1].date()),'Status':'OK'}
 except Exception as e:return {'Ticker':t,'Status':'Data unavailable'}
if st.button('Refresh data'):fetch.clear();st.rerun()
if st.session_state.tickers:
 with st.spinner('Fetching market data...'):
  records=[fetch(t) for t in st.session_state.tickers]
 df=pd.DataFrame(records)
 a,b,c=st.columns(3);a.metric('Tracked tickers',len(records));b.metric('Loaded',sum(r.get('Status')=='OK' for r in records));c.metric('Unavailable',sum(r.get('Status')!='OK' for r in records))
 overview,details,events=st.tabs(['Overview','Company detail','Milestones & earnings'])
 with overview:
  st.dataframe(df,hide_index=True,use_container_width=True,column_config={'Revenue (TTM)':st.column_config.NumberColumn(format='compact')})
  st.caption('1W/1M compare the latest available close with approximately 5/21 trading sessions earlier. P/E and revenue fields may be unavailable or stale.')
 with details:
  selected=st.selectbox('Select company',st.session_state.tickers)
  record=next(r for r in records if r['Ticker']==selected)
  st.json(record)
  try:
   h=yf.Ticker(selected).history(period='6mo');st.line_chart(h['Close'],y_label='Price') if not h.empty else st.info('Chart unavailable')
  except Exception:st.info('Chart unavailable')
 with events:
  st.info('Next phase: verified earnings dates, investor-relations announcements, contracts and milestones with source links. No events are fabricated in this version.')
else:st.info('Add your first ticker in the sidebar.')
