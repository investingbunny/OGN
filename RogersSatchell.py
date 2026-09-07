import math

import numpy as np


def get_estimator(price_data, window=30, trading_periods=252, clean=True):
    
    log_ho = (price_data['High'] / price_data['Open']).apply(np.log)
    log_lo = (price_data['Low'] / price_data['Open']).apply(np.log)
    log_co = (price_data['Close'] / price_data['Open']).apply(np.log)
    
    rs = log_ho * (log_ho - log_co) + log_lo * (log_lo - log_co)

    def f(v):
        # Annualise by sqrt(trading_periods); multiplying by the period count
        # itself overstated the result by sqrt(252).
        return math.sqrt(trading_periods * v.mean())
    
    result = rs.rolling(
        window=window,
        center=False
    ).apply(func=f)
    
    if clean:
        return result.dropna()
    else:
        return result
