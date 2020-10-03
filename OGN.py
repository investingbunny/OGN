# -*- coding: utf-8 -*-
"""
Created on Sat Jul 11 11:30:09 2020

@author: HRTR

"""
from nsepy import get_history
from nsepy.derivatives import get_expiry_date
import datetime
from datetime import date
from nsepy import get_rbi_ref_history
import yfinance as yf
import pandas as pd
import pyarrow
import pyarrow.feather as feather
from nsepy import get_index_pe_history
import matplotlib
import time
from dateutil.relativedelta import *
import os

DailyOHLCFilePath = "ohlc.ftr";
IntradayFilePath = "intraday.ftr"
MonthlyFuturesFilePath = "monthly-futures.ftr"
FullFuturesFilePath = "full-futures.ftr"
MonthlyOptionsFilePath = "monthly-options.ftr"
FXHistory = "FXHistory.ftr"
PEHistory = "PEHistory.ftr"

NSE500ScripList = ["BANKNIFTY","NIFTY","3MINDIA","ACC","AIAENG","APLAPOLLO","AUBANK","AARTIIND","AAVAS","ABBOTINDIA",
                   "ADANIGAS","ADANIGREEN","ADANIPORTS","ADANIPOWER","ADANITRANS","ABCAPITAL","ABFRL",
                   "ADVENZYMES","AEGISCHEM","AFFLE","AJANTPHARM","AKZOINDIA","APLLTD","ALKEM","ALLCARGO",
                   "AMARAJABAT","AMBER","AMBUJACEM","APOLLOHOSP","APOLLOTYRE","ARVINDFASN","ASAHIINDIA",
                   "ASHOKLEY","ASHOKA","ASIANPAINT","ASTERDM","ASTRAZEN","ASTRAL","ATUL","AUROPHARMA",
                   "AVANTIFEED","DMART","AXISBANK","BASF","BEML","BSE","BAJAJ-AUTO","BAJAJCON","BAJAJELEC",
                   "BAJFINANCE","BAJAJFINSV","BAJAJHLDNG","BALKRISIND","BALMLAWRIE","BALRAMCHIN","BANDHANBNK",
                   "BANKBARODA","BANKINDIA","MAHABANK","BATAINDIA","BAYERCROP","BERGEPAINT","BDL","BEL",
                   "BHARATFORG","BHEL","BPCL","BHARTIARTL","INFRATEL","BIOCON","BIRLACORPN","BSOFT",
                   "BLISSGVS","BLUEDART","BLUESTARCO","BBTC","BOMDYEING","BOSCHLTD","BRIGADE","BRITANNIA",
                   "CARERATING","CCL","CESC","CRISIL","CADILAHC","CANFINHOME","CANBK","CAPLIPOINT","CGCL",
                   "CARBORUNIV","CASTROLIND","CEATLTD","CENTRALBK","CDSL","CENTURYPLY","CERA","CHALET",
                   "CHAMBLFERT","CHENNPETRO","CHOLAHLDNG","CHOLAFIN","CIPLA","CUB","COALINDIA","COCHINSHIP",
                   "COLPAL","CONCOR","COROMANDEL","CREDITACC","CROMPTON","CUMMINSIND","CYIENT","DBCORP",
                   "DCBBANK","DCMSHRIRAM","DLF","DABUR","DALBHARAT","DEEPAKNTR","DELTACORP","DHFL","DBL",
                   "DISHTV","DCAL","DIVISLAB","DIXON","LALPATHLAB","DRREDDY","EIDPARRY","EIHOTEL","EDELWEISS",
                   "EICHERMOT","ELGIEQUIP","EMAMILTD","ENDURANCE","ENGINERSIN","EQUITAS","ERIS","ESCORTS",
                   "ESSELPACK","EXIDEIND","FDC","FEDERALBNK","FMGOETZE","FINEORG","FINCABLES","FINPIPE","FSL",
                   "FORTIS","FCONSUMER","FLFL","FRETAIL","GAIL","GEPIL","GET&D","GHCL","GMRINFRA","GALAXYSURF",
                   "GARFIBRES","GAYAPROJ","GICRE","GILLETTE","GLAXO","GLENMARK","GODFRYPHLP","GODREJAGRO",
                   "GODREJCP","GODREJIND","GODREJPROP","GRANULES","GRAPHITE","GRASIM","GESHIP","GREAVESCOT",
                   "GRINDWELL","GUJALKALI","GUJGASLTD","GMDCLTD","GNFC","GPPL","GSFC","GSPL","GULFOILLUB",
                   "HAPMIN","HEG","HCLTECH","HDFCAMC","HDFCBANK","HDFCLIFE","HFCL","HATSUN","HAVELLS","HEIDELBERG",
                   "HERITGFOOD","HEROMOTOCO","HEXAWARE","HSCL","HIMATSEIDE","HINDALCO","HAL","HINDCOPPER",
                   "HINDPETRO","HINDUNILVR","HINDZINC","HONAUT","HUDCO","HDFC","ICICIBANK","ICICIGI",
                   "ICICIPRULI","ISEC","ICRA","IDBI","IDFCFIRSTB","IDFC","IFBIND","IFCI","IIFL","IRB",
                   "IRCON","ITC","ITDCEM","ITI","INDIACEM","ITDC","IBULHSGFIN","IBULISL","IBREALEST",
                   "IBVENTURES","INDIAMART","INDIANB","IEX","INDHOTEL","IOC","IOB","INDOSTAR","IGL",
                   "INDUSINDBK","INFIBEAM","NAUKRI","INFY","INOXLEISUR","INTELLECT","INDIGO","IPCALAB",
                   "JBCHEPHARM","JKCEMENT","JKLAKSHMI","JKPAPER","JKTYRE","JMFINANCIL","JSWENERGY","JSWSTEEL",
                   "JAGRAN","JAICORPLTD","JISLJALEQS","J&KBANK","JAMNAAUTO","JINDALSAW","JSLHISAR","JSL",
                   "JINDALSTEL","JCHAC","JUBLFOOD","JUBILANT","JUSTDIAL","JYOTHYLAB","KPRMILL","KEI","KNRCON",
                   "KPITTECH","KRBL","KAJARIACER","KALPATPOWR","KANSAINER","KTKBANK","KARURVYSYA","KSCL",
                   "KEC","KENNAMET","KIRLOSENG","KOLTEPATIL","KOTAKBANK","L&TFH","LTTS","LICHSGFIN",
                   "LAXMIMACH","LAKSHVILAS","LTI","LT","LAURUSLABS","LEMONTREE","LINDEINDIA","LUPIN",
                   "LUXIND","MASFIN","MMTC","MOIL","MRF","MAGMA","MGL","MAHSCOOTER","MAHSEAMLES","M&MFIN",
                   "M&M","MAHINDCIE","MHRIL","MAHLOG","MANAPPURAM","MRPL","MARICO","MARUTI","MFSL",
                   "METROPOLIS","MINDTREE","MINDACORP","MINDAIND","MIDHANI","MOTHERSUMI","MOTILALOFS",
                   "MPHASIS","MCX","MUTHOOTFIN","NATCOPHARM","NBCC","NCC","NESCO","NHPC","NIITTECH",
                   "NLCINDIA","NMDC","NTPC","NH","NATIONALUM","NFL","NBVENTURES","NAVINFLUOR","NESTLEIND",
                   "NETWORK18","NILKAMAL","NAM-INDIA","OBEROIRLTY","ONGC","OIL","OMAXE","OFSS","ORIENTCEM",
                   "ORIENTELEC","ORIENTREF","PCJEWELLER","PIIND","PNBHOUSING","PNCINFRA","PTC","PVR",
                   "PAGEIND","PARAGMILK","PERSISTENT","PETRONET","PFIZER","PHILIPCARB","PHOENIXLTD",
                   "PIDILITIND","PEL","POLYCAB","PFC","POWERGRID","PRAJIND","PRESTIGE","PRSMJOHNSN","PGHL",
                   "PGHH","PNB","QUESS","RBLBANK","RECLTD","RITES","RADICO","RVNL","RAIN","RAJESHEXPO",
                   "RALLIS","RCF","RATNAMANI","RAYMOND","REDINGTON","RELAXO","RELCAPITAL","RELIANCE",
                   "RELINFRA","RPOWER","REPCOHOME","RESPONIND","SHK","SBILIFE","SJVN","SKFINDIA","SRF",
                   "SADBHAV","SANOFI","SCHAEFFLER","SIS","SFL","SHILPAMED","SHOPERSTOP","SHREECEM","RENUKA",
                   "SHRIRAMCIT","SRTRANSFIN","SIEMENS","SOBHA","SOLARINDS","SONATSOFTW","SOUTHBANK",
                   "SPANDANA","SPICEJET","STARCEMENT","SBIN","SAIL","STRTECH","STAR","SUDARSCHEM","SPARC",
                   "SUNPHARMA","SUNTV","SUNCLAYLTD","SUNDARMFIN","SUNDRMFAST","SUNTECK","SUPRAJIT",
                   "SUPREMEIND","SUZLON","SWANENERGY","SYMPHONY","SYNGENE","TCIEXP","TCNSBRANDS","TTKPRESTIG",
                   "TVTODAY","TV18BRDCST","TVSMOTOR","TAKE","TASTYBITE","TCS","TATAELXSI","TATAGLOBAL",
                   "TATAINVEST","TATAMTRDVR","TATAMOTORS","TATAPOWER","TATASTLBSL","TATASTEEL","TEAMLEASE",
                   "TECHM","TECHNOE","NIACL","RAMCOCEM","THERMAX","THYROCARE","TIMETECHNO","TIMKEN","TITAN",
                   "TORNTPHARM","TORNTPOWER","TRENT","TRIDENT","TRITURBINE","TIINDIA","UCOBANK","UFLEX","UPL",
                   "UJJIVAN","ULTRACEMCO","UNIONBANK","UBL","MCDOWELL-N","VGUARD","VMART","VIPIND","VRLLOG",
                   "VSTIND","WABAG","VAIBHAVGBL","VAKRANGEE","VTL","VARROC","VBL","VEDL","VENKEYS",
                   "VINATIORGA","IDEA","VOLTAS","WABCOINDIA","WELCORP","WELSPUNIND","WESTLIFE","WHIRLPOOL",
                   "WIPRO","WOCKPHARMA","YESBANK","ZEEL","ZENSARTECH","ZYDUSWELL","ECLERX","TATACONSUM",
                   "DEEPAKFERT","ADANIENT","CGPOWER","PENIND"]

