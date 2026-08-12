# `emeasure.statistics` 使用说明

`emeasure.statistics` 提供面向实验测量数据的趋势检验、等效性检验和偶发尖峰处理工具。

当前公开接口包括：

| 类别 | 函数 | 用途 |
| --- | --- | --- |
| 趋势检验 | `mann_kendall_test()` | 判断有序数据中是否存在显著的单调上升或下降趋势 |
| 趋势估计 | `theil_sen_test()` | 鲁棒估计斜率、置信区间和整个观测区间内的变化量 |
| 等效性检验 | `tost_independent()` | 判断两组相互独立的数据均值是否在给定容差内等效 |
| 等效性检验 | `tost_paired()` | 判断两组一一对应的数据是否在给定容差内等效 |
| 鲁棒尺度 | `median_absolute_deviation()` | 计算未缩放的中位数绝对偏差 MAD |
| 鲁棒尺度 | `robust_standard_deviation()` | 使用 `1.4826 × MAD` 估计标准差 |
| 单点检测 | `mad_outlier_test()` | 判断一个新测量值是否偏离参考窗口 |
| 序列滤波 | `hampel_filter()` | 使用滑动窗口检测并处理序列中的偶发尖峰 |

## 1. 安装依赖与导入

这些函数依赖 NumPy 和 SciPy：

```bash
python -m pip install numpy scipy
```

建议始终从公开模块导入，不要直接从 `_trend.py`、`_equivalence.py` 或 `_outlier.py` 导入：

```python
from emeasure.statistics import (
    hampel_filter,
    mad_outlier_test,
    mann_kendall_test,
    median_absolute_deviation,
    robust_standard_deviation,
    theil_sen_test,
    tost_independent,
    tost_paired,
)
```

所有输入数据都应是一维、有限的实数序列。当前实现不自动忽略 `NaN` 或无穷大；应在调用前处理这些值。

## 2. Mann–Kendall 单调趋势检验

### `mann_kendall_test()`

```python
mann_kendall_test(
    values,
    *,
    alpha=0.05,
    alternative="two-sided",
) -> MannKendallResult
```

Mann–Kendall（MK）检验是一种非参数趋势检验。它不要求数据服从正态分布，也不直接假设趋势为线性，因此适合判断实验数据是否仍在持续上升或下降。

原假设是“序列不存在单调趋势”。当 `p_value < alpha` 时拒绝原假设，并认为检测到了趋势。

参数说明：

| 参数 | 含义 |
| --- | --- |
| `values` | 按采样顺序排列的一维数据，至少需要 3 个有限值 |
| `alpha` | 显著性水平，默认 `0.05` |
| `alternative="two-sided"` | 同时检测上升和下降趋势 |
| `alternative="increasing"` | 只检验上升趋势 |
| `alternative="decreasing"` | 只检验下降趋势 |

基础示例：

```python
from emeasure.statistics import mann_kendall_test

values = [1.00, 1.02, 1.05, 1.08, 1.11, 1.15]
result = mann_kendall_test(values)

print(result.has_trend)  # True
print(result.trend)      # "increasing"
print(result.p_value)    # 约 0.0085
print(result.tau)        # 1.0
```

对于近似稳定的序列：

```python
values = [1.01, 0.99, 1.00, 1.02, 0.98, 1.00]
result = mann_kendall_test(values)

if result.has_trend:
    print("仍存在趋势：", result.trend)
else:
    print("没有检出显著单调趋势")
```

`MannKendallResult` 的主要字段：

| 字段 | 含义 |
| --- | --- |
| `has_trend` | 是否在给定 `alpha` 下检出显著趋势 |
| `trend` | `"increasing"`、`"decreasing"` 或 `"none"` |
| `p_value` | 检验的 p 值 |
| `z` | 连续性修正后的标准化统计量 |
| `tau` | Kendall tau；符号表示方向，绝对值反映排序关联强度 |
| `s` | MK 原始统计量 S |
| `variance_s` | 对重复测量值修正后的 S 方差 |
| `alpha` | 实际使用的显著性水平 |
| `alternative` | 实际使用的备择假设 |
| `samples` | 样本数量 |

