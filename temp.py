# -*- coding: utf-8 -*-
"""
Created on Tue Aug 18 11:54:38 2020

@author: User
"""
# -*- coding: utf-8 -*-
"""
Created on Sat Dec 12 16:44:30 2020

@author: User




# res = next(x for x, val in enumerate(ExpiryDateList) if val > CurrentDate)
# ExpiryDate = ExpiryDateList[res]



# OptionChainCSV.columns = pd.RangeIndex(OptionChainCSV.columns.size)



# header_row = 0
# OptionChainCSV.columns = OptionChainCSV.iloc[header_row]



# FnOVolatilityURL = FnOVolatility + FnOVolatilityArg
# try:
#     r = requests.get(FnOVolatilityURL, allow_redirects=True) #Download FnO Volatility report for 'weekday'
#     if r.ok:
#         data = r.content.decode('utf8')


"""
        
# def GreaterThanCheck(QuantileList, val): 
#     return(all(val > x for x in QuantileList))

# def LessThanCheck(QuantileList, val): 
#     return(all(x > val for x in QuantileList))

# MidMonthDate = CurrentDate + relativedelta(months=1)
# FarMonthDate = MidMonthDate + relativedelta(months=1)

# try: #Need to figure out a way to get expiry dates accurately with new site
#     ExpiryDateSet = None
#     ExpiryDateSet = get_expiry_date(CurrentDate.year,CurrentDate.month)
#     ExpiryDateSet = ExpiryDateSet.union(get_expiry_date(MidMonthDate.year,MidMonthDate.month))
#     ExpiryDateSet = ExpiryDateSet.union(get_expiry_date(FarMonthDate.year,FarMonthDate.month))
# except:
#     print('Couldnt download ExpiryDateSet:')
# ######################################################## Need to iterate future expiry dates below
# ExpiryDateList = list(ExpiryDateSet)

    # def rolling_quantiles(self, window=30, quantiles=[0.25, 0.75]):
    #     """Plots rolling quantiles of volatility
        
    #     Parameters
    #     ----------
    #     window : int
    #         Rolling window for which to calculate the estimator
    #     quantiles : [lower, upper]
    #         List of lower and upper quantiles for which to plot
    #     """

    #     price_data = self._price_data

    #     if len(quantiles) != 2:
    #         raise ValueError(
    #             'A two element list of quantiles is required, lower and upper')
    #     if quantiles[0] + quantiles[1] != 1.0:
    #         raise ValueError(
    #             'The sum of the quantiles must equal 1.0')
    #     if quantiles[0] > quantiles[1]:
    #         raise ValueError(
    #             'The lower quantiles (first element) must be less than the upper quantile (second element)')
        
    #     estimator = self._get_estimator(
    #         window=window,
    #         price_data=price_data
    #     )
    #     date = estimator.index
        
    #     top_q = estimator.rolling(window=window, center=False).quantile(quantiles[1])
    #     median = estimator.rolling(window=window, center=False).median()
    #     bottom_q = estimator.rolling(window=window, center=False).quantile(quantiles[0])
    #     realized = estimator
    #     last = estimator[-1]

    #     if self._estimator is "Skew" or self._estimator is "Kurtosis":
    #         f = lambda x: "%i" % round(x, 0)
    #     else:
    #         f = lambda x: "%i%%" % round(x*100, 0)

    #     # figure
    #     fig = plt.figure(figsize=(8, 6))
    #     fig.autofmt_xdate()
    #     left, width = 0.07, 0.65
    #     bottom, height = 0.2, 0.7
    #     left_h = left+width+0.02
        
    #     rect_cones = [left, bottom, width, height]
    #     rect_box = [left_h, bottom, 0.17, height]
        
    #     cones = plt.axes(rect_cones)
    #     box = plt.axes(rect_box)

    #     # set the plots
    #     cones.plot(date, top_q, label=str(int(quantiles[1]*100)) + " Prctl")
    #     cones.plot(date, median, label="Median")
    #     cones.plot(date, bottom_q, label=str(int(quantiles[0]*100)) + " Prctl")
    #     cones.plot(date, realized, 'r-.', label="Realized")
        
    #     # set and format the y-axis labels
    #     locs = cones.get_yticks()
    #     cones.set_yticklabels(map(f, locs))
        
    #     # turn on the grid
    #     cones.grid(True, axis='y', which='major', alpha=0.5)
        
    #     # set the title
    #     cones.set_title(self._estimator + ' (' + self._symbol + ', daily ' + self._start.strftime('%Y-%m-%d') + ' to ' + self._end.strftime('%Y-%m-%d') + ')')
        
    #     # set the legend
    #     cones.legend(loc='upper center', bbox_to_anchor=(0.5, -0.05), ncol=3)

    #     # box plots
    #     box.boxplot(realized, notch=1, sym='+')
    #     box.plot(1, last, color='r', marker='*', markeredgecolor='k')
        
    #     # set and format the y-axis labels
    #     locs = box.get_yticks()
    #     box.set_yticklabels(map(f, locs))
        
    #     # move the y-axis ticks on the right side
    #     box.yaxis.tick_right()
        
    #     # turn on the grid
    #     box.grid(True, axis='y', which='major', alpha=0.5)
        
    #     return fig, plt

    # def rolling_extremes(self, window=30):
    #     """Plots rolling max and min of volatility estimator
        
    #     Parameters
    #     ----------
    #     window : int
    #         Rolling window for which to calculate the estimator
    #     """

    #     price_data = self._price_data

    #     estimator = self._get_estimator(
    #         window=window,
    #         price_data=price_data
    #     )
    #     date = estimator.index
    #     max_ = estimator.rolling(window=window, center=False).max()
    #     min_ = estimator.rolling(window=window, center=False).min()
    #     realized = estimator
    #     last = estimator[-1]

    #     if self._estimator is "Skew" or self._estimator is "Kurtosis":
    #         f = lambda x: "%i" % round(x, 0)
    #     else:
    #         f = lambda x: "%i%%" % round(x*100, 0)

    #     # figure
    #     fig = plt.figure(figsize=(8, 6))
    #     fig.autofmt_xdate()
    #     left, width = 0.07, 0.65
    #     bottom, height = 0.2, 0.7
    #     left_h = left+width+0.02
        
    #     rect_cones = [left, bottom, width, height]
    #     rect_box = [left_h, bottom, 0.17, height]
        
    #     cones = plt.axes(rect_cones)
    #     box = plt.axes(rect_box)

    #     # set the plots
    #     cones.plot(date, max_, label="Max")
    #     cones.plot(date, min_, label="Min")
    #     cones.plot(date, realized, 'r-.', label="Realized")
        
    #     # set and format the y-axis labels
    #     locs = cones.get_yticks()
    #     cones.set_yticklabels(map(f, locs))
        
    #     # turn on the grid
    #     cones.grid(True, axis='y', which='major', alpha=0.5)
        
    #     # set the title
    #     cones.set_title(self._estimator + ' (' + self._symbol + ', daily ' + self._start.strftime('%Y-%m-%d') + ' to ' + self._end.strftime('%Y-%m-%d') + ')')
        
    #     # set the legend
    #     cones.legend(loc='upper center', bbox_to_anchor=(0.5, -0.05), ncol=3)

    #     # box plot
    #     box.boxplot(realized, notch=1, sym='+')
    #     box.plot(1, last, color='r', marker='*', markeredgecolor='k')
        
    #     # set and format the y-axis labels
    #     locs = box.get_yticks()
    #     box.set_yticklabels(map(f, locs))
        
    #     # move the y-axis ticks on the right side
    #     box.yaxis.tick_right()
        
    #     # turn on the grid
    #     box.grid(True, axis='y', which='major', alpha=0.5)
        
    #     return fig, plt

    # def rolling_descriptives(self, window=30):
    #     """Plots rolling first and second moment of volatility estimator
        
    #     Parameters
    #     ----------
    #     window : int
    #         Rolling window for which to calculate the estimator
    #     """

    #     price_data = self._price_data

    #     estimator = self._get_estimator(
    #         window=window,
    #         price_data=price_data
    #     )
    #     date = estimator.index
    #     mean = estimator.rolling(window=window, center=False).mean()
    #     std = estimator.rolling(window=window, center=False).std()
    #     z_score = (estimator - mean) / std
        
    #     realized = estimator
    #     last = estimator[-1]

    #     if self._estimator is "Skew" or self._estimator is "Kurtosis":
    #         f = lambda x: "%i" % round(x, 0)
    #     else:
    #         f = lambda x: "%i%%" % round(x*100, 0)

    #     # figure
    #     fig = plt.figure(figsize=(8, 6))
    #     fig.autofmt_xdate()
    #     left, width = 0.07, 0.65
    #     left_h = left+width+0.02
        
    #     rect_cones = [left, 0.35, width, 0.55]
    #     rect_box = [left_h, 0.15, 0.17, 0.75]
    #     rect_z = [left, 0.15, width, 0.15]
        
    #     cones = plt.axes(rect_cones)
    #     box = plt.axes(rect_box)
    #     z = plt.axes(rect_z)
        
    #     if self._estimator is "Skew" or self._estimator is "Kurtosis":
    #         f = lambda x: "%i" % round(x, 0)
    #     else:
    #         f = lambda x: "%i%%" % round(x*100, 0)

    #     # set the plots
    #     cones.plot(date, mean, label="Mean")
    #     cones.plot(date, std, label="Std. Dev.")
    #     cones.plot(date, realized, 'r-.', label="Realized")
        
    #     # set and format the y-axis labels
    #     locs = cones.get_yticks()
    #     cones.set_yticklabels(map(f, locs))
        
    #     # turn on the grid
    #     cones.grid(True, axis='y', which='major', alpha=0.5)
        
    #     # set the title
    #     cones.set_title(self._estimator + ' (' + self._symbol + ', daily ' + self._start.strftime('%Y-%m-%d') + ' to ' + self._end.strftime('%Y-%m-%d') + ')')
        
    #     # shrink the plot up a bit and set the legend
    #     pos = cones.get_position()
    #     cones.set_position([pos.x0, pos.y0 + pos.height * 0.1, pos.width, pos.height * 0.9]) #
    #     cones.legend(loc='upper center', bbox_to_anchor=(0.5, -0.05), ncol=3)

    #     # box plot
    #     box.boxplot(realized, notch=1, sym='+')
    #     box.plot(1, last, color='r', marker='*', markeredgecolor='k')
        
    #     # set and format the y-axis labels
    #     locs = box.get_yticks()
    #     box.set_yticklabels(map(f, locs))
        
    #     # move the y-axis ticks on the right side
    #     box.yaxis.tick_right()
        
    #     # turn on the grid
    #     box.grid(True, axis='y', which='major', alpha=0.5)

    #     # z-score set the plots
    #     z.plot(date, z_score, 'm-', label="Z-Score")
        
    #     # turn on the grid
    #     z.grid(True, axis='y', which='major', alpha=0.5)
        
    #     # create a horizontal line at y=0
    #     z.axhline(0, 0, 1, linestyle='-', linewidth=1.0, color='black')
        
    #     # set the legend
    #     z.legend(loc='upper center', bbox_to_anchor=(0.5, -0.2), ncol=3)
        
    #     return fig, plt

    # def histogram(self, window=90, bins=100, normed=True):
    #     """
        
    #     Parameters
    #     ----------
    #     window : int
    #         Rolling window for which to calculate the estimator
    #     bins : int
            
    #     """

    #     price_data = self._price_data

    #     estimator = self._get_estimator(
    #         window=window,
    #         price_data=price_data
    #     )
    #     mean = estimator.mean()
    #     std = estimator.std()
    #     last = estimator[-1]

    #     fig = plt.figure(figsize=(8, 6))
        
    #     n, bins, patches = plt.hist(estimator, bins, normed=normed, facecolor='blue', alpha=0.25)
        
    #     if normed:
    #         y = mlab.normpdf(bins, mean, std)
    #         plt.plot(bins, y, 'g--', linewidth=1)

    #     plt.axvline(last, 0, 1, linestyle='-', linewidth=1.5, color='r')

    #     plt.grid(True, axis='y', which='major', alpha=0.5)
    #     plt.title('Distribution of ' + self._estimator +
    #               ' estimator values (' + self._symbol +
    #               ', daily ' + self._start.strftime('%Y-%m-%d') + ' to ' + self._end.strftime('%Y-%m-%d') + ')')
        
    #     return fig, plt
    
    # def benchmark_compare(self, window=90):
    #     """
        
    #     Parameters
    #     ----------
    #     window : int
    #         Rolling window for which to calculate the estimator
    #     bins : int
            
    #     """

    #     price_data = self._price_data
    #     bench_data = self._bench_data

    #     y = self._get_estimator(
    #         window=window,
    #         price_data=price_data
    #     )
    #     x = self._get_estimator(
    #         window=window,
    #         price_data=bench_data
    #     )
    #     date = y.index
        
    #     ratio = y / x

    #     if self._estimator is "Skew" or self._estimator is "Kurtosis":
    #         f = lambda x: "%i" % round(x, 0)
    #     else:
    #         f = lambda x: "%i%%" % round(x*100, 0)
        
    #     # figure
    #     fig = plt.figure(figsize=(8, 6))
    #     fig.autofmt_xdate()
    #     left, width = 0.07, .9
        
    #     rect_cones = [left, 0.4, width, .5]
    #     rect_box = [left, 0.15, width, 0.15]
        
    #     cones = plt.axes(rect_cones)
    #     box = plt.axes(rect_box)

    #     # set the plots
    #     cones.plot(date, y, label=self._symbol)
    #     cones.plot(date, x, label=self._bench_symbol)
        
    #     # set and format the y-axis labels
    #     locs = cones.get_yticks()
    #     cones.set_yticklabels(map(f, locs))
        
    #     # turn on the grid
    #     cones.grid(True, axis='y', which='major', alpha=0.5)
        
    #     # set the title
    #     cones.set_title(self._estimator + ' (' + self._symbol +
    #                     ' v. ' + self._bench_symbol + ', daily ' +
    #                     self._start.strftime("%Y%m%d") + ' to ' + self._end.strftime("%Y%m%d") + ')')
        
    #     # shrink the plot up a bit and set the legend
    #     cones.legend(loc='upper center', bbox_to_anchor=(0.5, -0.05), ncol=3)

    #     # set the plot
    #     box.plot(date, ratio, label=self._symbol + '/' + self._bench_symbol)
        
    #     # set the y-limits
    #     box.set_ylim((ratio.min() - 0.05, ratio.max() + 0.05))
        
    #     # fill the area
    #     box.fill_between(date, ratio, 0, color='blue', alpha=0.25)
        
    #     # set the legend
    #     box.legend(loc='upper center', bbox_to_anchor=(0.5, -0.2), ncol=3)

    #     return fig, plt

    # def benchmark_correlation(self, window=90):
    #     """
        
    #     Parameters
    #     ----------
    #     window : int
    #         Rolling window for which to calculate the estimator
    #     bins : int
            
    #     """
        
    #     price_data = self._price_data
    #     bench_data = self._bench_data

    #     y = self._get_estimator(
    #         window=window,
    #         price_data=price_data
    #     )
    #     x = self._get_estimator(
    #         window=window,
    #         price_data=bench_data
    #     )
    #     date = y.index

    #     corr = x.rolling(window=window).corr(other=y)

    #     if self._estimator is "Skew" or self._estimator is "Kurtosis":
    #         f = lambda x: "%i" % round(x, 0)
    #     else:
    #         f = lambda x: "%i%%" % round(x*100, 0)
        
    #     # figure
    #     fig = plt.figure(figsize=(8, 6))
    #     cones = plt.axes()

    #     # set the plots
    #     cones.plot(date, corr)

    #     # set the y-limits
    #     cones.set_ylim((corr.min() - 0.05, corr.max() + 0.05))

    #     # set and format the y-axis labels
    #     locs = cones.get_yticks()
    #     cones.set_yticklabels(map(f, locs))

    #     # turn on the grid
    #     cones.grid(True, axis='y', which='major', alpha=0.5)

    #     # set the title
    #     cones.set_title(self._estimator + ' (Correlation of ' +
    #                     self._symbol + ' v. ' + self._bench_symbol +
    #                     ', daily ' + self._start + ' to ' + self._end + ')')
        
    #     return fig, plt

    # def benchmark_regression(self, window=90):
    #     """
        
    #     Parameters
    #     ----------
    #     window : int
    #         Rolling window for which to calculate the estimator
    #     bins : int
            
    #     """
    #     price_data = self._price_data
    #     bench_data = self._bench_data

    #     y = self._get_estimator(
    #         window=window,
    #         price_data=price_data
    #     )
    #     X = self._get_estimator(
    #         window=window,
    #         price_data=bench_data
    #     )
        
    #     model = sm.OLS(y, X)
    #     results = model.fit()

    #     return results.summary()
    
    # def term_sheet(
    #         self,
    #         window=30,
    #         windows=[30, 60, 90, 120],
    #         quantiles=[0.25, 0.75],
    #         bins=100,
    #         normed=True,
    #         open=False):
        
    #     cones_fig, cones_plt = self.cones(windows=windows, quantiles=quantiles)
    #     rolling_quantiles_fig, rolling_quantiles_plt = self.rolling_quantiles(window=window, quantiles=quantiles)
    #     rolling_extremes_fig, rolling_extremes_plt = self.rolling_extremes(window=window)
    #     rolling_descriptives_fig, rolling_descriptives_plt = self.rolling_descriptives(window=window)
    #     histogram_fig, histogram_plt = self.histogram(window=window, bins=bins, normed=normed)
    #     benchmark_compare_fig, benchmark_compare_plt = self.benchmark_compare(window=window)
    #     benchmark_corr_fig, benchmark_corr_plt = self.benchmark_correlation(window=window)
    #     benchmark_regression = self.benchmark_regression(window=window)
        
    #     filename = self._symbol.upper() + '_termsheet_' + datetime.datetime.today().strftime("%Y%m%d") + '.pdf'
    #     fn = os.path.abspath(os.path.join(u'..', u'term-sheets', filename))
    #     pp = PdfPages(fn)
        
    #     pp.savefig(cones_fig)
    #     pp.savefig(rolling_quantiles_fig)
    #     pp.savefig(rolling_extremes_fig)
    #     pp.savefig(rolling_descriptives_fig)
    #     pp.savefig(histogram_fig)
    #     pp.savefig(benchmark_compare_fig)
    #     pp.savefig(benchmark_corr_fig)

    #     fig = plt.figure(figsize=(8, 6))
    #     ax = fig.add_subplot(111)
    #     ax.text(
    #         0, .2,
    #         benchmark_regression,
    #         family='monospace',
    #         fontsize=9
    #     )

    #     plt.axis('off')
    #     fig.tight_layout()
    #     pp.savefig(fig)
    #     pp.close()
        
    #     print('%s output complete' % filename)






























            OldOHLCdf = OldOHLCdf[OldOHLCdf.Date < OHLCStartDate] #DO NOT ENABLE!!!
        # if (FindFeather(OHLCSettleArg, './New NSE site/')):
        #     Settledf = feather.read_feather('./New NSE site/'+OHLCSettleArg) #Volatilitydf.info()
        #     NewOHLCdf = pd.merge(NewOHLCdf, Settledf, how="inner", on=["Symbol","Expiry","Instrument"])
        # else:
        #     print('Couldnt find settlement info for '+ OHLCSettleArg)
            
        # #FnO Settlement Report download    
        # FnOSettleArg = 'FOSett_prce_' + weekday.strftime("%d%m%Y") + '.csv'
        # FnOSettlementURL = FnOSettlement + FnOSettleArg
        # try:
        #     r = requests.get(FnOSettlementURL, allow_redirects=True) #Download FnO Volatility report for 'weekday'
        #     if r.ok:
        #         data = r.content.decode('utf8')
        #         Setdf = pd.read_csv(io.StringIO(data))
        #         Setdf = Setdf.rename(columns=lambda x: x.strip())
        #         Setdf = Setdf.applymap(lambda x: x.strip() if isinstance(x, str) else x)
        #         Setdf = RefineNewNSEFutures(Setdf)
        # except:
        #     print('Couldnt download:'+ FnOSettlementURL)    
            
        # if not Setdf.empty:
        #     feather.write_feather(Setdf, './New NSE site/'+FnOSettleArg+'.ftr')    


