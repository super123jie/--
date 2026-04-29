"""单测脚本 3：SG90 舵机（窗帘 + 门）

接线：
- 舵机 1 信号 → GPIO13 (Pin 33) - 窗帘
- 舵机 2 信号 → GPIO19 (Pin 35) - 门
- 舵机 VCC   → 5V
- 舵机 GND   → GND

预期：每个舵机 0° → 90° → 180° → 0° 来回扫一遍。

运行：
    python3 test_03_servo.py
"""
from gpiozero import AngularServo
from time import sleep

SERVOS = {
    "窗帘": 13,
    "门":   19,
}


def sweep(name, pin):
    s = AngularServo(pin, min_angle=0, max_angle=180,
                      min_pulse_width=0.0005, max_pulse_width=0.0025)
    print(f"→ {name} 舵机 (GPIO{pin})")
    for ang in [0, 45, 90, 135, 180, 90, 0]:
        print(f"   {ang}°")
        s.angle = ang
        sleep(0.6)
    s.detach()


def main():
    for name, pin in SERVOS.items():
        sweep(name, pin)
    print("OK")


if __name__ == "__main__":
    main()
