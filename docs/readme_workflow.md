# `emeasure.workflow` 使用说明

`emeasure.workflow` 提供与具体仪器驱动无关的测量流程控制工具，包括可取消延时、条件轮询和多种稳态等待方法。

当前公开函数包括：

| 类别 | 函数 | 用途 |
| --- | --- | --- |
| 延时 | `sleep()` | 使用单调时钟进行可取消延时 |
| 延时 | `delay()` | `sleep()` 的同义包装 |
| 条件等待 | `wait_until()` | 轮询任意条件，直到连续满足指定次数 |
| 稳态等待 | `wait_stable_range()` | 等待最近窗口的峰峰值小于容差 |
| 稳态等待 | `wait_stable_target()` | 等待最近窗口全部进入已知目标范围 |
| 稳态等待 | `wait_stable()` | 用 MK、Theil–Sen 和 TOST 判断未知终值是否稳定 |

## 1. 导入方式

建议从公开模块导入，不要直接从以下划线开头的内部文件导入：

```python
from emeasure.workflow import (
    ConditionEvaluationError,
    MeasurementReadError,
    StabilityTimeoutError,
    WaitTimeoutError,
    WorkflowCancelledError,
    delay,
    sleep,
    wait_stable,
    wait_stable_range,
    wait_stable_target,
    wait_until,
)
```

统计型 `wait_stable()` 会使用 `emeasure.statistics` 中的 MK、Theil–Sen、TOST 和 Hampel 算法，因此需要安装 NumPy 和 SciPy。

## 2. `sleep()`：可取消延时

```python
sleep(
    seconds,
    *,
    cancel_event=None,
    check_interval=0.1,
) -> None
```

`sleep()` 使用单调时钟计时，因此修改系统日期或系统时间不会改变等待时长。

参数说明：

| 参数 | 含义 |
| --- | --- |
| `seconds` | 等待秒数，必须是有限的非负数；允许为 `0` |
| `cancel_event` | 可选的取消事件，需要提供可调用的 `is_set()` 方法 |
| `check_interval` | 等待期间检查取消状态的最大间隔，必须大于 `0` |

基础示例：

```python
from emeasure.workflow import sleep

instrument.set_voltage(1.0)
sleep(0.5)
value = instrument.measure_voltage()
```

`check_interval` 只影响取消响应速度，不改变目标等待时长。例如 `check_interval=0.05` 表示等待期间最多约每 0.05 秒检查一次取消状态。

### 使用 `threading.Event` 取消

标准库的 `threading.Event` 可以直接作为 `cancel_event`：

```python
import threading

from emeasure.workflow import WorkflowCancelledError, sleep

stop_event = threading.Event()

# 示例中在 0.2 秒后请求取消。
timer = threading.Timer(0.2, stop_event.set)
timer.start()

try:
    sleep(
        10.0,
        cancel_event=stop_event,
        check_interval=0.05,
    )
except WorkflowCancelledError as exc:
    print(exc.operation)  # "sleep"
    print(exc.elapsed)    # 取消前已经等待的秒数
finally:
    timer.cancel()
```

## 3. `delay()`：延时别名

```python
delay(
    seconds,
    *,
    cancel_event=None,
    check_interval=0.1,
) -> None
```

`delay()` 直接调用 `sleep()`，参数、异常和取消行为完全相同。它适合让测量流程读起来更自然：

```python
from emeasure.workflow import delay

source.set_output(True)
delay(1.0)
reading = meter.read()
```

如果项目希望保持统一风格，可以只选择 `sleep()` 或 `delay()` 中的一个使用。

## 4. `CancellationEvent` 接口

`CancellationEvent` 是一个协议类型。传入对象不需要继承某个特定类，只要提供以下方法即可：

```python
class CancellationEvent:
    def is_set(self) -> bool:
        ...
```

因此 `threading.Event`、进程间事件或自定义的停止标志都可以使用。取消后会抛出 `WorkflowCancelledError`，而不是返回一个容易被忽略的特殊值。

## 5. `wait_until()`：等待任意条件

```python
wait_until(
    condition,
    *,
    timeout,
    interval=0.5,
    min_wait=0.0,
    confirmations=1,
    cancel_event=None,
    cancel_check_interval=0.1,
    on_poll=None,
) -> WaitUntilResult
```

