"""单测脚本 2：4 通道继电器

接线：
- 继电器 VCC → 5V
- 继电器 GND → GND
- IN1 → GPIO5  (Pin 29)  门锁
- IN2 → GPIO6  (Pin 31)  燃气阀
- IN3 → GPIO16 (Pin 36)  电视
- IN4 → GPIO20 (Pin 38)  净化器

预期：每路依次吸合 1 秒（能听到"咔嗒"声 + 板上 LED 点亮）。

注意：
- 大多数模块是"低电平触发"（LOW = 吸合）。
- 如果你的模块是"高电平触发"，把 ACTIVE_LOW 改为 False。

运行：
    python3 test_02_relay.py
"""
from gpiozero import OutputDevice
from time import sleep

ACTIVE_LOW = True   # 如果继电器是低电平触发就 True
PINS = {
    "门锁 (IN1)":  5,
    "燃气阀 (IN2)": 6,
    "电视 (IN3)":  16,
    "净化器 (IN4)": 20,
}


def main():
    relays = {name: OutputDevice(pin, active_high=not ACTIVE_LOW, initial_value=False)
              for name, pin in PINS.items()}
    print("依次测试 4 路继电器：")
    for name, dev in relays.items():
        print(f"  → {name} 吸合")
        dev.on()
        sleep(1.5)
        print(f"    {name} 释放")
        dev.off()
        sleep(0.5)
    print("OK")


if __name__ == "__main__":
    main()