注意事项：

- `has_trend=False` 只表示“没有检出趋势”，不等于已经证明数据稳定。
- 如果采样非常密集，连续点之间可能存在很强的自相关，普通 MK 检验得到的 p 值可能过于乐观。
- 单侧检验应当在分析前已经明确趋势方向时使用，不应根据观察到的数据临时选择方向。
- 在稳态判断中，建议同时限制 Theil–Sen 漂移量，并用 TOST 检查相邻窗口是否等效。

## 3. Theil–Sen 鲁棒斜率估计

### `theil_sen_test()`

```python
theil_sen_test(
    values,
    x=None,
    *,
    confidence=0.95,
    method="separate",
) -> TheilSenResult
```

Theil–Sen 方法取所有点对斜率的中位数，因此比普通最小二乘直线更不容易被单个尖峰拉偏。它适合回答两个问题：

1. 数据变化的典型速率是多少？
2. 斜率置信区间是否完全位于零的一侧？

参数说明：

| 参数 | 含义 |
| --- | --- |
| `values` | 因变量序列，至少需要 3 个有限值 |
| `x` | 可选的自变量；省略时使用 `0, 1, 2, ...` 作为样本序号 |
| `confidence` | 斜率置信区间的置信水平，默认 `0.95` |
| `method="separate"` | 截距为 `median(y) - slope × median(x)` |
| `method="joint"` | 截距为 `median(y - slope × x)` |

含一个尖峰的数据示例：

```python
from emeasure.statistics import theil_sen_test

values = [0.0, 0.5, 1.0, 1.5, 2.0, 10.0, 3.0, 3.5, 4.0, 4.5]
result = theil_sen_test(values)

print(result.slope)             # 0.5，每个采样点约增加 0.5
print(result.has_trend)         # True
print(result.trend)             # "increasing"
print(result.estimated_change)  # 4.5，整个窗口内的估计变化量
```

当采样间隔不是 1 时，应传入实际时间：

```python
time_s = [0, 2, 4, 6, 8, 10]
voltage_v = [1.00, 1.01, 1.02, 1.03, 1.04, 1.05]

result = theil_sen_test(voltage_v, x=time_s)
print(result.slope)             # 单位为 V/s
print(result.estimated_change)  # 单位为 V
```

`TheilSenResult` 的主要字段和属性：

| 字段或属性 | 含义 |
| --- | --- |
| `has_trend` | 斜率置信区间是否完全位于零的一侧 |
| `trend` | `"increasing"`、`"decreasing"` 或 `"none"` |
| `slope` | 鲁棒斜率估计 |
| `intercept` | 截距估计 |
| `slope_low`、`slope_high` | 斜率置信区间 |
| `confidence` | 置信水平 |
| `method` | 截距计算方法 |
| `samples` | 样本数量 |
| `x_span` | `max(x) - min(x)` |
| `estimated_change` | `slope × x_span`，整个窗口内的估计变化量 |
| `change_low`、`change_high` | 斜率置信区间换算成整个窗口内的变化量 |

用于稳定判断时，不应只看 `has_trend`，还应设置具有物理意义的漂移容差：

```python
drift_tolerance = 0.02  # 允许窗口内最多变化 0.02 V
result = theil_sen_test(values)

small_enough = abs(result.estimated_change) <= drift_tolerance
```

## 4. TOST 等效性检验

传统差异检验中的“没有显著差异”不等于“已经证明相等”。TOST（two one-sided tests）直接检验两组均值之差是否严格落在预先规定的等效区间内。

本模块始终定义：

```text
mean_difference = mean(sample_b) - mean(sample_a)
```

等效边界 `low` 和 `high` 必须由实验允许误差、仪器精度或工程需求预先确定，而不应仅根据当前数据临时设定。

### `tost_independent()`

```python
tost_independent(
    sample_a,
    sample_b,
    *,
    low,
    high,
    alpha=0.05,
    equal_var=False,
) -> TOSTResult
```

用于两组相互独立的数据。例如两个器件、两次独立实验或来自不同样本的测量。

参数说明：