`wait_until()` 周期性调用无参数函数 `condition()`，将返回值转换为 `bool`。只有条件连续为真达到 `confirmations` 次后才返回。

参数说明：

| 参数 | 含义 |
| --- | --- |
| `condition` | 无参数可调用对象；返回值按 `bool(value)` 判断 |
| `timeout` | 最大总等待时间，必须大于 `0` |
| `interval` | 两次条件检查之间的间隔，必须大于 `0` |
| `min_wait` | 第一次检查前的最短等待时间，必须满足 `0 <= min_wait < timeout` |
| `confirmations` | 条件需要连续为真的次数，默认 `1` |
| `cancel_event` | 可选取消事件 |
| `cancel_check_interval` | 睡眠期间的取消检查间隔 |
| `on_poll` | 每次成功执行条件函数后调用的状态回调 |

### 基础示例

```python
from emeasure.workflow import wait_until

result = wait_until(
    instrument.is_ready,
    timeout=30.0,
    interval=0.2,
    min_wait=1.0,
    confirmations=3,
)

print(result.value)     # 最后一次 condition() 的原始返回值
print(result.elapsed)   # 总耗时
print(result.attempts)  # 条件函数总调用次数
```

当一次检查为假时，连续成功计数会重置为零。`confirmations=3` 因而可以避免单次状态抖动导致过早继续。

### 条件返回测量结果

条件不一定只返回 `True` 或 `False`。以下示例在温度进入范围后返回温度值，否则返回 `None`：

```python
from emeasure.workflow import wait_until

def temperature_if_ready():
    temperature = controller.read_temperature()
    if abs(temperature - 25.0) <= 0.1:
        return temperature
    return None

result = wait_until(
    temperature_if_ready,
    timeout=120.0,
    interval=0.5,
    confirmations=2,
)

stable_temperature = float(result.value)
```

注意：如果有效结果本身可能是 `0`、空字符串或空容器，它们会被当作假值。此时应让条件明确返回 `True`，或返回一个始终为真的自定义结果对象。

### 轮询回调

```python
from emeasure.workflow import WaitUntilPoll, wait_until

def report_poll(status: WaitUntilPoll) -> None:
    print(
        status.attempt,
        status.condition_met,
        status.consecutive_successes,
        status.elapsed,
    )

result = wait_until(
    instrument.is_ready,
    timeout=30.0,
    on_poll=report_poll,
)
```

`WaitUntilPoll` 字段：

| 字段 | 含义 |
| --- | --- |
| `value` | 本次条件函数的原始返回值 |
| `condition_met` | `bool(value)` 的结果 |
| `elapsed` | 从等待开始到本次检查完成的秒数 |
| `attempt` | 当前检查序号，从 1 开始 |
| `consecutive_successes` | 当前连续成功次数 |
| `required_confirmations` | 要求的连续成功次数 |

`WaitUntilResult` 字段：

| 字段 | 含义 |
| --- | --- |
| `value` | 最后一次条件函数的原始返回值 |
| `elapsed` | 总耗时 |
| `attempts` | 条件函数调用总次数 |
| `consecutive_successes` | 返回时的连续成功次数 |
| `required_confirmations` | 要求的连续成功次数 |

`timeout` 包含 `min_wait`、条件函数运行时间和回调运行时间。回调是同步执行的；如果回调抛出异常，该异常会直接向上传播。

## 6. 三种稳态等待方法如何选择

| 方法 | 最终值 | 判定条件 | 特点 |
| --- | --- | --- | --- |
| `wait_stable_range()` | 可以未知 | 最近窗口峰峰值不超过容差 | 最简单、最快，适合低噪声数据 |
| `wait_stable_target()` | 必须已知 | 最近窗口的所有值都位于目标带内 | 适合温度、电压、位置等受控量 |
| `wait_stable()` | 可以未知 | 无显著趋势、漂移足够小、相邻窗口等效 | 判定更完整，但需要更多样本 |

稳态函数都主动调用 `getter()` 读取标量测量值。`getter()` 应当：

- 不接收参数；
- 返回能够转换成 `float` 的有限标量；
- 不在内部进行很长时间的阻塞；
- 让驱动异常正常抛出，以便工作流包装为 `MeasurementReadError`。