NSEFnOList = ["BANKNIFTY","NIFTY","ACC","ADANIENT","ADANIPORTS","AMARAJABAT","AMBUJACEM","APOLLOHOSP",
              "APOLLOTYRE","ASHOKLEY","ASIANPAINT","AUROPHARMA","AXISBANK","BAJAJ-AUTO","BAJAJFINSV",
              "BAJFINANCE","BALKRISIND","BANDHANBNK","BANKBARODA","BATAINDIA","BEL","BERGEPAINT","BHARATFORG",
              "BHARTIARTL","BHEL","BIOCON","BOSCHLTD","BPCL","BRITANNIA","CADILAHC","CANBK","CENTURYTEX",
              "CHOLAFIN","CIPLA","COALINDIA","COLPAL","CONCOR","CUMMINSIND","DABUR","DIVISLAB","DLF",
              "DRREDDY","EICHERMOT","EQUITAS","ESCORTS","EXIDEIND","FEDERALBNK","GAIL","GLENMARK","GMRINFRA",
              "GODREJCP","GODREJPROP","GRASIM","HAVELLS","HCLTECH","HDFC","HDFCBANK","HDFCLIFE","HEROMOTOCO",
              "HINDALCO","HINDPETRO","HINDUNILVR","IBULHSGFIN","ICICIBANK","ICICIPRULI","IDEA","IDFCFIRSTB",
              "IGL","INDIGO","INDUSINDBK","INFRATEL","INFY","IOC","ITC","JINDALSTEL","JSWSTEEL","JUBLFOOD",
              "JUSTDIAL","KOTAKBANK","L&TFH","LICHSGFIN","LT","LUPIN","M&M","M&MFIN","MANAPPURAM","MARICO",
              "MARUTI","MCDOWELL-N","MFSL","MGL","MINDTREE","MOTHERSUMI","MRF","MUTHOOTFIN","NATIONALUM",
               "NAUKRI","NCC","NESTLEIND","NIITTECH","NMDC","NTPC","ONGC","PAGEIND","PEL","PETRONET","PFC",
               "PIDILITIND","PNB","POWERGRID","PVR","RAMCOCEM","RBLBANK","RECLTD","RELIANCE","SAIL","SBILIFE",
              "SBIN","SHREECEM","SIEMENS","SRF","SRTRANSFIN","SUNPHARMA","SUNTV","TATACHEM","TATACONSUM",
              "TATAMOTORS","TATAPOWER","TATASTEEL","TCS","TECHM","TITAN","TORNTPHARM","TORNTPOWER","TVSMOTOR",
              "UBL","UJJIVAN","ULTRACEMCO","UPL","VEDL","VOLTAS","WIPRO","ZEEL"]

