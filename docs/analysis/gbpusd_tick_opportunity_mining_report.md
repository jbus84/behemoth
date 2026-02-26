# Tick Opportunity Mining Report

## Setup
- symbol: `GBPUSD`
- bar_ticks_grid: `100,1000,2000`
- horizons: `1,2,3,4,5,6`
- train_years: `2022,2023,2024`
- test_year: `2025`
- min_annual_fills: `5000.0`
- inclusion_metric: `mean`

## Directional Top
```text
 bar_ticks  horizon       family                      state_id quality_tier  annualized_test_fills  mean_gross_pips_test  median_gross_pips_test  gross_std_test  hit_rate_gross_test  selection_pass
       100        4  path_follow              path_follow__all            C           99012.088668              0.043674                     0.0        4.197321             0.498444            True
       100        6  path_follow              path_follow__all            C           99012.088668              0.039227                     0.0        5.104665             0.499437            True
       100        5  path_follow              path_follow__all            C           99012.088668              0.038778                     0.0        4.682026             0.498951            True
       100        3  path_follow              path_follow__all            C           99012.088668              0.029495                     0.0        3.642104             0.497725            True
       100        2  path_follow              path_follow__all            C           99012.088668              0.023465                     0.0        2.968399             0.496914            True
       100        1  path_follow              path_follow__all            C           99012.088668              0.013534                     0.0        2.120042             0.491309            True
       100        4  path_follow path_follow__high_abs_vel_q70            C           82419.588196              0.047354                     0.0        4.362962             0.497486            True
       100        6  path_follow path_follow__high_abs_vel_q70            C           82419.588196              0.046600                     0.0        5.290986             0.499178            True
       100        5  path_follow path_follow__high_abs_vel_q70            C           82419.588196              0.043573                     0.0        4.849845             0.498241            True
       100        3  path_follow path_follow__high_abs_vel_q70            C           82419.588196              0.030951                     0.0        3.793977             0.497449            True
       100        2  path_follow path_follow__high_abs_vel_q70            C           82419.588196              0.023608                     0.0        3.092648             0.497327            True
       100        1  path_follow path_follow__high_abs_vel_q70            C           82419.588196              0.013401                     0.0        2.203774             0.490898            True
       100        4  path_follow     path_follow__low_cost_q50            C           81369.887247              0.036197                     0.0        4.237985             0.497675            True
       100        5  path_follow     path_follow__low_cost_q50            C           81369.887247              0.035684                     0.0        4.719829             0.499020            True
       100        6  path_follow     path_follow__low_cost_q50            C           81369.887247              0.035482                     0.0        5.155587             0.499673            True
       100        3  path_follow     path_follow__low_cost_q50            C           81369.887247              0.025560                     0.0        3.668311             0.497478            True
       100        2  path_follow     path_follow__low_cost_q50            C           81369.887247              0.017469                     0.0        2.995033             0.496417            True
       100        1  path_follow     path_follow__low_cost_q50            C           81369.887247              0.010902                     0.0        2.140468             0.490917            True
       100        4 shock_revert             shock_revert__all            C           74336.088057              0.069039                     0.1        4.256763             0.500041            True
       100        6 shock_revert             shock_revert__all            C           74336.088057              0.064449                     0.1        5.169080             0.501823            True
```

## OCO Top
```text
 bar_ticks  horizon                family                          state_id quality_tier  annualized_test_fills  mean_gross_pips_test  median_gross_pips_test  gross_std_test  hit_rate_gross_test  selection_pass
       100        6       oco_first_touch          oco_first_touch__all__k2            C          234216.831445              0.116378                     0.1        4.613153             0.504098            True
       100        5       oco_first_touch          oco_first_touch__all__k2            C          230529.485063              0.112714                     0.1        4.170641             0.504871            True
       100        4       oco_first_touch          oco_first_touch__all__k2            C          224128.252378              0.120221                     0.1        3.684007             0.505241            True
       100        3       oco_first_touch          oco_first_touch__all__k2            C          211419.292497              0.123636                     0.1        3.142658             0.507452            True
       100        6       oco_first_touch          oco_first_touch__all__k3            C          207575.260180              0.105381                     0.1        4.379185             0.505182            True
       100        5       oco_first_touch          oco_first_touch__all__k3            C          195866.573485              0.104200                     0.1        3.967232             0.505689            True
       100        6       oco_first_touch oco_first_touch__low_cost_q50__k2            C          195833.461039              0.121293                     0.1        4.598552             0.504671            True
       100        5       oco_first_touch oco_first_touch__low_cost_q50__k2            C          192932.423196              0.116058                     0.1        4.153619             0.505053            True
       100        4       oco_first_touch oco_first_touch__low_cost_q50__k2            C          187738.380989              0.120537                     0.1        3.664662             0.505700            True
       100        2       oco_first_touch          oco_first_touch__all__k2            C          184711.912533              0.126258                     0.1        2.523563             0.512090            True
       100        3 oco_first_touch_clean    oco_first_touch_clean__all__k2            B          182958.848742              0.799944                     0.4        2.536985             0.579358            True
       100        6 oco_first_touch_clean    oco_first_touch_clean__all__k3            B          182170.988149              0.988982                     0.5        3.564230             0.569732            True
       100        4 oco_first_touch_clean    oco_first_touch_clean__all__k2            A          180455.188663              1.163164                     0.7        2.892900             0.611735            True
       100        4       oco_first_touch          oco_first_touch__all__k3            C          178697.178323              0.114216                     0.1        3.526746             0.509083            True
       100        5 oco_first_touch_clean    oco_first_touch_clean__all__k3            B          177814.123516              0.754743                     0.4        3.282153             0.553575            True
       100        3       oco_first_touch oco_first_touch__low_cost_q50__k2            C          177272.178734              0.123359                     0.1        3.118144             0.507413            True
       100        6       oco_first_touch oco_first_touch__low_cost_q50__k3            C          174243.442366              0.104439                     0.1        4.353353             0.504999            True
       100        5 oco_first_touch_clean    oco_first_touch_clean__all__k2            A          173003.481762              1.542242                     1.0        3.203491             0.645364            True
       100        2 oco_first_touch_clean    oco_first_touch_clean__all__k2            B          171469.106094              0.468359                     0.2        2.113663             0.549498            True
       100        4 oco_first_touch_clean    oco_first_touch_clean__all__k3            B          167439.233009              0.550232                     0.3        2.993904             0.541466            True
```

## Selection Summary
```text
    library  rows_total  rows_pass  pass_rate  mean_annualized_fills_all  mean_annualized_fills_pass  mean_gross_all  mean_gross_pass  tier_a_rows  tier_b_rows  tier_c_rows
directional        2088        364   0.174330               12329.099561                30165.955674        0.082081         0.082043            0           13          351
        oco        2160        762   0.352778               15257.155518                35552.819137        2.441010         1.221528           82          201          479
```