| 参数 | 含义 |
| --- | --- |
| `sample_a`、`sample_b` | 两个独立样本，每组至少 2 个有限值，样本数可以不同 |
| `low`、`high` | 均值差 `mean_b - mean_a` 的等效区间，要求 `low < high` |
| `alpha` | 显著性水平，默认 `0.05`，且必须小于 `0.5` |
| `equal_var=False` | 默认使用 Welch 方法，不假设两组方差相同 |
| `equal_var=True` | 使用合并方差；只有在共同方差假设合理时才使用 |

示例：判断两批独立测量的平均值差是否在 ±0.2 内：

```python
from emeasure.statistics import tost_independent

sample_a = [10.00, 10.10, 9.90, 10.05, 9.95, 10.02, 9.98, 10.03]
sample_b = [10.02, 10.08, 9.94, 10.06, 9.97, 10.01, 10.00, 10.04]

result = tost_independent(
    sample_a,
    sample_b,
    low=-0.2,
    high=0.2,
)

print(result.equivalent)       # True
print(result.method)           # "independent-welch"
print(result.mean_difference)  # 约 0.01125
print(result.p_value)          # 约 5.19e-6
```

### `tost_paired()`

```python
tost_paired(
    sample_a,
    sample_b,
    *,
    low,
    high,
    alpha=0.05,
) -> TOSTResult
```

用于一一对应的成对数据。例如同一器件校准前后、同一设定点的两次重复扫描，或同一时间点由两种方法得到的结果。

两组数据长度必须相同，并且相同位置的数据必须互相对应。

```python
from emeasure.statistics import tost_paired

before = [10.00, 10.10, 9.90, 10.05, 9.95, 10.02, 9.98, 10.03]
after = [10.02, 10.08, 9.94, 10.06, 9.97, 10.01, 10.00, 10.04]

result = tost_paired(
    before,
    after,
    low=-0.05,
    high=0.05,
)

print(result.equivalent)       # True
print(result.method)           # "paired"
print(result.mean_difference)  # 约 0.01125
```

`TOSTResult` 的主要字段：

| 字段 | 含义 |
| --- | --- |
| `equivalent` | 两个单侧检验是否都通过，即 `p_value < alpha` |
| `method` | `"independent-welch"`、`"independent-pooled"` 或 `"paired"` |
| `mean_a`、`mean_b` | 两组样本均值 |
| `mean_difference` | `mean_b - mean_a` |
| `equivalence_low`、`equivalence_high` | 等效区间 |
| `standard_error` | 均值差的标准误差 |
| `degrees_of_freedom` | t 检验自由度 |
| `t_lower`、`p_lower` | 针对下边界的单侧检验结果 |
| `t_upper`、`p_upper` | 针对上边界的单侧检验结果 |
| `p_value` | `max(p_lower, p_upper)`，TOST 的总体 p 值 |
| `alpha` | 显著性水平 |
| `confidence_level` | 等效置信区间的置信水平，即 `1 - 2 × alpha` |
| `confidence_low`、`confidence_high` | 均值差的等效置信区间 |
| `samples_a`、`samples_b` | 两组样本数 |

当 `alpha=0.05` 时，返回的是 90% 置信区间。该区间严格位于 `(low, high)` 内，与 TOST 判断为等效是等价的。

如果 `equivalent=False`，正确解释是“现有数据不足以证明两组在该容差内等效”，而不是已经证明两组不等效。样本太少、噪声太大或等效区间太窄都可能导致这一结果。

## 5. MAD 鲁棒尺度函数

MAD 是 median absolute deviation，即中位数绝对偏差：

```text
MAD = median(abs(x - median(x)))
```

与普通标准差相比，中位数和 MAD 不容易被少量极端值明显拉偏，适合含偶发尖峰的实验数据。

### `median_absolute_deviation()`

```python
median_absolute_deviation(values) -> float
```

返回未缩放的 MAD，至少需要 1 个有限值。

```python
from emeasure.statistics import median_absolute_deviation

reference = [1.00, 1.01, 0.99, 1.00, 1.02, 0.98, 1.01]
mad = median_absolute_deviation(reference)

print(mad)  # 约 0.01
```