def RefineNewNSEFutures(DF):
    df = DF.copy()
    
    if 'INSTRUMENT' in df.columns:
        df.rename(columns={'INSTRUMENT': 'Instrument'}, inplace=True)
        
    if 'SYMBOL' in df.columns:
        df.rename(columns={'SYMBOL': 'Symbol'}, inplace=True)
    
    if 'EXP_DATE' in df.columns:
        df.rename(columns={'EXP_DATE': 'Expiry'}, inplace=True)
        # df["Expiry"] = df["EXP_DATE"].apply(pd.to_datetime, format='%d-%b-%Y')
        df['Expiry'] = df['Expiry'].dt.date
     
    if 'OPEN_PRICE' in df.columns:
        df.rename(columns={'OPEN_PRICE': 'Open'}, inplace=True) 
        
    if 'HI_PRICE' in df.columns:
        df.rename(columns={'HI_PRICE': 'High'}, inplace=True)
        
    if 'LO_PRICE' in df.columns:
        df.rename(columns={'LO_PRICE': 'Low'}, inplace=True)
    
    if 'CLOSE_PRICE' in df.columns:
        df.rename(columns={'CLOSE_PRICE': 'Close'}, inplace=True)

    if 'OPEN_INT*' in df.columns:
        df.rename(columns={'OPEN_INT*': 'Open Interest'}, inplace=True)

    if 'TRD_VAL' in df.columns:
        df.rename(columns={'TRD_VAL': 'Turnover'}, inplace=True)                  
        
    if 'NO_OF_CONT' in df.columns:
        df.rename(columns={'NO_OF_CONT': 'Number of Contracts'}, inplace=True)      

    if 'DATE' in df.columns:
        df.rename(columns={'DATE': 'Date'}, inplace=True)
        df['Date'] = df['Date'].apply(pd.to_datetime, format='%d-%b-%Y')
        df['Date'] = df['Date'].dt.date
    
    if 'UNDERLYING' in df.columns:
        df.rename(columns={'UNDERLYING': 'Symbol'}, inplace=True)

    if 'INSTRUMENT' in df.columns:
        df.rename(columns={'INSTRUMENT': 'Instrument'}, inplace=True)

    if 'EXPIRY DATE' in df.columns:
        df.rename(columns={'EXPIRY DATE': 'Expiry'}, inplace=True)
        df['Expiry'] = df['Expiry'].apply(pd.to_datetime, format='%d-%b-%Y')
        df['Expiry'] = df['Expiry'].dt.date

    if 'MTM SETTLEMENT PRICE' in df.columns:
        df.rename(columns={'MTM SETTLEMENT PRICE': 'Settle Price'}, inplace=True)
        
    return df

