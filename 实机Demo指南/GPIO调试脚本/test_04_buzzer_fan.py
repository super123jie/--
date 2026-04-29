"""单测脚本 4：蜂鸣器 + 风扇

接线：
- 蜂鸣器 + → GPIO21 (Pin 40)
- 蜂鸣器 - → GND
- 风扇通过继电器 4 (GPIO20) 控制（简化版）；或 PWM via GPIO12

预期：
- 蜂鸣器响 3 声短鸣
- 风扇启动 2 秒，停止

运行：
    python3 test_04_buzzer_fan.py
"""
from gpiozero import OutputDevice, Buzzer
from time import sleep

BUZZER_PIN = 21
FAN_RELAY_PIN = 20   # 简化版用继电器开关；PWM 版改成 GPIO12 + 三极管


def main():
    buz = Buzzer(BUZZER_PIN)
    print("→ 蜂鸣器 3 短鸣")
    for _ in range(3):
        buz.on(); sleep(0.15); buz.off(); sleep(0.15)

    fan = OutputDevice(FAN_RELAY_PIN, active_high=False, initial_value=False)
    print("→ 风扇启动")
    fan.on()
    sleep(2.5)
    print("→ 风扇停止")
    fan.off()
    print("OK")


if __name__ == "__main__":
    main()
