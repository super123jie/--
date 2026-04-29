"""单测脚本 1：WS2812 LED 灯带

接线检查：
- 灯带 VCC → 5V
- 灯带 GND → GND
- 灯带 DIN → GPIO18 (Pin 12)

预期效果：
- 红 → 绿 → 蓝 → 暖白 各亮 1 秒
- 然后熄灭

先决条件：
    sudo pip install rpi_ws281x
    脚本必须用 sudo 跑（PWM 需 root）

运行：
    sudo python3 test_01_lights.py
"""
from rpi_ws281x import PixelStrip, Color
import time

LED_COUNT = 60          # 灯带 LED 数量（按你买的实际数）
LED_PIN = 18            # GPIO18（PWM）
LED_FREQ_HZ = 800000
LED_DMA = 10
LED_BRIGHTNESS = 80     # 0-255
LED_INVERT = False
LED_CHANNEL = 0


def fill(strip, r, g, b):
    for i in range(strip.numPixels()):
        strip.setPixelColor(i, Color(r, g, b))
    strip.show()


def main():
    strip = PixelStrip(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA,
                        LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
    strip.begin()
    print("→ 红色")
    fill(strip, 255, 0, 0); time.sleep(1)
    print("→ 绿色")
    fill(strip, 0, 255, 0); time.sleep(1)
    print("→ 蓝色")
    fill(strip, 0, 0, 255); time.sleep(1)
    print("→ 暖白")
    fill(strip, 255, 180, 100); time.sleep(1)
    print("→ 熄灭")
    fill(strip, 0, 0, 0)
    print("OK")


if __name__ == "__main__":
    main()