# for sym in FnOSymbollist:
#     FuturesFileName = sym + '_' + FullFuturesFilePath
#     #Read from feather
#     if (FindFeather(FuturesFileName, './Datastore/')):
#         OldFuturesdf = feather.read_feather('./Datastore/'+FuturesFileName)
#         df = OldFuturesdf.copy()
#         print('Updating Futures for '+ sym)
#         if 'Number of Contracts' in df.columns:
#             df.rename(columns={'Number of Contracts': 'No. of contracts'}, inplace=True)
        
#         if 'Turnover' in df.columns:
#             df.rename(columns={'Turnover': 'Turnover in Lacs'}, inplace=True)

#         if 'Open Interest' in df.columns:
#             df.rename(columns={'Open Interest': 'Open Int'}, inplace=True)
        
#     if not df.empty:
#         feather.write_feather(df, './Datastore/'+FuturesFileName)

    
            # ###########OldFuturesdf.drop("index", axis=1, inplace=True) #DO NOT ENABLE!!!
            # ############OldFuturesdf = OldFuturesdf[OldFuturesdf.Date < FnOStartDate] #DO NOT ENABLE!!!
            # ########OldOptionsdf = OldOptionsdf[OldOptionsdf.Date < FnOStartDate] #DO NOT ENABLE!!!            
            
            
