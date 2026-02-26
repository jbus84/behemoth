# Tick Opportunity Mining Report

## Setup
- symbol: `USDJPY`
- bar_ticks_grid: `100,1000,2000`
- horizons: `1,2,3,4,5,6`
- train_years: `2022,2023,2024`
- test_year: `2025`
- min_annual_fills: `5000.0`
- inclusion_metric: `mean`

## Directional Top
```text
 bar_ticks  horizon       family                       state_id quality_tier  annualized_test_fills  mean_gross_pips_test  median_gross_pips_test  gross_std_test  hit_rate_gross_test  selection_pass
       100        6  path_follow               path_follow__all            C          141106.205903              0.041474                     0.1        6.302141             0.500068            True
       100        5  path_follow               path_follow__all            C          141104.028302              0.040382                     0.0        5.777180             0.499324            True
       100        4  path_follow               path_follow__all            C          141104.028302              0.030646                     0.0        5.177218             0.498720            True
       100        3  path_follow               path_follow__all            C          141104.028302              0.027433                     0.1        4.493381             0.500398            True
       100        2  path_follow               path_follow__all            C          141104.028302              0.021748                     0.0        3.721730             0.497938            True
       100        1  path_follow               path_follow__all            C          141103.247413              0.014172                     0.0        2.690570             0.496234            True
       100        6  path_follow  path_follow__high_abs_vel_q70            C          125147.774109              0.040718                     0.0        6.400996             0.499238            True
       100        5  path_follow  path_follow__high_abs_vel_q70            C          125145.956183              0.040969                     0.0        5.872522             0.498649            True
       100        4  path_follow  path_follow__high_abs_vel_q70            C          125145.956183              0.030261                     0.0        5.271396             0.497807            True
       100        3  path_follow  path_follow__high_abs_vel_q70            C          125145.956183              0.023796                     0.0        4.571887             0.499619            True
       100        2  path_follow  path_follow__high_abs_vel_q70            C          125145.956183              0.021735                     0.0        3.799693             0.497462            True
       100        1  path_follow  path_follow__high_abs_vel_q70            C          125145.956183              0.014731                     0.0        2.750271             0.496323            True
       100        6 shock_revert              shock_revert__all            C          106521.813909              0.065061                     0.1        6.381774             0.501512            True
       100        5 shock_revert              shock_revert__all            C          106520.415972              0.069704                     0.1        5.864459             0.501639            True
       100        4 shock_revert              shock_revert__all            C          106520.415972              0.064047                     0.1        5.263745             0.500707            True
       100        3 shock_revert              shock_revert__all            C          106520.415972              0.052285                     0.1        4.567801             0.503297            True
       100        2 shock_revert              shock_revert__all            C          106520.415972              0.036425                     0.1        3.801648             0.500528            True
       100        1 shock_revert              shock_revert__all            C          106520.415972              0.023882                     0.0        2.762439             0.499001            True
       100        6 shock_revert shock_revert__high_abs_vel_q70            C          101624.737326              0.059182                     0.0        6.449929             0.499990            True
       100        5 shock_revert shock_revert__high_abs_vel_q70            C          101623.449724              0.066783                     0.1        5.927371             0.500123            True
```

## OCO Top
```text
 bar_ticks  horizon                family                          state_id quality_tier  annualized_test_fills  mean_gross_pips_test  median_gross_pips_test  gross_std_test  hit_rate_gross_test  selection_pass
       100        6       oco_first_touch          oco_first_touch__all__k2            C          336977.656732              0.205285                     0.2        5.787663             0.517760            True
       100        5       oco_first_touch          oco_first_touch__all__k2            C          334768.581343              0.210905                     0.2        5.237746             0.519362            True
       100        4       oco_first_touch          oco_first_touch__all__k2            C          330216.099230              0.216374                     0.2        4.628447             0.522390            True
       100        3       oco_first_touch          oco_first_touch__all__k2            C          319521.994580              0.219353                     0.2        3.942282             0.528444            True
       100        6       oco_first_touch          oco_first_touch__all__k3            C          318289.902045              0.176796                     0.2        5.514494             0.520781            True
       100        5       oco_first_touch          oco_first_touch__all__k3            C          307297.425940              0.185418                     0.1        4.988996             0.522707            True
       100        2       oco_first_touch          oco_first_touch__all__k2            C          291875.492803              0.220044                     0.2        3.163636             0.539128            True
       100        4       oco_first_touch          oco_first_touch__all__k3            C          289434.048722              0.191413                     0.1        4.424635             0.526871            True
       100        5 oco_first_touch_clean    oco_first_touch_clean__all__k3            A          262933.757750              1.287730                     0.7        3.942576             0.602161            True
       100        2 oco_first_touch_clean    oco_first_touch_clean__all__k2            B          260298.278527              0.782092                     0.4        2.545806             0.599669            True
       100        6 oco_first_touch_clean    oco_first_touch_clean__all__k3            A          259708.913854              1.643299                     1.0        4.277387             0.624333            True
       100        4 oco_first_touch_clean    oco_first_touch_clean__all__k3            B          259534.637366              0.948903                     0.5        3.585296             0.582728            True
       100        3 oco_first_touch_clean    oco_first_touch_clean__all__k2            A          259310.956760              1.276187                     0.8        3.058438             0.635772            True
       100        3       oco_first_touch          oco_first_touch__all__k3            C          258968.021114              0.202262                     0.2        3.808380             0.535229            True
       100        4 oco_first_touch_clean    oco_first_touch_clean__all__k2            A          244302.956437              1.806211                     1.2        3.515132             0.674227            True
       100        3 oco_first_touch_clean    oco_first_touch_clean__all__k3            B          242265.165266              0.661908                     0.3        3.163039             0.569694            True
       100        5 oco_first_touch_clean    oco_first_touch_clean__all__k2            A          227418.739777              2.338977                     1.7        3.897814             0.709991            True
       100        6       oco_first_touch          oco_first_touch__all__k5            C          222807.045688              0.234618                     0.2        5.294090             0.524872            True
       100        6       oco_first_touch oco_first_touch__low_cost_q50__k2            C          220473.539972              0.201168                     0.2        5.655154             0.518456            True
       100        5       oco_first_touch oco_first_touch__low_cost_q50__k2            C          219035.383305              0.208226                     0.2        5.109126             0.519673            True
```

## Selection Summary
```text
    library  rows_total  rows_pass  pass_rate  mean_annualized_fills_all  mean_annualized_fills_pass  mean_gross_all  mean_gross_pass  tier_a_rows  tier_b_rows  tier_c_rows
directional        2088        490   0.234674               17586.021336                33033.659795        0.059956         0.135158            0           49          441
        oco        2160        995   0.460648               24050.282215                45047.978110        3.285186         1.922642          146          408          441
```
