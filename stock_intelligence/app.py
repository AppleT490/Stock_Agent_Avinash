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