# def UpdatetNSEFuturesData():
#     TotalNewFuturesdf = pd.DataFrame()
#     for weekday in bday:
#         FnOReportArg = 'fo' + weekday.strftime("%d%m%Y")
#         FnOSettleArg = 'FOSett_prce_' + weekday.strftime("%d%m%Y") + '.csv.ftr'
    
#         zf = ZipFile('New NSE site/'+FnOReportArg + '.zip') 
#         CSVdf = pd.read_csv(zf.open(FnOReportArg+'.csv'), parse_dates=[2], dayfirst=True)
#         CSVdf = CSVdf.rename(columns=lambda x: x.strip())
#         CSVdf = CSVdf.applymap(lambda x: x.strip() if isinstance(x, str) else x)
#         NewFuturesdf = RefineNewNSEFutures(CSVdf)
        
#         if (FindFeather(FnOSettleArg, './New NSE site/')):
#             Settledf = feather.read_feather('./New NSE site/'+FnOSettleArg) #Volatilitydf.info()
#             NewFuturesdf = pd.merge(NewFuturesdf, Settledf, how="inner", on=["Symbol","Expiry","Instrument"])
#         else:
#             print('Couldnt find settlement info for '+ FnOSettleArg)
        
#         TotalNewFuturesdf = TotalNewFuturesdf.append(NewFuturesdf, ignore_index=True)
    
