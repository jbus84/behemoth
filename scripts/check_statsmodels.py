
try:
    import statsmodels.api as sm
    from statsmodels.tsa.stattools import adfuller
    print("statsmodels available")
except ImportError:
    print("statsmodels NOT available")
