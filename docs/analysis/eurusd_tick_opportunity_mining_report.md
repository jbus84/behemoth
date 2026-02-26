# Tick Opportunity Mining Report

## Setup
- symbol: `EURUSD`
- bar_ticks_grid: `100,1000,2000`
- horizons: `1,2,3,4,5,6`
- train_years: `2022,2023,2024`
- test_year: `2025`
- min_annual_fills: `5000.0`
- inclusion_metric: `mean`

## Directional Top
```text
 bar_ticks  horizon       family                    state_id quality_tier  annualized_test_fills  mean_gross_pips_test  median_gross_pips_test  gross_std_test  hit_rate_gross_test  selection_pass
       100        6  path_follow            path_follow__all            C           95688.640398              0.032378                     0.0        4.838134             0.497126            True
       100        5  path_follow            path_follow__all            C           95688.640398              0.021578                     0.0        4.422926             0.494662            True
       100        4  path_follow            path_follow__all            C           95685.102990              0.020021                     0.0        3.967179             0.495653            True
       100        2  path_revert            path_revert__all            C           95685.102990              0.002230                     0.0        2.807021             0.492297            True
       100        1  path_follow            path_follow__all            C           95685.102990              0.000972                     0.0        1.986874             0.485815            True
       100        3  path_follow            path_follow__all            C           95685.102990              0.000299                     0.0        3.433881             0.492706            True
       100        6 shock_revert           shock_revert__all            C           71644.044441              0.023558                     0.0        4.881001             0.497261            True
       100        4 shock_revert           shock_revert__all            C           71644.044441              0.015953                     0.0        4.014489             0.496253            True
       100        5 shock_revert           shock_revert__all            C           71644.044441              0.008514                     0.0        4.461983             0.495440            True
       100        2 shock_follow           shock_follow__all            C           71644.044441              0.004655                     0.0        2.852932             0.492485            True
       100        3 shock_follow           shock_follow__all            C           71644.044441              0.003344                     0.0        3.470495             0.494012            True
       100        1 shock_revert           shock_revert__all            C           71644.044441              0.001415                     0.0        2.029662             0.486419            True
       100        6  path_follow path_follow__high_range_q70            C           67804.375668              0.047633                     0.0        5.146072             0.499697            True
       100        5  path_follow path_follow__high_range_q70            C           67804.375668              0.032587                     0.0        4.703269             0.497032            True
       100        4  path_follow path_follow__high_range_q70            C           67804.375668              0.031793                     0.0        4.228223             0.499134            True
       100        1  path_follow path_follow__high_range_q70            C           67804.375668              0.007210                     0.0        2.124225             0.488655            True
       100        3  path_follow path_follow__high_range_q70            C           67804.375668              0.006298                     0.0        3.661249             0.494664            True
       100        2  path_follow path_follow__high_range_q70            C           67804.375668              0.003637                     0.0        3.002636             0.492829            True
       100        3  path_follow   path_follow__low_cost_q30            C           67353.838607              0.086428                     0.1        3.322921             0.503628            True
       100        4  path_follow   path_follow__low_cost_q30            C           67353.838607              0.061892                     0.1        3.850042             0.505241            True
```

## OCO Top
```text
 bar_ticks  horizon                family                          state_id quality_tier  annualized_test_fills  mean_gross_pips_test  median_gross_pips_test  gross_std_test  hit_rate_gross_test  selection_pass
       100        6       oco_first_touch          oco_first_touch__all__k2            C          227223.890546              0.124003                     0.1        4.364683             0.508301            True
       100        5       oco_first_touch          oco_first_touch__all__k2            C          222643.822632              0.125107                     0.1        3.942335             0.508938            True
       100        4       oco_first_touch          oco_first_touch__all__k2            C          214500.952291              0.131956                     0.1        3.483378             0.509811            True
       100        3       oco_first_touch          oco_first_touch__all__k2            C          199183.651448              0.133190                     0.1        2.975823             0.512238            True
       100        6       oco_first_touch          oco_first_touch__all__k3            C          194677.027510              0.135391                     0.1        4.163445             0.510418            True
       100        5       oco_first_touch          oco_first_touch__all__k3            C          181352.342279              0.135347                     0.1        3.785087             0.511358            True
       100        4 oco_first_touch_clean    oco_first_touch_clean__all__k2            B          179967.085748              0.968473                     0.6        2.780251             0.596993            True
       100        3 oco_first_touch_clean    oco_first_touch_clean__all__k2            B          177749.361473              0.662607                     0.3        2.445913             0.568836            True
       100        6 oco_first_touch_clean    oco_first_touch_clean__all__k3            B          176130.002264              0.816781                     0.4        3.468372             0.560042            True
       100        5 oco_first_touch_clean    oco_first_touch_clean__all__k2            A          175745.451996              1.284695                     0.8        3.086761             0.625621            True
       100        6 oco_first_touch_clean    oco_first_touch_clean__all__k2            A          168976.536761              1.615963                     1.1        3.373509             0.652977            True
       100        2       oco_first_touch          oco_first_touch__all__k2            C          168857.162888              0.131986                     0.1        2.406598             0.515270            True
       100        5 oco_first_touch_clean    oco_first_touch_clean__all__k3            B          168513.797908              0.633312                     0.3        3.204215             0.547762            True
       100        4       oco_first_touch          oco_first_touch__all__k3            C          162325.831536              0.142132                     0.1        3.387247             0.512943            True
       100        6       oco_first_touch oco_first_touch__low_cost_q30__k2            C          160529.990352              0.064323                     0.1        4.240499             0.506649            True
       100        2 oco_first_touch_clean    oco_first_touch_clean__all__k2            C          159375.135110              0.397901                     0.2        2.056732             0.544333            True
       100        5       oco_first_touch oco_first_touch__low_cost_q30__k2            C          156028.445512              0.057948                     0.1        3.829899             0.506899            True
       100        4 oco_first_touch_clean    oco_first_touch_clean__all__k3            B          154448.031572              0.479034                     0.2        2.925804             0.537624            True
       100        4       oco_first_touch oco_first_touch__low_cost_q30__k2            C          148036.297498              0.034205                     0.1        3.419842             0.506538            True
       100        3       oco_first_touch          oco_first_touch__all__k3            C          135460.856739              0.143527                     0.1        2.958247             0.515943            True
```

## Selection Summary
```text
    library  rows_total  rows_pass  pass_rate  mean_annualized_fills_all  mean_annualized_fills_pass  mean_gross_all  mean_gross_pass  tier_a_rows  tier_b_rows  tier_c_rows
directional        2088        362   0.173372               10758.271346                26566.401087        0.075006          0.11125            0           34          328
        oco        2160        737   0.341204               12567.484852                29530.128190        2.203453          1.19563           56          252          429
```