#     TotalNewFuturesdf = TotalNewFuturesdf.sort_values(by=['Symbol', 'Date'])
#     FnOSymbollist = []
#     #Adding values to list
#     FnOSymbollist = list(TotalNewFuturesdf['Symbol'])
#     #Removing duplicates in list
#     FnOSymbollist = list(dict.fromkeys(FnOSymbollist))
    
#     #Update the old Futures file
#     for sym in FnOSymbollist:
        
#         FuturesFileName = sym + '_' + FullFuturesFilePath
#         #Read from feather
#         if (FindFeather(FuturesFileName, './Datastore/')):
#             OldFuturesdf = feather.read_feather('./Datastore/'+FuturesFileName)
#             print('Updating Futures for '+ sym)
#             Mergedf = OldFuturesdf.append(TotalNewFuturesdf[TotalNewFuturesdf["Symbol"] == sym], ignore_index = True)            
#         else: #A new symbol has been added, create a feather for it
#             print('Creating new Futures DB for '+ sym)
#             Mergedf = TotalNewFuturesdf[TotalNewFuturesdf["Symbol"] == sym]#, ignore_index = True)
            
#         if not Mergedf.empty:
#             feather.write_feather(Mergedf, './Datastore/'+FuturesFileName)


    ExpiryDatedf = NewFuturesdf.groupby('Symbol')['Expiry'].apply(lambda x: pd.Series(list(x))).unstack() 
    ExpiryDatedf = ExpiryDatedf.reset_index(level=0)
    ExpiryDatedf = ExpiryDatedf.rename(columns={0: 'NearExpiry',1:'MidExpiry',2:'FarExpiry'})
    
    SettlePricedf = NewFuturesdf.groupby('Symbol')['Settle Price'].apply(lambda x: pd.Series(list(x))).unstack()
    SettlePricedf = SettlePricedf.reset_index(level=0)
    SettlePricedf = SettlePricedf.rename(columns={0: 'NearSettlePrice',1:'MidSettlePrice',2:'FarSettlePrice'})
  
    OpenInterestdf = NewFuturesdf.groupby('Symbol')['Open Interest'].apply(lambda x: pd.Series(list(x))).unstack()
    OpenInterestdf = OpenInterestdf.reset_index(level=0)
    OpenInterestdf = OpenInterestdf.rename(columns={0: 'NearOpenInterest',1:'MidOpenInterest',2:'FarOpenInterest'})        
    
    NoOfContractsdf = NewFuturesdf.groupby('Symbol')['Number of Contracts'].apply(lambda x: pd.Series(list(x))).unstack()
    NoOfContractsdf = NoOfContractsdf.reset_index(level=0)
    NoOfContractsdf = NoOfContractsdf.rename(columns={0: 'NearNoOfContracts',1:'MidNoOfContracts',2:'FarNoOfContracts'})        
    
  
    dfs = [ExpiryDatedf, OpenInterestdf, SettlePricedf, NoOfContractsdf]
    Futdf = reduce(lambda left,right: pd.merge(left,right,on='Symbol'), dfs)   
    

    if (FindFeather(FnOVolatilityArg, './New NSE site/')):
        Volatilitydf = feather.read_feather('./New NSE site/'+FnOVolatilityArg) #Volatilitydf.info()
        #Below Formatting is needed to clean up the csv and remove whitespaces
        Volatilitydf = Volatilitydf.rename(columns=lambda x: x.strip())
        Volatilitydf = Volatilitydf.applymap(lambda x: x.strip() if isinstance(x, str) else x)
        Mergedf = pd.merge(NewFuturesdf, Volatilitydf, how="outer", on=["Symbol"])