NSE500Yahoo = ["3MINDIA.NS","ACC.NS","AIAENG.NS","APLAPOLLO.NS","AUBANK.NS","AARTIIND.NS","AAVAS.NS",
               "ABBOTINDIA.NS","ADANIGAS.NS","ADANIGREEN.NS","ADANIPORTS.NS","ADANIPOWER.NS","ADANITRANS.NS",
               "ABCAPITAL.NS","ABFRL.NS","ADVENZYMES.NS","AEGISCHEM.NS","AFFLE.NS","AJANTPHARM.NS",
               "AKZOINDIA.NS","APLLTD.NS","ALKEM.NS","ALLCARGO.NS","AMARAJABAT.NS","AMBER.NS","AMBUJACEM.NS",
               "APOLLOHOSP.NS","APOLLOTYRE.NS","ARVINDFASN.NS","ASAHIINDIA.NS","ASHOKLEY.NS","ASHOKA.NS",
               "ASIANPAINT.NS","ASTERDM.NS","ASTRAZEN.NS","ASTRAL.NS","ATUL.NS","AUROPHARMA.NS",
               "AVANTIFEED.NS","DMART.NS","AXISBANK.NS","BASF.NS","BEML.NS","BSE.NS","BAJAJ-AUTO.NS",
               "BAJAJCON.NS","BAJAJELEC.NS","BAJFINANCE.NS","BAJAJFINSV.NS","BAJAJHLDNG.NS","BALKRISIND.NS",
               "BALMLAWRIE.NS","BALRAMCHIN.NS","BANDHANBNK.NS","BANKBARODA.NS","BANKINDIA.NS","MAHABANK.NS",
               "BATAINDIA.NS","BAYERCROP.NS","BERGEPAINT.NS","BDL.NS","BEL.NS","BHARATFORG.NS","BHEL.NS",
               "BPCL.NS","BHARTIARTL.NS","INFRATEL.NS","BIOCON.NS","BIRLACORPN.NS","BSOFT.NS","BLISSGVS.NS",
               "BLUEDART.NS","BLUESTARCO.NS","BBTC.NS","BOMDYEING.NS","BOSCHLTD.NS","BRIGADE.NS",
               "BRITANNIA.NS","CARERATING.NS","CCL.NS","CESC.NS","CRISIL.NS","CADILAHC.NS","CANFINHOME.NS",
               "CANBK.NS","CAPLIPOINT.NS","CGCL.NS","CARBORUNIV.NS","CASTROLIND.NS","CEATLTD.NS",
               "CENTRALBK.NS","CDSL.NS","CENTURYPLY.NS","CERA.NS","CHALET.NS","CHAMBLFERT.NS",
               "CHENNPETRO.NS","CHOLAHLDNG.NS","CHOLAFIN.NS","CIPLA.NS","CUB.NS","COALINDIA.NS",
               "COCHINSHIP.NS","COLPAL.NS","CONCOR.NS","COROMANDEL.NS","CREDITACC.NS","CROMPTON.NS",
               "CUMMINSIND.NS","CYIENT.NS","DBCORP.NS","DCBBANK.NS","DCMSHRIRAM.NS","DLF.NS","DABUR.NS",
               "DALBHARAT.NS","DEEPAKNTR.NS","DELTACORP.NS","DHFL.NS","DBL.NS","DISHTV.NS","DCAL.NS",
               "DIVISLAB.NS","DIXON.NS","LALPATHLAB.NS","DRREDDY.NS","EIDPARRY.NS","EIHOTEL.NS",
               "EDELWEISS.NS","EICHERMOT.NS","ELGIEQUIP.NS","EMAMILTD.NS","ENDURANCE.NS","ENGINERSIN.NS",
               "EQUITAS.NS","ERIS.NS","ESCORTS.NS","ESSELPACK.NS","EXIDEIND.NS","FDC.NS","FEDERALBNK.NS",
               "FMGOETZE.NS","FINEORG.NS","FINCABLES.NS","FINPIPE.NS","FSL.NS","FORTIS.NS","FCONSUMER.NS",
               "FLFL.NS","FRETAIL.NS","GAIL.NS","GEPIL.NS","GET&D.NS","GHCL.NS","GMRINFRA.NS",
               "GALAXYSURF.NS","GARFIBRES.NS","GAYAPROJ.NS","GICRE.NS","GILLETTE.NS","GLAXO.NS",
               "GLENMARK.NS","GODFRYPHLP.NS","GODREJAGRO.NS","GODREJCP.NS","GODREJIND.NS","GODREJPROP.NS",
               "GRANULES.NS","GRAPHITE.NS","GRASIM.NS","GESHIP.NS","GREAVESCOT.NS","GRINDWELL.NS",
               "GUJALKALI.NS","GUJGASLTD.NS","GMDCLTD.NS","GNFC.NS","GPPL.NS","GSFC.NS","GSPL.NS",
               "GULFOILLUB.NS","HEG.NS","HCLTECH.NS","HDFCAMC.NS","HDFCBANK.NS","HDFCLIFE.NS","HFCL.NS",
               "HATSUN.NS","HAVELLS.NS","HEIDELBERG.NS","HERITGFOOD.NS","HEROMOTOCO.NS","HEXAWARE.NS",
               "HSCL.NS","HIMATSEIDE.NS","HINDALCO.NS","HAL.NS","HINDCOPPER.NS","HINDPETRO.NS",
               "HINDUNILVR.NS","HINDZINC.NS","HONAUT.NS","HUDCO.NS","HDFC.NS","ICICIBANK.NS","ICICIGI.NS",
               "ICICIPRULI.NS","ISEC.NS","ICRA.NS","IDBI.NS","IDFCFIRSTB.NS","IDFC.NS","IFBIND.NS","IFCI.NS",
               "IIFL.NS","IRB.NS","IRCON.NS","ITC.NS","ITDCEM.NS","ITI.NS","INDIACEM.NS","ITDC.NS",
               "IBULHSGFIN.NS","IBULISL.NS","IBREALEST.NS","IBVENTURES.NS","INDIAMART.NS","INDIANB.NS",
               "IEX.NS","INDHOTEL.NS","IOC.NS","IOB.NS","INDOSTAR.NS","IGL.NS","INDUSINDBK.NS","INFIBEAM.NS",
               "NAUKRI.NS","INFY.NS","INOXLEISUR.NS","INTELLECT.NS","INDIGO.NS","IPCALAB.NS","JBCHEPHARM.NS",
               "JKCEMENT.NS","JKLAKSHMI.NS","JKPAPER.NS","JKTYRE.NS","JMFINANCIL.NS","JSWENERGY.NS",
               "JSWSTEEL.NS","JAGRAN.NS","JAICORPLTD.NS","JISLJALEQS.NS","J&KBANK.NS","JAMNAAUTO.NS",
               "JINDALSAW.NS","JSLHISAR.NS","JSL.NS","JINDALSTEL.NS","JCHAC.NS","JUBLFOOD.NS","JUBILANT.NS",
               "JUSTDIAL.NS","JYOTHYLAB.NS","KPRMILL.NS","KEI.NS","KNRCON.NS","KPITTECH.NS","KRBL.NS",
               "KAJARIACER.NS","KALPATPOWR.NS","KANSAINER.NS","KTKBANK.NS","KARURVYSYA.NS","KSCL.NS",
               "KEC.NS","KENNAMET.NS","KIRLOSENG.NS","KOLTEPATIL.NS","KOTAKBANK.NS","L&TFH.NS","LTTS.NS",
               "LICHSGFIN.NS","LAXMIMACH.NS","LAKSHVILAS.NS","LTI.NS","LT.NS","LAURUSLABS.NS","LEMONTREE.NS",
               "LINDEINDIA.NS","LUPIN.NS","LUXIND.NS","MASFIN.NS","MMTC.NS","MOIL.NS","MRF.NS","MAGMA.NS",
               "MGL.NS","MAHSCOOTER.NS","MAHSEAMLES.NS","M&MFIN.NS","M&M.NS","MAHINDCIE.NS","MHRIL.NS",
               "MAHLOG.NS","MANAPPURAM.NS","MRPL.NS","MARICO.NS","MARUTI.NS","MFSL.NS","METROPOLIS.NS",
               "MINDTREE.NS","MINDACORP.NS","MINDAIND.NS","MIDHANI.NS","MOTHERSUMI.NS","MOTILALOFS.NS",
               "MPHASIS.NS","MCX.NS","MUTHOOTFIN.NS","NATCOPHARM.NS","NBCC.NS","NCC.NS","NESCO.NS","NHPC.NS",
               "NIITTECH.NS","NLCINDIA.NS","NMDC.NS","NTPC.NS","NH.NS","NATIONALUM.NS","NFL.NS",
               "NBVENTURES.NS","NAVINFLUOR.NS","NESTLEIND.NS","NETWORK18.NS","NILKAMAL.NS","NAM-INDIA.NS",
               "OBEROIRLTY.NS","ONGC.NS","OIL.NS","OMAXE.NS","OFSS.NS","ORIENTCEM.NS","ORIENTELEC.NS",
               "ORIENTREF.NS","PCJEWELLER.NS","PIIND.NS","PNBHOUSING.NS","PNCINFRA.NS","PTC.NS","PVR.NS",
               "PAGEIND.NS","PARAGMILK.NS","PERSISTENT.NS","PETRONET.NS","PFIZER.NS","PHILIPCARB.NS",
               "PHOENIXLTD.NS","PIDILITIND.NS","PEL.NS","POLYCAB.NS","PFC.NS","POWERGRID.NS","PRAJIND.NS",
               "PRESTIGE.NS","PRSMJOHNSN.NS","PGHL.NS","PGHH.NS","PNB.NS","QUESS.NS","RBLBANK.NS","RECLTD.NS",
               "RITES.NS","RADICO.NS","RVNL.NS","RAIN.NS","RAJESHEXPO.NS","RALLIS.NS","RCF.NS","RATNAMANI.NS",
               "RAYMOND.NS","REDINGTON.NS","RELAXO.NS","RELCAPITAL.NS","RELIANCE.NS","RELINFRA.NS",
               "RPOWER.NS","REPCOHOME.NS","RESPONIND.NS","SHK.NS","SBILIFE.NS","SJVN.NS","SKFINDIA.NS",
               "SRF.NS","SADBHAV.NS","SANOFI.NS","SCHAEFFLER.NS","SIS.NS","SFL.NS","SHILPAMED.NS",
               "SHOPERSTOP.NS","SHREECEM.NS","RENUKA.NS","SHRIRAMCIT.NS","SRTRANSFIN.NS","SIEMENS.NS",
               "SOBHA.NS","SOLARINDS.NS","SONATSOFTW.NS","SOUTHBANK.NS","SPANDANA.NS","SPICEJET.NS",
               "STARCEMENT.NS","SBIN.NS","SAIL.NS","STRTECH.NS","STAR.NS","SUDARSCHEM.NS","SPARC.NS",
               "SUNPHARMA.NS","SUNTV.NS","SUNCLAYLTD.NS","SUNDARMFIN.NS","SUNDRMFAST.NS","SUNTECK.NS",
               "SUPRAJIT.NS","SUPREMEIND.NS","SUZLON.NS","SWANENERGY.NS","SYMPHONY.NS","SYNGENE.NS",
               "TCIEXP.NS","TCNSBRANDS.NS","TTKPRESTIG.NS","TVTODAY.NS","TV18BRDCST.NS","TVSMOTOR.NS",
               "TAKE.NS","TASTYBITE.NS","TCS.NS","TATAELXSI.NS","TATACONSUM.NS","TATAINVEST.NS",
               "TATAMTRDVR.NS","TATAMOTORS.NS","TATAPOWER.NS","TATASTLBSL.NS","TATASTEEL.NS","TEAMLEASE.NS",
               "TECHM.NS","TECHNOE.NS","NIACL.NS","RAMCOCEM.NS","THERMAX.NS","THYROCARE.NS","TIMETECHNO.NS",
               "TIMKEN.NS","TITAN.NS","TORNTPHARM.NS","TORNTPOWER.NS","TRENT.NS","TRIDENT.NS","TRITURBINE.NS",
               "TIINDIA.NS","UCOBANK.NS","UFLEX.NS","UPL.NS","UJJIVAN.NS","ULTRACEMCO.NS","UNIONBANK.NS",
               "UBL.NS","MCDOWELL-N.NS","VGUARD.NS","VMART.NS","VIPIND.NS","VRLLOG.NS","VSTIND.NS","WABAG.NS",
               "VAIBHAVGBL.NS","VAKRANGEE.NS","VTL.NS","VARROC.NS","VBL.NS","VEDL.NS","VENKEYS.NS",
               "VINATIORGA.NS","IDEA.NS","VOLTAS.NS","WABCOINDIA.NS","WELCORP.NS","WELSPUNIND.NS",
               "WESTLIFE.NS","WHIRLPOOL.NS","WIPRO.NS","WOCKPHARMA.NS","YESBANK.NS","ZEEL.NS","ZENSARTECH.NS",
               "ZYDUSWELL.NS","ECLERX.NS","DEEPAKFERT.NS","ADANIENT.NS","CGPOWER.NS","PENIND.NS"]