## 7. 稳态函数的公共参数

三种稳态函数共享以下流程控制参数：

| 参数 | 含义 |
| --- | --- |
| `sample_interval` | 两次测量之间的间隔，默认 `0.5` 秒 |
| `timeout` | 包括预等待、读数和回调在内的最大总时间 |
| `min_wait` | 第一次读取前的可取消预等待 |
| `confirmations` | 稳态条件需要连续满足的检查次数，默认 `2` |
| `check_every` | 缓冲区填满后，每增加多少个样本重新检查一次 |
| `cancel_event` | 可选取消事件 |
| `cancel_check_interval` | 等待采样期间的取消检查间隔 |
| `on_sample` | 每次获得原始读数后执行的回调 |
| `on_check` | 每次完成稳态判定后执行的回调 |

调用开始后，函数先等待 `min_wait`，然后立即读取第一个样本。缓冲区填满以前不会执行稳态判断。

如果没有指定 `check_every`，默认值是 `max(1, window_size // 2)`。相邻检查窗口通常会重叠，但每次确认之间一定包含新样本。任何一次检查失败都会把连续成功计数重置为零。

### 公共 Hampel 尖峰参数

三种函数默认只在稳态判断之前对当前窗口使用 Hampel 滤波：

| 参数 | 含义 |
| --- | --- |
| `hampel_window=7` | Hampel 局部窗口；设为 `None` 可关闭滤波 |
| `hampel_threshold=3.5` | MAD 鲁棒标准差倍数 |
| `hampel_absolute_tolerance=0.0` | 尖峰检测的最小绝对偏差门槛 |

被 Hampel 识别的孤立尖峰会以局部中位数替换后再参与判定。原始测量不会被修改，仍可通过 `on_sample` 保存。最终结果中的 `filtered_window` 是用于判定的窗口。

如果已经能估计仪器噪声或最小分辨率，建议把 `hampel_absolute_tolerance` 设置成有物理意义的最小异常幅度，以避免 MAD 为零或很小时过度标记。

## 8. `wait_stable_range()`：峰峰值稳定

```python
wait_stable_range(
    getter,
    *,
    tolerance,
    window_size=10,
    sample_interval=0.5,
    timeout=120.0,
    min_wait=0.0,
    confirmations=2,
    check_every=None,
    cancel_event=None,
    cancel_check_interval=0.1,
    hampel_window=7,
    hampel_threshold=3.5,
    hampel_absolute_tolerance=0.0,
    on_sample=None,
    on_check=None,
) -> StabilityResult
```

判定条件为：

```text
max(filtered_window) - min(filtered_window) <= tolerance
```

参数：

| 参数 | 含义 |
| --- | --- |
| `tolerance` | 允许的最大峰峰值，必须大于 `0` |
| `window_size` | 最近窗口的样本数，至少为 3 |

返回的 `result.value` 是最终滤波窗口的算术平均值。

示例：

```python
from emeasure.workflow import wait_stable_range

result = wait_stable_range(
    meter.read_voltage,
    tolerance=0.002,
    window_size=10,
    sample_interval=0.1,
    timeout=20.0,
    confirmations=2,
    hampel_absolute_tolerance=0.01,
)

print(result.value)
print(result.last_check.diagnostics.peak_to_peak)
```

这一方法速度快、含义直观，但它不会单独检验很慢的趋势。如果窗口较短，缓慢爬升的数据也可能暂时具有很小的峰峰值。

## 9. `wait_stable_target()`：已知目标值稳定

```python
wait_stable_target(
    getter,
    *,
    target,
    tolerance,
    window_size=5,
    sample_interval=0.5,
    timeout=120.0,
    min_wait=0.0,
    confirmations=2,
    check_every=None,
    cancel_event=None,
    cancel_check_interval=0.1,
    hampel_window=7,
    hampel_threshold=3.5,
    hampel_absolute_tolerance=0.0,
    on_sample=None,
    on_check=None,
) -> StabilityResult
```

判定条件为：

```text
max(abs(filtered_window - target)) <= tolerance
```

也就是说，最近窗口内的每一个值都必须位于闭区间：

```text
[target - tolerance, target + tolerance]
```

