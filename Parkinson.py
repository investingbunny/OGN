import math

import numpy as np


def get_estimator(price_data, window=30, trading_periods=252, clean=True):

    rs = (1.0 / (4.0 * math.log(2.0))) * ((price_data['High'] / price_data['Low']).apply(np.log))**2.0

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