Scriplist = ["RELIANCE", "HDFCBANK", "TATASTEEL", "TCS", "TATAMOTORS","TATAPOWER",
             "INDIGO","IDEA","OIL","AUROPHARMA","CIPLA","NIFTY","FEDERALBNK","AXISBANK",
             "ZEEL","HDFCLIFE","BHARTIARTL","BHEL","SAIL","JINDALSTEL","PNB",
             "HINDALCO","ADANIENT","BANKINDIA","MANAPPURAM","DEEPAKFERT","ITC","MOTHERSUMI","ICICIBANK",
             "BAJFINANCE","GREAVESCOT","CGPOWER","LUPIN","REDINGTON","CONCOR","EICHERMOT","RBLBANK"]

YahooScriplist = ["RELIANCE.NS", "HDFCBANK.NS", "TATASTEEL.NS", "TCS.NS", "TATAMOTORS.NS",
                  "TATAPOWER.NS","INDIGO.NS","IDEA.NS","OIL.NS","AUROPHARMA.NS","CIPLA.NS",
                  "FEDERALBNK.NS","AXISBANK.NS","ZEEL.NS","HDFCLIFE.NS","BHARTIARTL.NS",
                  "BHEL.NS","SAIL.NS","JINDALSTEL.NS","PNB.NS","HINDALCO.NS","ADANIENT.NS",
                  "BANKINDIA.NS","MANAPPURAM.NS","DEEPAKFERT.NS","ITC.NS","MOTHERSUMI.NS",
                  "ICICIBANK.NS","BAJFINANCE.NS","GREAVESCOT.NS","CGPOWER.NS","LUPIN.NS",
                  "REDINGTON.NS","CONCOR.NS","EICHERMOT.NS","RBLBANK.NS"]

OptionsScriplist = ["RELIANCE", "HDFCBANK", "TATASTEEL", "TCS", "TATAMOTORS","TATAPOWER",
             "INDIGO","IDEA","OIL","AUROPHARMA","CIPLA","NIFTY","FEDERALBNK","AXISBANK",
             "ZEEL","HDFCLIFE","BHARTIARTL","BHEL","SAIL","JINDALSTEL","PNB",
             "HINDALCO","ADANIENT","BANKINDIA","MANAPPURAM","ITC","MOTHERSUMI","ICICIBANK",
             "BAJFINANCE","LUPIN","REDINGTON","CONCOR","EICHERMOT","RBLBANK"]

FuturesScriplist = ["RELIANCE", "HDFCBANK", "TATASTEEL", "TCS", "TATAMOTORS","TATAPOWER",
             "INDIGO","IDEA","OIL","AUROPHARMA","CIPLA","NIFTY","FEDERALBNK","AXISBANK",
             "ZEEL","HDFCLIFE","BHARTIARTL","BHEL","SAIL","JINDALSTEL","PNB",
             "HINDALCO","ADANIENT","BANKINDIA","MANAPPURAM","ITC","MOTHERSUMI","ICICIBANK",
             "BAJFINANCE","LUPIN","REDINGTON","CONCOR","EICHERMOT","RBLBANK"]

FuturesIndexList = ["INDIGO"]#,"NIFTYIT","BANKNIFTY"]

#Check for file

def FindFeather(name, path):
    for root, dirs, files in os.walk(path):
        if name in files:
            return os.path.join(root, name)

def OHLCUpdate():
    for Scrip in NSE500ScripList:
        OHLCdf = None
        # Scrip = "SPICEJET"
        CurrentDate = datetime.date.today()
        OHLCFileName = Scrip + '_' + DailyOHLCFilePath
        #Read from feather
        if (FindFeather(OHLCFileName, './Datastore/')):
            OHLCdf = feather.read_feather('./Datastore/'+OHLCFileName)
            LastDateOHLCdf = ((OHLCdf.tail(1)).iloc[0]['Date'])
            LastDateOHLCdf += datetime.timedelta(days=1) #Added this to start from the next day - TBV
            if(CurrentDate > LastDateOHLCdf):
                #Update Dataframe
                FreshOHLC = None
                print(OHLCFileName + ' is being updated now from ' + LastDateOHLCdf.strftime("%Y-%m-%d %H:%M"))
                if Scrip == "BANKNIFTY" or Scrip == "NIFTY":
                    FreshOHLC = get_history(symbol=Scrip, start=LastDateOHLCdf, 
                            end=CurrentDate,index = True) #Accomodate INDIAVIX here
                    FreshOHLC.dropna(axis=0, how='any', inplace=True)
                else:    
                    FreshOHLC = get_history(symbol=Scrip, start=LastDateOHLCdf, 
                                            end=CurrentDate) #Accomodate INDIAVIX here
                
                FreshOHLC = FreshOHLC.sort_index()
                FreshOHLC.reset_index(level=0, inplace=True)
                OHLCdf = OHLCdf.append(FreshOHLC, ignore_index=True)
            else:
                print(OHLCFileName + ' is upto date')
                continue
        else:
            #Create Dataframe for new Scrip added
            OHLCStartDate = date(2005,1,1)
            print(OHLCFileName + ' is being created from ' + OHLCStartDate.strftime("%Y-%m-%d %H:%M"))
            
            if Scrip == "BANKNIFTY" or Scrip == "NIFTY":
                OHLCdf = get_history(symbol=Scrip, start=OHLCStartDate, 
            end=CurrentDate,index = True) #Accomodate INDIAVIX here
                OHLCdf.dropna(axis=0, how='any', inplace=True)
            else:  
                OHLCdf = get_history(symbol=Scrip, start=OHLCStartDate, 
                                 end=CurrentDate)
                
            OHLCdf = OHLCdf.sort_index()    
            OHLCdf.reset_index(level=0, inplace=True)# Required only for fresh df?

        #Update Feather
        if not OHLCdf.empty:
            feather.write_feather(OHLCdf, './Datastore/'+OHLCFileName)

def FXPEUpdate():
    FXPEdf = None
    CurrentDate = datetime.date.today()
    FileList = [FXHistory,PEHistory]
    #Read from feather
    for f in FileList:
        if (FindFeather(f, './Datastore/')):
            FXPEdf = feather.read_feather('./Datastore/'+f)
            LastDateFXPEdf = ((FXPEdf.tail(1)).iloc[0]['Date'])
            LastDateFXPEdf += datetime.timedelta(days=1) #Added this to start from the next day - TBV
            if(CurrentDate > LastDateFXPEdf):
                #Update Dataframe
                FreshFXPE = None
                print(f + ' is being updated now from ' + LastDateFXPEdf.strftime("%Y-%m-%d %H:%M"))
                if f == FXHistory:
                    FreshFXPE = get_rbi_ref_history(LastDateFXPEdf, CurrentDate)
                else:    
                    FreshFXPE = get_index_pe_history(symbol="NIFTY",
                                                    start=LastDateFXPEdf,
                                                    end=CurrentDate)
                
                FreshFXPE = FreshFXPE.sort_index()    
                FreshFXPE.reset_index(level=0, inplace=True)
                FXPEdf = FXPEdf.append(FreshFXPE, ignore_index=True)
            else:
                print(f + ' is upto date')
                continue
        else:
            #Create Dataframe for new Scrip added
            OHLCStartDate = date(2000,1,1)
            print(f + ' is being created from ' + OHLCStartDate.strftime("%Y-%m-%d %H:%M"))
            
            if f == FXHistory:
                FXPEdf = get_rbi_ref_history(OHLCStartDate, CurrentDate)
            else:  
                FXPEdf = get_index_pe_history(symbol="NIFTY", start=OHLCStartDate,
                                end=CurrentDate)
                
            FXPEdf = FXPEdf.sort_index()    
            FXPEdf.reset_index(level=0, inplace=True)# Required only for fresh df?
    
        #Update Feather
        if not FXPEdf.empty:
            feather.write_feather(FXPEdf, './Datastore/'+f)