### `robust_standard_deviation()`

```python
robust_standard_deviation(values) -> float
```

返回：

```text
robust_std = 1.4826022185 × MAD
```

对于近似正态分布的噪声，这一缩放使结果可按普通标准差的尺度解释。

```python
from emeasure.statistics import robust_standard_deviation

reference = [1.00, 1.01, 0.99, 1.00, 1.02, 0.98, 1.01]
noise_std = robust_standard_deviation(reference)

print(noise_std)  # 约 0.01483
```

如果数据几乎完全相同，MAD 可能等于零。此时不应简单地把任何非零偏差都当作尖峰；在尖峰检测函数中应设置 `absolute_tolerance`。

## 6. 单个新测量值的 MAD 检测

### `mad_outlier_test()`

```python
mad_outlier_test(
    value,
    reference,
    *,
    threshold=3.5,
    absolute_tolerance=0.0,
) -> MADPointResult
```

该函数使用一段参考数据判断一个新值是否为异常点。判定条件为：

```text
abs(value - median) > max(
    threshold × 1.4826 × MAD,
    absolute_tolerance,
)
```

参数说明：

| 参数 | 含义 |
| --- | --- |
| `value` | 要判断的新测量值 |
| `reference` | 参考窗口，至少需要 3 个有限值 |
| `threshold` | 鲁棒标准差倍数，默认 `3.5` |
| `absolute_tolerance` | 最小绝对偏差门槛，默认 `0.0` |

示例：

```python
from emeasure.statistics import mad_outlier_test

reference = [1.00, 1.01, 0.99, 1.00, 1.02, 0.98, 1.01]
result = mad_outlier_test(
    1.80,
    reference,
    threshold=3.5,
    absolute_tolerance=0.05,
)

print(result.is_outlier)  # True
print(result.median)      # 1.0
print(result.deviation)   # 0.8
print(result.cutoff)      # 约 0.05189
```

`MADPointResult` 字段：

| 字段 | 含义 |
| --- | --- |
| `is_outlier` | 新值是否超过判定门槛 |
| `value` | 被判断的测量值 |
| `median` | 参考窗口中位数 |
| `mad` | 参考窗口的未缩放 MAD |
| `robust_std` | `1.4826 × MAD` |
| `deviation` | 新值到参考中位数的绝对偏差 |
| `cutoff` | 最终使用的门槛 |
| `threshold` | 鲁棒标准差倍数 |
| `absolute_tolerance` | 绝对偏差下限 |
| `reference_samples` | 参考样本数 |

该函数适合在线测量：保留最近若干个可信值作为 `reference`，每次获得一个新读数后立即检查。

## 7. Hampel 滑动窗口尖峰处理

### `hampel_filter()`

```python
hampel_filter(
    values,
    *,
    window_size=11,
    threshold=3.5,
    absolute_tolerance=0.0,
    replacement="median",
) -> HampelResult
```

Hampel 方法在每个位置建立一个局部窗口，用局部中位数和局部 MAD 判断该点是否为孤立尖峰。

参数说明：

| 参数 | 含义 |
| --- | --- |
| `values` | 至少包含 3 个有限值的一维序列 |
| `window_size` | 奇数且不小于 3；实验数据中常用 7～21 |
| `threshold` | 鲁棒标准差倍数，默认 `3.5` |
| `absolute_tolerance` | 最小绝对偏差门槛，可根据仪器噪声或分辨率设定 |
| `replacement="median"` | 用局部中位数替换尖峰 |
| `replacement="nan"` | 用 `NaN` 标记尖峰 |
| `replacement="drop"` | 从 `filtered` 中删除尖峰，因此输出长度可能改变 |
| `replacement="none"` | 只检测，不修改 `filtered` 中的数值 |

示例：

```python
from emeasure.statistics import hampel_filter

values = [1.00, 1.01, 0.99, 1.02, 4.50, 1.00, 0.98, 1.01, 1.00]
result = hampel_filter(
    values,
    window_size=7,
    threshold=3.5,
    absolute_tolerance=0.05,
    replacement="median",
)

print(result.outlier_indices.tolist())
# [4]

print(result.filtered.tolist())
# [1.0, 1.01, 0.99, 1.02, 1.01, 1.0, 0.98, 1.01, 1.0]
```