参数：

| 参数 | 含义 |
| --- | --- |
| `target` | 已知目标值，必须是有限数 |
| `tolerance` | 目标值两侧允许的绝对误差，必须大于 `0` |
| `window_size` | 最近窗口的样本数，至少为 3 |

返回的 `result.value` 是最终滤波窗口的算术平均值。

示例：等待温度连续落在 `25.0 ± 0.1 °C` 范围内：

```python
from emeasure.workflow import wait_stable_target

result = wait_stable_target(
    controller.read_temperature,
    target=25.0,
    tolerance=0.1,
    window_size=8,
    sample_interval=0.5,
    timeout=180.0,
    confirmations=3,
)

print(result.value)
print(result.last_check.diagnostics.maximum_error)
```

该方法只检查是否进入目标范围，不要求窗口峰峰值小于 `tolerance`。一个窗口可以同时包含 `target - tolerance` 和 `target + tolerance`，并仍然通过目标带判断。

## 10. `wait_stable()`：未知终值的统计稳态判断

```python
wait_stable(
    getter,
    *,
    equivalence_tolerance,
    drift_tolerance=None,
    window_size=10,
    alpha=0.05,
    sample_interval=0.5,
    timeout=120.0,
    min_wait=0.0,
    confirmations=2,
    check_every=None,
    cancel_event=None,
    cancel_check_interval=0.1,
    hampel_window=7,
    hampel_threshold=3.5,
    hampel_absolute_tolerance=0.0,
    on_sample=None,
    on_check=None,
) -> StabilityResult
```

该函数保存两个相邻窗口，因此开始第一次判断前至少需要 `2 × window_size` 个样本。每个窗口各有 `window_size` 个值。

一次检查只有同时满足以下三项才算稳定：

1. MK 检验没有发现显著单调趋势；
2. Theil–Sen 在两个窗口范围内估计的总变化量绝对值不超过 `drift_tolerance`；
3. Welch TOST 证明新旧窗口均值差位于 `±equivalence_tolerance` 内。

统计参数：

| 参数 | 含义 |
| --- | --- |
| `equivalence_tolerance` | 新旧窗口均值允许的最大绝对差，必须大于 `0` |
| `drift_tolerance` | 两个窗口范围内允许的 Theil–Sen 总变化量；省略时等于 `equivalence_tolerance` |
| `window_size` | 每一个子窗口的样本数，至少为 2 |
| `alpha` | MK 和 TOST 的显著性水平，必须位于 `(0, 0.5)` |

返回的 `result.value` 是较新子窗口的滤波后平均值。

示例：

```python
from emeasure.workflow import wait_stable

result = wait_stable(
    meter.read_voltage,
    equivalence_tolerance=0.005,
    drift_tolerance=0.003,
    window_size=12,
    alpha=0.05,
    sample_interval=0.2,
    timeout=60.0,
    confirmations=2,
    hampel_window=7,
    hampel_absolute_tolerance=0.01,
)

diagnostics = result.last_check.diagnostics
print(result.value)
print(diagnostics.mann_kendall.has_trend)
print(diagnostics.theil_sen.estimated_change)
print(diagnostics.tost.equivalent)
```

统计型方法的注意事项：

- MK 的“未检出趋势”本身不能证明稳定，所以实现还会检查漂移量和窗口等效性。
- TOST 需要足够数据才能证明等效。窗口太小、噪声太大或容差太窄时，函数可能一直等到超时。
- 相邻样本如果具有很强的自相关，MK 和 TOST 的 p 值可能不够准确。可以适当增大 `sample_interval`，使相邻读数更接近独立。
- `equivalence_tolerance` 和 `drift_tolerance` 应根据测量单位和实验需求设定，不能只根据本次数据临时放宽。

## 11. 稳态状态回调

### `StabilitySample`

`on_sample` 每次收到一个原始读数后执行：

```python
from emeasure.workflow import StabilitySample

def save_sample(status: StabilitySample) -> None:
    saver.add({
        "elapsed": status.elapsed,
        "sample": status.sample,
        "voltage": status.value,
    })
```

字段：

| 字段 | 含义 |
| --- | --- |
| `value` | 未经 Hampel 替换的原始有限读数 |
| `elapsed` | 从等待开始到本次读取完成的秒数 |
| `sample` | 样本序号，从 1 开始 |