def FullFuturesUpdate():
    for Scrip in NSEFnOList: #FuturesIndexList:#
        # Scrip = "NIFTY"
        CurrentDate = datetime.date.today()
        CurrentMonth = CurrentDate.month
        CurrentYear = CurrentDate.year
        FullFuturesFileName = Scrip + '_' + FullFuturesFilePath
        #Read from feather
        if (FindFeather(FullFuturesFileName, './Datastore')):
            FullFuturesdf = feather.read_feather('./Datastore/'+FullFuturesFileName)
            
            if FullFuturesdf.empty:
                continue
            
            LastDateFullFutures = ((FullFuturesdf.tail(1)).iloc[0]['Date'])
            FuturesExpiry = ((FullFuturesdf.tail(1)).iloc[0]['Expiry'])
            
            if LastDateFullFutures == FuturesExpiry:
                LastDateFullFutures += relativedelta(months=1)
                LastDateFullFutures = LastDateFullFutures.replace(day=1)    
            else:
                LastDateFullFutures += datetime.timedelta(days=1) #Added this to start from the next day - TBV
                
            LastYearFullFutures = LastDateFullFutures.year
            LastMonthFullFutures = LastDateFullFutures.month
            ExpiryMonth = LastMonthFullFutures
            ExpiryYear = LastYearFullFutures
            if(CurrentDate > LastDateFullFutures):
                #Update Dataframe
                print(FullFuturesFileName + ' is being updated from' + LastDateFullFutures.strftime("%Y-%m-%d %H:%M") )
                if(CurrentMonth == LastMonthFullFutures): #works unless you don't update for a year
                    NextExpiryDate = CurrentDate
                    FullFuturesExpirydf = pd.DataFrame()
                    for x in range(1):
                        try:
                            if Scrip == "BANKNIFTY" or Scrip == "NIFTY":
                                FreshFullFutures = get_history(symbol=Scrip, start=LastDateFullFutures, 
                                                end=CurrentDate,index = True, futures=True,
                                                expiry_date=max(get_expiry_date(ExpiryYear,ExpiryMonth)))
                            else:
                                FreshFullFutures = get_history(symbol=Scrip, start=LastDateFullFutures, 
                                                end=CurrentDate,futures=True,
                                                expiry_date=max(get_expiry_date(ExpiryYear,ExpiryMonth)))
                        except:
                            print(Scrip," :failed to fetch data...retrying" + NextExpiryDate.strftime("%Y-%m-%d %H:%M"))
                        NextExpiryDate = NextExpiryDate + relativedelta(months=1)
                        ExpiryMonth = NextExpiryDate.month
                        ExpiryYear = NextExpiryDate.year
                        FullFuturesExpirydf = FullFuturesExpirydf.append(FreshFullFutures)

					#Attempt to add mid month and far month in addition to existing near month FullFutures    
                    FullFuturesExpirydf = FullFuturesExpirydf.sort_index()
                    FullFuturesExpirydf.reset_index(level=0, inplace=True)
                    FullFuturesdf = FullFuturesdf.append(FullFuturesExpirydf, ignore_index=True)                    
					################################################################
                    
                    print(FullFuturesFileName + ' is being updated for same month' + 
                          LastDateFullFutures.strftime("%Y-%m-%d %H:%M"))
                else:
                    FreshFullFutures = None
                    LastDateFullFutures = ((FullFuturesdf.tail(1)).iloc[0]['Date'])
                    FuturesExpiry = ((FullFuturesdf.tail(1)).iloc[0]['Expiry'])
                    
                    if LastDateFullFutures == FuturesExpiry:
                        LastDateFullFutures += relativedelta(months=1)
                        LastDateFullFutures = LastDateFullFutures.replace(day=1)    
                    else:
                        LastDateFullFutures += datetime.timedelta(days=1)

                    while True:
                        LastYearFullFutures = LastDateFullFutures.year
                        LastMonthFullFutures = LastDateFullFutures.month
                        FullFuturesExpirydf = pd.DataFrame()
                        NextExpiryDate = LastDateFullFutures
                        ExpiryMonth = LastMonthFullFutures
                        ExpiryYear = LastYearFullFutures
                        
                        for x in range(1):
                            try:
                                if Scrip == "BANKNIFTY" or Scrip == "NIFTY":
                                    FreshFullFutures = get_history(symbol=Scrip, start=LastDateFullFutures, 
                                    end=LastDateFullFutures + relativedelta(day=31),index = True, futures=True,
                                    expiry_date=max(get_expiry_date(ExpiryYear,ExpiryMonth)))
                                else:
                                    FreshFullFutures = get_history(symbol=Scrip, start=LastDateFullFutures, 
                                    end=LastDateFullFutures + relativedelta(day=31),futures=True,
                                    expiry_date=max(get_expiry_date(ExpiryYear,ExpiryMonth)))
                            except:
                                print(Scrip," :failed to fetch data...retrying" + NextExpiryDate.strftime("%Y-%m-%d %H:%M"))
                            NextExpiryDate = NextExpiryDate + relativedelta(months=1)
                            ExpiryMonth = NextExpiryDate.month
                            ExpiryYear = NextExpiryDate.year
                            if FreshFullFutures.empty:
                                continue
                            FullFuturesExpirydf = FullFuturesExpirydf.append(FreshFullFutures)

                        LastDateFullFutures += relativedelta(months=1)
                        LastDateFullFutures = LastDateFullFutures.replace(day=1)
                        
                        # if FullFuturesExpirydf.empty:
                        #     continue                        

                        FullFuturesExpirydf = FullFuturesExpirydf.sort_index()
                        FullFuturesExpirydf.reset_index(level=0, inplace=True)
                        FullFuturesdf = FullFuturesdf.append(FullFuturesExpirydf, ignore_index=True)
						
                        print(FullFuturesFileName + ' is being updated for '
                              + LastDateFullFutures.strftime("%Y-%m-%d %H:%M"))
                        if(LastDateFullFutures > CurrentDate):
                            break
            else:
                print(FullFuturesFileName + 'is upto date')
                continue
        else:
            #Create Dataframe for new Scrip added
            FullFuturesExpirydf = pd.DataFrame()
            FullFuturesdf = pd.DataFrame()
            FullFuturesStartDate = date(2011,1,1)
            LastDateFullFutures = FullFuturesStartDate
            print(FullFuturesFileName + ' is being created from' + FullFuturesStartDate.strftime("%Y-%m-%d %H:%M")) 

            NextExpiryDate = LastDateFullFutures
            ExpiryMonth = LastDateFullFutures.month
            ExpiryYear = LastDateFullFutures.year
            
            for x in range(1):
                try:
                    if Scrip == "BANKNIFTY" or Scrip == "NIFTY":
                        FreshFullFutures = get_history(symbol=Scrip, start=FullFuturesStartDate, 
                                                end=FullFuturesStartDate + relativedelta(day=31),index = True, futures=True,
                                                expiry_date=max(get_expiry_date(ExpiryYear,ExpiryMonth)))
                    else:
                        FreshFullFutures = get_history(symbol=Scrip, start=FullFuturesStartDate, 
                                                end=FullFuturesStartDate + relativedelta(day=31),futures=True,
                                                expiry_date=max(get_expiry_date(ExpiryYear,ExpiryMonth)))
                except:
                    print(Scrip," :failed to fetch data...retrying" + NextExpiryDate.strftime("%Y-%m-%d %H:%M"))
                NextExpiryDate = NextExpiryDate + relativedelta(months=1)
                ExpiryMonth = NextExpiryDate.month
                ExpiryYear = NextExpiryDate.year
                if FreshFullFutures.empty:
                    continue
                
                FullFuturesExpirydf = FullFuturesExpirydf.append(FreshFullFutures)   
          
            if not FullFuturesExpirydf.empty:
                FullFuturesdf = FullFuturesExpirydf.sort_index()
                FullFuturesdf.reset_index(level=0, inplace=True) # Required for any new data fetch
                # LastDateFullFutures = ((FullFuturesdf.tail(1)).iloc[0]['Date'])
                
            LastDateFullFutures += relativedelta(months=1)
            LastDateFullFutures = LastDateFullFutures.replace(day = 1) #Start from the month beginning
            LastYearFullFutures = LastDateFullFutures.year
            LastMonthFullFutures = LastDateFullFutures.month
            NextExpiryDate = LastDateFullFutures
            ExpiryMonth = LastMonthFullFutures
            ExpiryYear = LastYearFullFutures
            #now to fill it up - TBD - can be done recursively            
            if(CurrentDate > LastDateFullFutures):
                #Update Dataframe
                print(FullFuturesFileName + ' is being updated from ' + LastDateFullFutures.strftime("%Y-%m-%d %H:%M"))
                while True:
                    FullFuturesExpirydf = pd.DataFrame()
                    for x in range(1):
                        try:
                            if Scrip == "BANKNIFTY" or Scrip == "NIFTY":
                                FreshFullFutures = get_history(symbol=Scrip, start=LastDateFullFutures, 
                                                end=LastDateFullFutures+ relativedelta(day=31),index = True, futures=True,
                                                expiry_date=max(get_expiry_date(ExpiryYear,ExpiryMonth)))
                            else:
                                FreshFullFutures = get_history(symbol=Scrip, start=LastDateFullFutures, 
                                                end=LastDateFullFutures+ relativedelta(day=31),futures=True,
                                                expiry_date=max(get_expiry_date(ExpiryYear,ExpiryMonth)))
                        except:
                            print(Scrip," :failed to fetch data...retrying" + NextExpiryDate.strftime("%Y-%m-%d %H:%M"))    
                            
                        NextExpiryDate = NextExpiryDate + relativedelta(months=1)
                        ExpiryMonth = NextExpiryDate.month
                        ExpiryYear = NextExpiryDate.year
                        if FreshFullFutures.empty:
                            continue
                        FullFuturesExpirydf = FullFuturesExpirydf.append(FreshFullFutures) 
                        
                    LastDateFullFutures += relativedelta(months=1)
                    LastDateFullFutures = LastDateFullFutures.replace(day = 1)  
                    LastYearFullFutures = LastDateFullFutures.year
                    LastMonthFullFutures = LastDateFullFutures.month
                    
                    NextExpiryDate = LastDateFullFutures
                    ExpiryMonth = NextExpiryDate.month
                    ExpiryYear = NextExpiryDate.year
                    print(FullFuturesFileName + ' is being updated for ' + LastDateFullFutures.strftime("%Y-%m-%d %H:%M"))

                    #Ideally it is required to prevent empty frame append but including this
                    #results in infinite loop as dates increment without limit
                    # if FullFuturesExpirydf.empty:
                    #     continue

                    FullFuturesExpirydf = FullFuturesExpirydf.sort_index()
                    #Not a good idea to check for empty frame here. Filters out newer Scrips                       
                    FullFuturesExpirydf.reset_index(level=0, inplace=True)
                    FullFuturesdf = FullFuturesdf.append(FullFuturesExpirydf, ignore_index=True)
                    
                    if(LastDateFullFutures > CurrentDate):
                        break
        
        #Update Feather
        if not FullFuturesdf.empty:
            FullFuturesdf = FullFuturesdf.drop_duplicates(subset=['Date', 'Expiry'], keep="first")
            feather.write_feather(FullFuturesdf, './Datastore/'+ FullFuturesFileName)