df = pd.DataFrame({'Date': ['05-01-2018', '02-20-2020']})

df['Date'] = pd.to_datetime(df['Date'])
df['Month'] = df['Date'].dt.month
df['Month-str'] = df['Date'].dt.strftime('%b')
df['Month-str-full'] = df['Date'].dt.strftime('%B')

    for Scrip in NSEFnOList:
        Scrip = "OIL"
        Optionsdf = None
        CurrentDate = datetime.date.today()
        CurrentMonth = CurrentDate.month
        CurrentYear = CurrentDate.year
        print('For'+Scrip)
        OptionsFileName = Scrip + '_' + MonthlyOptionsFilePath
        #Read from feather
        if (FindFeather(OptionsFileName, './Datastore')):
            Optionsdf = feather.read_feather('./Datastore/'+OptionsFileName)
            try:
                # Optionsdf['Date'] = Optionsdf['Date'].dt.date
                Optionsdf['Expiry'] = Optionsdf['Expiry'].dt.date
            except:
                print(Scrip," :already done")
                continue
            feather.write_feather(Optionsdf, './Datastore/'+ OptionsFileName)
            # continue

# def MACDVisual(MACDdf,Scrip):
#     DF = MACDdf.copy()         
#     plt.subplot(311)
#     plt.figsize=(16,9)
    