### `StabilityCheck`

`on_check` 在缓冲区填满并完成一次稳定判断后执行：

```python
from emeasure.workflow import StabilityCheck

def report_check(status: StabilityCheck) -> None:
    print(
        status.method,
        status.stable_now,
        status.consecutive_successes,
        status.value,
    )
```

字段：

| 字段 | 含义 |
| --- | --- |
| `method` | `"range"`、`"target"` 或 `"statistical"` |
| `stable_now` | 本次窗口是否通过判断 |
| `value` | 本次窗口的代表值 |
| `elapsed` | 本次判断完成时的总耗时 |
| `samples` | 到目前为止读取的样本总数 |
| `window_size` | 范围/目标窗口长度，或统计方法的单个子窗口长度 |
| `window_outlier_count` | 当前完整判定窗口中由 Hampel 标记的点数 |
| `consecutive_successes` | 当前连续通过次数 |
| `required_confirmations` | 要求的连续通过次数 |
| `filtered_window` | 实际参与判断的滤波后完整窗口 |
| `diagnostics` | 与具体方法对应的诊断对象 |

### `StabilityResult`

稳态条件连续满足后返回：

| 字段 | 含义 |
| --- | --- |
| `method` | 使用的稳态方法 |
| `value` | 最终代表值 |
| `elapsed` | 总等待时间 |
| `samples` | 读取的样本总数 |
| `window_size` | 报告窗口长度 |
| `window_outlier_count` | 最终窗口内的尖峰数量 |
| `consecutive_successes` | 返回时的连续通过次数 |
| `filtered_window` | 最终判断使用的滤波窗口 |
| `last_check` | 完整的最后一次 `StabilityCheck` |

回调同步执行，其运行时间计入 `timeout`。回调异常会直接向上传播，因此保存或显示状态的回调应尽量快速，并自行处理可恢复的记录错误。

## 12. 三种诊断对象

根据 `StabilityCheck.method`，`diagnostics` 是以下对象之一。

### `RangeStabilityDiagnostics`

| 字段 | 含义 |
| --- | --- |
| `peak_to_peak` | 当前滤波窗口的峰峰值 |
| `tolerance` | 要求的峰峰值上限 |

### `TargetStabilityDiagnostics`

| 字段 | 含义 |
| --- | --- |
| `target` | 目标值 |
| `maximum_error` | 当前窗口内最大的目标绝对误差 |
| `tolerance` | 允许的最大目标误差 |

### `StatisticalStabilityDiagnostics`

| 字段 | 含义 |
| --- | --- |
| `mann_kendall` | 完整的 `MannKendallResult` |
| `theil_sen` | 完整的 `TheilSenResult` |
| `tost` | 完整的 `TOSTResult` |
| `drift_tolerance` | 实际使用的漂移容差 |
| `equivalence_tolerance` | 实际使用的等效容差 |

这些结果对象都是只读 dataclass，适合直接记录到日志或在界面中显示。

## 13. 异常与诊断信息

所有工作流专用异常都继承 `WorkflowError`。

| 异常 | 发生条件 | 重要字段 |
| --- | --- | --- |
| `WorkflowCancelledError` | `cancel_event.is_set()` 返回真 | `operation`、`elapsed` |
| `WaitTimeoutError` | `wait_until()` 超时 | `timeout`、`elapsed`、`attempts`、`last_value`、`operation` |
| `ConditionEvaluationError` | `condition()` 抛出异常 | `elapsed`、`attempt` |
| `MeasurementReadError` | `getter()` 抛出异常，或返回值无法转换为有限浮点数 | `elapsed`、`sample` |
| `StabilityTimeoutError` | 稳态等待超时 | `timeout`、`elapsed`、`samples`、`last_check` |

`WaitTimeoutError` 同时继承 Python 的 `TimeoutError`；`StabilityTimeoutError` 又继承 `WaitTimeoutError`。

### 处理条件超时

```python
from emeasure.workflow import WaitTimeoutError, wait_until

try:
    wait_until(
        instrument.is_ready,
        timeout=10.0,
    )
except WaitTimeoutError as exc:
    print(exc.attempts)
    print(exc.last_value)
```