def MonthlyFuturesUpdate():
    for Scrip in NSEFnOList:
        # Scrip = "NIFTY"
        Futuresdf = None
        CurrentDate = datetime.date.today()
        CurrentMonth = CurrentDate.month
        CurrentYear = CurrentDate.year
        FuturesFileName = Scrip + '_' + MonthlyFuturesFilePath
        #Read from feather
        if (FindFeather(FuturesFileName, './Datastore')):
            Futuresdf = feather.read_feather('./Datastore/'+FuturesFileName)
            
            if Futuresdf.empty:
                continue
            
            LastDateFutures = ((Futuresdf.tail(1)).iloc[0]['Date'])
            FuturesExpiry = ((Futuresdf.tail(1)).iloc[0]['Expiry'])
            
            if LastDateFutures == FuturesExpiry:
                LastDateFutures += relativedelta(months=1)
                LastDateFutures = LastDateFutures.replace(day=1)    
            else:
                LastDateFutures += datetime.timedelta(days=1) #Added this to start from the next day - TBV
                
            LastYearFutures = LastDateFutures.year
            LastMonthFutures = LastDateFutures.month
            if(CurrentDate > LastDateFutures):
                #Update Dataframe
                print(FuturesFileName + ' is being updated from' + LastDateFutures.strftime("%Y-%m-%d %H:%M") )
                if(CurrentMonth == LastMonthFutures): #works unless you don't update for a year

                    if Scrip == "BANKNIFTY" or Scrip == "NIFTY":
                        FreshFutures = get_history(symbol=Scrip, start=LastDateFutures, 
                                        end=CurrentDate,index = True, futures=True,
                                        expiry_date=max(get_expiry_date(CurrentYear,CurrentMonth)))
                    else:
                        FreshFutures = get_history(symbol=Scrip, start=LastDateFutures, 
                                        end=CurrentDate,futures=True,
                                        expiry_date=max(get_expiry_date(CurrentYear,CurrentMonth)))
                    
                    FreshFutures = FreshFutures.sort_index()
                    FreshFutures.reset_index(level=0, inplace=True)
                    Futuresdf = Futuresdf.append(FreshFutures, ignore_index=True)                    
                    
                    print(FuturesFileName + ' is being updated for same month' + 
                          LastDateFutures.strftime("%Y-%m-%d %H:%M"))
                else:
                    FreshFutures = None
                    LastDateFutures = ((Futuresdf.tail(1)).iloc[0]['Date'])
                    FuturesExpiry = ((Futuresdf.tail(1)).iloc[0]['Expiry'])
                    
                    if LastDateFutures == FuturesExpiry:
                        LastDateFutures += relativedelta(months=1)
                        LastDateFutures = LastDateFutures.replace(day=1)    
                    else:
                        LastDateFutures += datetime.timedelta(days=1)
                
                    while True:
                        LastYearFutures = LastDateFutures.year
                        LastMonthFutures = LastDateFutures.month
                        
                        if Scrip == "BANKNIFTY" or Scrip == "NIFTY":
                            FreshFutures = get_history(symbol=Scrip, start=LastDateFutures, 
                                        end=LastDateFutures + relativedelta(day=31),index = True, futures=True,
                                        expiry_date=max(get_expiry_date(LastYearFutures,LastMonthFutures)))
                        else:
                            FreshFutures = get_history(symbol=Scrip, start=LastDateFutures, 
                                        end=LastDateFutures + relativedelta(day=31),futures=True,
                                        expiry_date=max(get_expiry_date(LastYearFutures,LastMonthFutures)))
                        
                        FreshFutures = FreshFutures.sort_index()
                        FreshFutures.reset_index(level=0, inplace=True)
                        Futuresdf = Futuresdf.append(FreshFutures, ignore_index=True)
                        print(FuturesFileName + ' is being updated for '
                              + LastDateFutures.strftime("%Y-%m-%d %H:%M"))
                        LastDateFutures += relativedelta(months=1)
                        LastDateFutures = LastDateFutures.replace(day=1)
                        if(LastDateFutures > CurrentDate):
                            break
            else:
                print(FuturesFileName + 'is upto date')
                continue
        else:
            #Create Dataframe for new Scrip added
            FuturesStartDate = date(2011,1,1)
            LastDateFutures = FuturesStartDate
            print(FuturesFileName + ' is being created from' + FuturesStartDate.strftime("%Y-%m-%d %H:%M")) 
            
            if Scrip == "BANKNIFTY" or Scrip == "NIFTY":
                Futuresdf = get_history(symbol=Scrip, start=FuturesStartDate, 
                                        end=FuturesStartDate + relativedelta(day=31),index = True, futures=True,
                                        expiry_date=max(get_expiry_date(FuturesStartDate.year,FuturesStartDate.month)))
            else:
                Futuresdf = get_history(symbol=Scrip, start=FuturesStartDate, 
                                        end=FuturesStartDate + relativedelta(day=31),futures=True,
                                        expiry_date=max(get_expiry_date(FuturesStartDate.year,FuturesStartDate.month)))
            
            Futuresdf = Futuresdf.sort_index()
            Futuresdf.reset_index(level=0, inplace=True) # Required for any new data fetch
            
            if not Futuresdf.empty:
                LastDateFutures = ((Futuresdf.tail(1)).iloc[0]['Date'])
                
            LastDateFutures += relativedelta(months=1)
            LastDateFutures = LastDateFutures.replace(day = 1) #Start from the month beginning
            LastYearFutures = LastDateFutures.year
            LastMonthFutures = LastDateFutures.month
            #now to fill it up - TBD - can be done recursively            
            if(CurrentDate > LastDateFutures):
                #Update Dataframe
                print(FuturesFileName + ' is being updated from ' + LastDateFutures.strftime("%Y-%m-%d %H:%M"))
                while True:
                    FreshFutures = None
                    
                    if Scrip == "BANKNIFTY" or Scrip == "NIFTY":
                        FreshFutures = get_history(symbol=Scrip, start=LastDateFutures, 
                                        end=LastDateFutures+ relativedelta(day=31),index = True, futures=True,
                                        expiry_date=max(get_expiry_date(LastYearFutures,LastMonthFutures)))
                    else:
                        FreshFutures = get_history(symbol=Scrip, start=LastDateFutures, 
                                        end=LastDateFutures+ relativedelta(day=31),futures=True,
                                        expiry_date=max(get_expiry_date(LastYearFutures,LastMonthFutures)))
                    
                    FreshFutures = FreshFutures.sort_index()
                    #Not a good idea to check for empty frame here. Filters out newer Scrips                       
                    FreshFutures.reset_index(level=0, inplace=True)
                    Futuresdf = Futuresdf.append(FreshFutures, ignore_index=True)
                    print(FuturesFileName + ' is being updated for ' + LastDateFutures.strftime("%Y-%m-%d %H:%M"))
                    LastDateFutures += relativedelta(months=1)
                    LastDateFutures = LastDateFutures.replace(day = 1)
                    LastYearFutures = LastDateFutures.year
                    LastMonthFutures = LastDateFutures.month
                    if(LastDateFutures > CurrentDate):
                        break
        
        #Update Feather
        if not Futuresdf.empty:
            feather.write_feather(Futuresdf, './Datastore/'+ FuturesFileName)