#     if(Scrip == "NIFTY"):
#         plt.plot(DF.iloc[-100:,3])
#     else:
#         plt.plot(DF.iloc[-100:,[7,8]])
#         plt.legend(('Close','VWAP'),loc='upper left')
    
#     plt.title(Scrip)
#     plt.xticks([])
#     plt.grid(True)
    
#     plt.subplot(312)
#     plt.figsize=(16,9)
#     if(Scrip == "NIFTY"):
#         plt.plot(DF.iloc[-100:,4].index, DF.iloc[-100:,4].values)
#     else:
#         plt.plot(DF.iloc[-100:,[9,12]].index, DF.iloc[-100:,[9,12]].values)
#         plt.legend(('Volume','Delivered'),loc='upper left')
#     plt.title('Volume/Delivered')
#     plt.xticks([])
#     plt.grid(True)
    
#     plt.subplot(313)
#     plt.figsize=(16,9)
#     plt.plot(DF.iloc[-100:,[-2,-1]])
#     plt.title('MACD')
#     plt.legend(('MACD','Signal'),loc='upper left')
#     plt.grid(True)
    
#     plt.show()
    
    # fig, (ax0, ax1) = plt.subplots(nrows=2,ncols=1, sharex=True, sharey=False, figsize=(10, 6), gridspec_kw = {'height_ratios':[2.5, 1]})
    # OHLCdf.iloc[-100:,8].plot(ax=ax0)
    # ax0.set(ylabel='Close')
    
    # OHLCdf.iloc[-100:,[-2,-1]].plot(ax=ax1)
    # ax1.set(xlabel='Date', ylabel='MACD/Signal')
    
    # # Title the figure
    # fig.suptitle('Stock Price with MACD', fontsize=14, fontweight='bold')
            # plt.subplot(312)
            # plt.plot(Indicatordf.iloc[-100:,[-2,-1]])
            # plt.figsize=(16,9)
            # plt.title(" TR & ATR")
            # plt.grid(True)
            # #Deliverable volume %
            # plt.subplot(313)
            # plt.plot(Indicatordf.iloc[-100:,-3])
            # plt.figsize=(16,9)
            # plt.title('%Deliverable')
            # plt.grid(True)            
            # plt.show()
    
            # OHLCdf["ADX"] = talib.ADX(OHLCdf["High"],
            #                                     OHLCdf["Low"],
            #                                     OHLCdf["Close"],
            #                                     timeperiod=14)
            
            # Indicatordf["ADX"] = ADX(Indicatordf,20)
            
                        # plt.subplot(311)
            # plt.plot(Indicatordf.iloc[-100:,[-4,-3,-2]])
            # plt.figsize=(16,9)
            # plt.title(Scrip+' Bollinger Band')
            # plt.grid(True)
            
            
                                # data[data['Value'] == True]
            
                    # .reset_index(level=0, inplace=True)
            
            #Using OHLCData here as it is not time serie data. Todo: Figure out a way to cache this
            # Renkodata = Renko_DF(OHLCdf)
            # #DF amd number of latest bricks
            # PlotRenko(Renkodata,100)
# df.sort_values(by='col1', ascending=False)
# MonthlyFuturesFilePath = "monthly-futures.ftr"
# MonthlyOptionsFilePath = "monthly-options.ftr"