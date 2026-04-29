"""单测脚本 5：3 个传感器（DHT22 / MQ-2 / PIR）

接线：
- DHT22 DATA → GPIO4 (Pin 7)，VCC → 3.3V
- MQ-2 DO    → GPIO17 (Pin 11)，VCC → 5V
- PIR  OUT   → GPIO27 (Pin 13)，VCC → 5V

预期：循环 30 秒，每 2 秒打印温湿度 + 燃气是否触发 + PIR 是否检测到人。

调测试方法：
- DHT22：手指捂住模块 5 秒看温度上升
- MQ-2：打火机不点火，按住放气阀靠近模块 → DO 变 LOW
- PIR：靠近模块挥手 → OUT 变 HIGH

依赖：
    pip install adafruit-circuitpython-dht

运行：
    python3 test_05_sensors.py
"""
import time
from gpiozero import DigitalInputDevice

# DHT22 用 Adafruit 库（gpiozero 不直接支持温湿度协议）
try:
    import board
    import adafruit_dht
    DHT22_AVAILABLE = True
    dht_sensor = adafruit_dht.DHT22(board.D4)
except ImportError:
    DHT22_AVAILABLE = False
    print("[警告] adafruit-circuitpython-dht 未安装，跳过 DHT22")

mq2 = DigitalInputDevice(17, pull_up=False)
pir = DigitalInputDevice(27, pull_up=False)


def read_dht():
    if not DHT22_AVAILABLE:
        return None, None
    try:
        return dht_sensor.temperature, dht_sensor.humidity
    except Exception as e:
        return None, f"err={e}"


def main():
    print("循环 30 秒读取传感器（Ctrl+C 停止）...")
    t0 = time.time()
    while time.time() - t0 < 30:
        t, h = read_dht()
        gas_triggered = (mq2.value == 0)  # DO 默认高，触发拉低
        person = pir.value == 1
        print(f"[{int(time.time()-t0):2d}s] "
                f"温度={t}℃ 湿度={h}%RH "
                f"燃气={'⚠️触发' if gas_triggered else '正常'} "
                f"人体={'有人' if person else '无'}")
        time.sleep(2)
    print("OK")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n用户中断")