def RefineOptionsdf(DF):
    df = DF.copy()
    
    if 'Option Type' in df.columns:
        df.rename(columns={'Option Type': 'Option type'}, inplace=True)
    
    if 'Last' in df.columns:
        df.rename(columns={'Last': 'LTP'}, inplace=True)
        
    if 'Number of Contracts' in df.columns:
        df.rename(columns={'Number of Contracts': 'No. of contracts'}, inplace=True)
        
    if 'Turnover' in df.columns:
        df.rename(columns={'Turnover': 'Turnover in Lacs'}, inplace=True)
        
    if 'Premium Turnover' in df.columns:
        df.rename(columns={'Premium Turnover': 'Premium Turnover in Lacs'}, inplace=True)     
        
    if 'Open Interest' in df.columns:
        df.rename(columns={'Open Interest': 'Open Int'}, inplace=True)
        
    if 'Underlying' in df.columns:
        df.rename(columns={'Underlying': 'Underlying Value'}, inplace=True)
        
    df[["Strike Price","Open","High","Low","Close","Premium Turnover in Lacs","Change in OI",
                "Underlying Value","LTP","No. of contracts","Turnover in Lacs","Open Int","Change in OI","Underlying Value"]] = df[["Strike Price","Open","High","Low","Close","Premium Turnover in Lacs","Change in OI",
                "Underlying Value","LTP","No. of contracts","Turnover in Lacs","Open Int","Change in OI","Underlying Value"]].apply(pd.to_numeric,errors='coerce')       
    df[["Date","Expiry"]] = df[["Date","Expiry"]].apply(pd.to_datetime, format='%d-%b-%Y')
    df['Date'] = df['Date'].dt.date
    df['Expiry'] = df['Expiry'].dt.date
    
    return df
        
def MonthlyOptionsUpdate():
    for Scrip in NSEFnOList:
        # Scrip = "BANKNIFTY"
        Optionsdf = None
        CurrentDate = datetime.date.today()
        CurrentMonth = CurrentDate.month
        CurrentYear = CurrentDate.year
        OptionsFileName = Scrip + '_' + MonthlyOptionsFilePath
        #Read from feather
        if (FindFeather(OptionsFileName, './Datastore')):
            Optionsdf = feather.read_feather('./Datastore/'+OptionsFileName)
            #This has been run on all Option files as on 3rd September, 2020. Not needed anymore.
            # Optionsdf['Date'] = Optionsdf['Date'].dt.date 
            # Optionsdf['Expiry'] = Optionsdf['Expiry'].dt.date

            if Optionsdf.empty:
                continue
            
            LastDateOptions = ((Optionsdf.tail(1)).iloc[0]['Date'])
            OptionsExpiry = ((Optionsdf.tail(1)).iloc[0]['Expiry'])
            
            if LastDateOptions == OptionsExpiry:
                LastDateOptions += relativedelta(months=1)
                LastDateOptions = LastDateOptions.replace(day=1)    
            else:
                LastDateOptions += datetime.timedelta(days=1)            
            
            # LastDateOptions += datetime.timedelta(days=1) #Added this to start from the next day - TBV
            LastYearOptions = LastDateOptions.year
            LastMonthOptions = LastDateOptions.month
            if(CurrentDate > LastDateOptions):
                #Update Dataframe

                if(CurrentMonth == LastMonthOptions): #works unless you don't update for a year
                    print(OptionsFileName + ' is being updated from' + LastDateOptions.strftime("%Y-%m-%d %H:%M") )                    
                    if Scrip == "BANKNIFTY" or Scrip == "NIFTY":
                        FreshOptions = get_history(symbol=Scrip, start=LastDateOptions, 
                                        end=CurrentDate,index = True, option_type="CE",
                                        expiry_date=max(get_expiry_date(CurrentYear,CurrentMonth)),
                                        custom_parsing=True)
                    else:
                        FreshOptions = get_history(symbol=Scrip, start=LastDateOptions, 
                                        end=CurrentDate,option_type="CE",
                                        expiry_date=max(get_expiry_date(CurrentYear,CurrentMonth)),
                                        custom_parsing=True)
                    
                    if not FreshOptions.empty:
                        FreshOptions = RefineOptionsdf(FreshOptions)
                        Optionsdf = Optionsdf.append(FreshOptions, ignore_index=True)
                    
                    FreshOptions = None
                    if Scrip == "BANKNIFTY" or Scrip == "NIFTY":
                        FreshOptions = get_history(symbol=Scrip, start=LastDateOptions, 
                                        end=CurrentDate,index = True, option_type="PE",
                                        expiry_date=max(get_expiry_date(CurrentYear,CurrentMonth)),
                                        custom_parsing=True)
                    else:
                        FreshOptions = get_history(symbol=Scrip, start=LastDateOptions, 
                                        end=CurrentDate,option_type="PE",
                                        expiry_date=max(get_expiry_date(CurrentYear,CurrentMonth)),
                                        custom_parsing=True)
                    
                    if not FreshOptions.empty:
                        FreshOptions = RefineOptionsdf(FreshOptions)
                        Optionsdf = Optionsdf.append(FreshOptions, ignore_index=True)
                    
                    Optionsdf = Optionsdf.sort_values(by=['Date','Option type'])
                    print(OptionsFileName + ' is being updated for same month' + 
                          LastDateOptions.strftime("%Y-%m-%d %H:%M"))
                else:
                    FreshOptions = None
                    LastDateOptions = ((Optionsdf.tail(1)).iloc[0]['Date'])
                    OptionsExpiry = ((Optionsdf.tail(1)).iloc[0]['Expiry'])
                    
                    if LastDateOptions == OptionsExpiry:
                        LastDateOptions += relativedelta(months=1)
                        LastDateOptions = LastDateOptions.replace(day=1)    
                    else:
                        LastDateOptions += datetime.timedelta(days=1)
                        
                    while True:
                        LastYearOptions = LastDateOptions.year
                        LastMonthOptions = LastDateOptions.month
                        
                        if Scrip == "BANKNIFTY" or Scrip == "NIFTY":
                            FreshOptions = get_history(symbol=Scrip, start=LastDateOptions, 
                                        end=LastDateOptions + relativedelta(day=31),index = True, option_type="CE",
                                        expiry_date=max(get_expiry_date(LastYearOptions,LastMonthOptions)),
                                        custom_parsing=True)
                        else:
                            FreshOptions = get_history(symbol=Scrip, start=LastDateOptions, 
                                        end=LastDateOptions + relativedelta(day=31),option_type="CE",
                                        expiry_date=max(get_expiry_date(LastYearOptions,LastMonthOptions)),
                                        custom_parsing=True)
                            
                        if not FreshOptions.empty:
                            FreshOptions = RefineOptionsdf(FreshOptions)    
                            Optionsdf = Optionsdf.append(FreshOptions, ignore_index=True)
                        
                        FreshOptions = None
                        if Scrip == "BANKNIFTY" or Scrip == "NIFTY":
                            FreshOptions = get_history(symbol=Scrip, start=LastDateOptions, 
                                        end=LastDateOptions + relativedelta(day=31),index = True, option_type="PE",
                                        expiry_date=max(get_expiry_date(LastYearOptions,LastMonthOptions)),
                                        custom_parsing=True)
                        else:
                            FreshOptions = get_history(symbol=Scrip, start=LastDateOptions, 
                                        end=LastDateOptions + relativedelta(day=31),option_type="PE",
                                        expiry_date=max(get_expiry_date(LastYearOptions,LastMonthOptions)),
                                        custom_parsing=True)
                            
                        if not FreshOptions.empty:
                            FreshOptions = RefineOptionsdf(FreshOptions)    
                            Optionsdf = Optionsdf.append(FreshOptions, ignore_index=True)                        
                        
                        LastDateOptions += relativedelta(months=1)
                        LastDateOptions = LastDateOptions.replace(day=1)
                        if(LastDateOptions > CurrentDate):
                            break
                        
                    print(OptionsFileName + ' is being updated for '+ LastDateOptions.strftime("%Y-%m-%d %H:%M"))    
                    Optionsdf = Optionsdf.sort_values(by=['Date','Option type'])
            else:
                print(OptionsFileName + 'is upto date')
                continue
        else:
            #Create Dataframe for new Scrip added
            OptionsStartDate = date(2011,1,1)
            LastDateOptions = OptionsStartDate
            print(OptionsFileName + ' is being created from' + OptionsStartDate.strftime("%Y-%m-%d %H:%M")) 
            
            if Scrip == "BANKNIFTY" or Scrip == "NIFTY":
                Optionsdf = get_history(symbol=Scrip, start=OptionsStartDate, 
                                        end=OptionsStartDate + relativedelta(day=31),index = True, option_type="CE",
                                        expiry_date=max(get_expiry_date(OptionsStartDate.year,OptionsStartDate.month)),
                                        custom_parsing=True)
            else:
                Optionsdf = get_history(symbol=Scrip, start=OptionsStartDate, 
                                        end=OptionsStartDate + relativedelta(day=31),option_type="CE",
                                        expiry_date=max(get_expiry_date(OptionsStartDate.year,OptionsStartDate.month)),
                                        custom_parsing=True)

            if not Optionsdf.empty:
                Optionsdf = RefineOptionsdf(Optionsdf)   
                # LastDateOptions = ((Optionsdf.tail(1)).iloc[0]['Date']).date()
                
            if Scrip == "BANKNIFTY" or Scrip == "NIFTY":
                PEOptionsdf = get_history(symbol=Scrip, start=OptionsStartDate, 
                                        end=OptionsStartDate + relativedelta(day=31),index = True, option_type="PE",
                                        expiry_date=max(get_expiry_date(OptionsStartDate.year,OptionsStartDate.month)),
                                        custom_parsing=True)
            else:
                PEOptionsdf = get_history(symbol=Scrip, start=OptionsStartDate, 
                                        end=OptionsStartDate + relativedelta(day=31),option_type="PE",
                                        expiry_date=max(get_expiry_date(OptionsStartDate.year,OptionsStartDate.month)),
                                        custom_parsing=True)

            if not PEOptionsdf.empty:
                PEOptionsdf = RefineOptionsdf(PEOptionsdf)
                Optionsdf = Optionsdf.append(PEOptionsdf, ignore_index=True) 
                LastDateOptions = ((Optionsdf.tail(1)).iloc[0]['Date'])

                
            LastDateOptions += relativedelta(months=1)
            LastDateOptions = LastDateOptions.replace(day = 1) #Start from the month beginning
            LastYearOptions = LastDateOptions.year
            LastMonthOptions = LastDateOptions.month
            #now to fill it up - TBD - can be done recursively            
            if(CurrentDate > LastDateOptions):
                #Update Dataframe
                print(OptionsFileName + ' is being updated from ' + LastDateOptions.strftime("%Y-%m-%d %H:%M"))
                while True:
                    FreshOptions = None
                    if Scrip == "BANKNIFTY" or Scrip == "NIFTY":
                        FreshOptions = get_history(symbol=Scrip, start=LastDateOptions, 
                                        end=LastDateOptions+ relativedelta(day=31),index = True, option_type="CE",
                                        expiry_date=max(get_expiry_date(LastYearOptions,LastMonthOptions)), 
                                        custom_parsing=True)
                    else:
                        FreshOptions = get_history(symbol=Scrip, start=LastDateOptions, 
                                        end=LastDateOptions+ relativedelta(day=31),option_type="CE",
                                        expiry_date=max(get_expiry_date(LastYearOptions,LastMonthOptions)), 
                                        custom_parsing=True)
                    
                    if not FreshOptions.empty:
                        FreshOptions = RefineOptionsdf(FreshOptions)    
                        Optionsdf = Optionsdf.append(FreshOptions, ignore_index=True)

                    FreshOptions = None
                    if Scrip == "BANKNIFTY" or Scrip == "NIFTY":
                        FreshOptions = get_history(symbol=Scrip, start=LastDateOptions, 
                                        end=LastDateOptions+ relativedelta(day=31),index = True, option_type="PE",
                                        expiry_date=max(get_expiry_date(LastYearOptions,LastMonthOptions)), 
                                        custom_parsing=True)
                    else:
                        FreshOptions = get_history(symbol=Scrip, start=LastDateOptions, 
                                        end=LastDateOptions+ relativedelta(day=31),option_type="PE",
                                        expiry_date=max(get_expiry_date(LastYearOptions,LastMonthOptions)), 
                                        custom_parsing=True)
                    
                    if not FreshOptions.empty:
                        FreshOptions = RefineOptionsdf(FreshOptions)    
                        Optionsdf = Optionsdf.append(FreshOptions, ignore_index=True)
                        
                    print(OptionsFileName + ' is being updated for ' + LastDateOptions.strftime("%Y-%m-%d %H:%M"))
                    LastDateOptions += relativedelta(months=1)
                    LastDateOptions = LastDateOptions.replace(day = 1)
                    LastYearOptions = LastDateOptions.year
                    LastMonthOptions = LastDateOptions.month
                    if(LastDateOptions > CurrentDate):
                        break
                    
                Optionsdf = Optionsdf.sort_values(by=['Date','Option type'])
        #Update Feather
        if not Optionsdf.empty:
            feather.write_feather(Optionsdf, './Datastore/'+ OptionsFileName)