### 处理稳态超时

```python
from emeasure.workflow import StabilityTimeoutError, wait_stable_range

try:
    wait_stable_range(
        meter.read_voltage,
        tolerance=0.001,
        timeout=30.0,
    )
except StabilityTimeoutError as exc:
    print(exc.samples)
    if exc.last_check is not None:
        print(exc.last_check.stable_now)
        print(exc.last_check.diagnostics)
```

### 查看原始仪器异常

`ConditionEvaluationError` 和 `MeasurementReadError` 使用异常链保留了原始异常：

```python
from emeasure.workflow import MeasurementReadError, wait_stable_range

try:
    wait_stable_range(
        meter.read_voltage,
        tolerance=0.01,
        timeout=10.0,
    )
except MeasurementReadError as exc:
    print("读取失败的样本：", exc.sample)
    print("底层异常：", exc.__cause__)
```

参数错误通常直接抛出 `TypeError` 或 `ValueError`，用于在测量开始前尽早发现配置问题。

## 14. 与数据保存器组合

`on_sample` 可以把等待期间的每个原始读数保存下来，而不仅仅保存最终稳定值：

```python
from emeasure.workflow import StabilitySample, wait_stable

def record(status: StabilitySample) -> None:
    saver.add({
        "elapsed_s": status.elapsed,
        "reading": status.value,
    })

result = wait_stable(
    meter.read_voltage,
    equivalence_tolerance=0.005,
    drift_tolerance=0.003,
    window_size=10,
    sample_interval=0.2,
    timeout=60.0,
    on_sample=record,
)

print("稳定测量值：", result.value)
```

建议同时保存原始读数、最终结果、稳态方法和 `last_check.diagnostics`。这样以后可以重新检查容差是否合理，也能区分原始尖峰和滤波后的判定数据。

## 15. 完整流程示例

以下示例展示设定仪器、等待目标稳定、读取数据和保证关闭输出的基本结构：

```python
import threading

from emeasure.workflow import (
    StabilityTimeoutError,
    WorkflowCancelledError,
    wait_stable_target,
)

stop_event = threading.Event()

source.set_output(True)
try:
    controller.set_temperature(25.0)

    result = wait_stable_target(
        controller.read_temperature,
        target=25.0,
        tolerance=0.1,
        window_size=8,
        sample_interval=0.5,
        timeout=180.0,
        min_wait=2.0,
        confirmations=3,
        cancel_event=stop_event,
    )

    measurement = meter.read()
    print("稳定温度：", result.value)
    print("测量值：", measurement)

except WorkflowCancelledError:
    print("测量已取消")
except StabilityTimeoutError as exc:
    print("等待稳定超时，已读取样本数：", exc.samples)
finally:
    source.set_output(False)
```

无论成功、取消还是超时，都应在 `finally` 中让仪器回到预期状态。关闭输出、停止扫描或恢复量程等操作不应依赖稳态等待成功。

## 16. 参数选择建议

| 参数 | 选择思路 |
| --- | --- |
| `sample_interval` | 应足以让相邻读数反映新信息；不必远快于仪器或器件响应时间 |
| `window_size` | 越大越稳健但等待越久；应覆盖一段有代表性的响应时间 |
| `confirmations` | 一般使用 2～3，降低偶然窗口通过的概率 |
| `check_every` | 较小会更快响应但重复计算更多；默认半个窗口通常足够 |
| `timeout` | 应大于 `min_wait + 填满窗口所需时间`，并留出多次确认时间 |
| `tolerance` | 使用实验允许误差或仪器规格，不要只根据当前数据决定 |
| `equivalence_tolerance` | 表示相邻窗口均值在物理上可忽略的最大差异 |
| `drift_tolerance` | 表示完整统计窗口内允许的最大估计漂移 |
| `hampel_absolute_tolerance` | 可参考已知噪声、量化步长或最小有意义变化 |

统计型 `wait_stable()` 第一次检查至少需要 `2 × window_size` 个样本。例如 `window_size=10`、`sample_interval=0.5` 时，仅填满缓冲区就需要约 9.5 秒，再加上 `min_wait`、后续确认和读数耗时。设置 `timeout` 时必须考虑这一点。