`HampelResult` 的主要字段和属性：

| 字段或属性 | 含义 |
| --- | --- |
| `original` | 原始数据的 NumPy 数组副本 |
| `filtered` | 按 `replacement` 处理后的数组 |
| `outlier_mask` | 与原始数据等长的布尔掩码 |
| `local_median` | 每个位置的局部中位数 |
| `local_mad` | 每个位置的局部 MAD |
| `local_robust_std` | 每个位置的 `1.4826 × MAD` |
| `local_cutoff` | 每个位置最终使用的判定门槛 |
| `window_size` | 实际使用的窗口长度；数据较短时可能自动缩小 |
| `threshold` | 鲁棒标准差倍数 |
| `absolute_tolerance` | 绝对偏差门槛 |
| `replacement` | 输出处理方式 |
| `outlier_indices` | 所有尖峰位置的 NumPy 索引数组 |
| `outlier_count` | 检出的尖峰数量 |

尖峰处理注意事项：

- Hampel 方法适合处理孤立尖峰，不适合把持续多个点的阶跃变化直接当作异常删除。
- 连续多个异常点可能表示器件状态真实改变、量程切换或连接故障，应交给测量流程进一步判断。
- 用于统计分析时，建议保留 `original` 和 `outlier_mask`，不要只保存处理后的数据。
- 如果后续算法不能接受 `NaN`，不要直接把 `replacement="nan"` 的结果传给本模块的其他函数。

## 8. 用于测量稳态判断的组合示例

一个较稳妥的稳态判断通常包含三个不同问题：

1. 是否存在孤立尖峰？
2. 最近窗口是否仍有趋势或明显漂移？
3. 相邻两个窗口是否已经在工程容差内等效？

```python
from emeasure.statistics import (
    hampel_filter,
    mann_kendall_test,
    theil_sen_test,
    tost_independent,
)

older_raw = [1.002, 1.004, 1.003, 1.005, 1.004, 1.003, 1.004]
newer_raw = [1.005, 1.003, 1.004, 1.004, 1.006, 1.003, 1.004]

# 1. 清理两个窗口中的孤立尖峰。
older = hampel_filter(
    older_raw,
    window_size=7,
    absolute_tolerance=0.01,
).filtered
newer = hampel_filter(
    newer_raw,
    window_size=7,
    absolute_tolerance=0.01,
).filtered

# 2. 新窗口不能存在显著趋势，而且窗口内估计漂移必须足够小。
mk = mann_kendall_test(newer)
slope = theil_sen_test(newer)
no_trend = not mk.has_trend
small_drift = abs(slope.estimated_change) <= 0.01

# 3. 两个窗口的均值差必须能够证明落在 ±0.01 内。
equivalence = tost_independent(
    older,
    newer,
    low=-0.01,
    high=0.01,
)

is_stable = no_trend and small_drift and equivalence.equivalent
print(is_stable)
```

在真实测量流程中，通常还应要求上述条件连续满足两次或三次，并设置最大等待时间。这样可以降低一次偶然窗口造成误判的概率。

## 9. 常见选择建议

| 需求 | 建议函数 |
| --- | --- |
| 判断数据是否仍持续上升或下降 | `mann_kendall_test()` |
| 估计每秒或每个采样点的漂移速度 | `theil_sen_test()` |
| 判断两个独立测量窗口是否足够接近 | `tost_independent()` |
| 判断同一批对象前后测量是否足够接近 | `tost_paired()` |
| 估计不易受尖峰影响的噪声尺度 | `robust_standard_deviation()` |
| 在线判断一个新读数是否为尖峰 | `mad_outlier_test()` |
| 批量检测并处理整段序列的尖峰 | `hampel_filter()` |

统计判断应与实验允许误差结合使用。`alpha`、等效边界、漂移容差、`absolute_tolerance` 和窗口长度最好在正式测量前根据仪器噪声、采样周期和待测器件的时间常数确定。