def IntradayUpdate():
    for Scrip in NSE500Yahoo:
        Intradaydf = None
        CurrentDate = datetime.date.today()
        IntradayFileName = Scrip + '_' + IntradayFilePath

        #Read from feather
        if (FindFeather(IntradayFileName, './Datastore/')):
            Intradaydf = feather.read_feather('./Datastore/'+ IntradayFileName)
            WeekStartDate = ((Intradaydf.tail(1)).iloc[0]['Datetime'])
            WeekStartDate += datetime.timedelta(days=1) #One time adjustment
            PlusOneWeek = WeekStartDate + datetime.timedelta(weeks=+1)
            if(CurrentDate > WeekStartDate):
                #Update Dataframe
                while True:
                    FreshIntradaydf = None
                    WeekStartDate = ((Intradaydf.tail(1)).iloc[0]['Datetime'])
                    WeekStartDate += datetime.timedelta(days=1) 
                    PlusOneWeek = WeekStartDate + datetime.timedelta(weeks=+1)
                    
                    if(WeekStartDate > CurrentDate):
                        break
                    
                    print(IntradayFileName + ' is being updated for ' + WeekStartDate.strftime("%Y-%m-%d %H:%M"))
                    FreshIntradaydf= yf.download(Scrip, start=WeekStartDate.strftime("%Y-%m-%d"), 
                       end=PlusOneWeek.strftime("%Y-%m-%d"), interval="1m")
                    
                    if FreshIntradaydf.empty:
                        break
                    
                    FreshIntradaydf = FreshIntradaydf.sort_index()
                    FreshIntradaydf.reset_index(level=0, inplace=True)
                    Intradaydf = Intradaydf.append(FreshIntradaydf, ignore_index=True)
            else:
                print(IntradayFileName + ' is upto date')
                continue
        else:
            #Create Dataframe for new Scrip added
            WeekStartDate = CurrentDate + relativedelta(months=-1)
            WeekStartDate += datetime.timedelta(days=2) #One time adjustment
            PlusOneWeek = WeekStartDate + datetime.timedelta(weeks=+1)
            print(IntradayFileName + ' is being created from ' + WeekStartDate.strftime("%Y-%m-%d %H:%M"))
            Intradaydf = yf.download(Scrip, start=WeekStartDate.strftime("%Y-%m-%d"), 
                   end=PlusOneWeek.strftime("%Y-%m-%d"), interval="1m")
            Intradaydf = Intradaydf.sort_index()
            Intradaydf.reset_index(level=0, inplace=True)
            
            while True:
                FreshIntradaydf = None
                WeekStartDate = ((Intradaydf.tail(1)).iloc[0]['Datetime'])
                WeekStartDate += datetime.timedelta(days=1) 
                PlusOneWeek = WeekStartDate + datetime.timedelta(weeks=+1)
                
                if(WeekStartDate > CurrentDate):
                    break
                
                print(IntradayFileName + ' is being updated for ' + WeekStartDate.strftime("%Y-%m-%d %H:%M"))
                FreshIntradaydf= yf.download(Scrip, start=WeekStartDate.strftime("%Y-%m-%d"), 
                   end=PlusOneWeek.strftime("%Y-%m-%d"), interval="1m")
                
                if FreshIntradaydf.empty:
                    break
                
                FreshIntradaydf = FreshIntradaydf.sort_index()
                FreshIntradaydf.reset_index(level=0, inplace=True)
                Intradaydf = Intradaydf.append(FreshIntradaydf, ignore_index=True)

        #Update Feather
        if not Intradaydf.empty:
            feather.write_feather(Intradaydf, './Datastore/'+IntradayFileName)

def main():
    OHLCUpdate()
    # MonthlyFuturesUpdate()
    # FullFuturesUpdate()
    IntradayUpdate()
    FXPEUpdate()
    MonthlyOptionsUpdate()
    
# hhhhhhhhhhhh = feather.read_feather('./Datastore/'+'CENTURYTEX_monthly-futures.ftr')    
# dd = get_expiry_date(2020,11)