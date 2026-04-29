"""综合测试脚本：模拟『睡眠模式』完整动作链

效果：
- 灯带渐暗到 15%（夜灯模式，暖白）
- 风扇启动（空调模拟）
- 舵机 1 转到 180°（拉窗帘）
- 继电器 1 吸合（锁门）
- 蜂鸣器一声短鸣（确认）

10 秒后恢复（关风扇、舵机回 0°、继电器释放、灯带熄灭）。

运行（需 sudo，因 WS2812 PWM 需要 root）：
    sudo python3 test_99_all.py
"""
from gpiozero import OutputDevice, AngularServo, Buzzer
from rpi_ws281x import PixelStrip, Color
from time import sleep


def fade_lights(strip, target_brightness, color=(255, 180, 100), steps=20):
    """灯带渐变到目标亮度，色调暖白。"""
    strip.setBrightness(target_brightness)
    for i in range(strip.numPixels()):
        strip.setPixelColor(i, Color(*color))
    strip.show()


def main():
    # 1. 初始化
    strip = PixelStrip(60, 18, 800000, 10, False, 80, 0)
    strip.begin()
    relay_door = OutputDevice(5, active_high=False, initial_value=False)
    fan = OutputDevice(20, active_high=False, initial_value=False)
    curtain = AngularServo(13, min_angle=0, max_angle=180,
                            min_pulse_width=0.0005, max_pulse_width=0.0025)
    buz = Buzzer(21)

    # 2. 睡眠模式动作链
    print("睡眠模式启动...")
    print("→ 灯渐暗到夜灯亮度（15%）")
    fade_lights(strip, 38, (255, 180, 100))   # 38/255 ≈ 15%
    sleep(0.5)
    print("→ 空调启动（风扇）")
    fan.on()
    sleep(0.3)
    print("→ 拉窗帘（舵机 → 180°）")
    curtain.angle = 180
    sleep(1)
    print("→ 锁门（继电器吸合）")
    relay_door.on()
    sleep(0.3)
    print("→ 确认蜂鸣")
    buz.on(); sleep(0.2); buz.off()

    print("\n保持 10 秒...")
    sleep(10)

    # 3. 恢复
    print("\n恢复初始状态...")
    fade_lights(strip, 0, (0, 0, 0))
    fan.off()
    curtain.angle = 0
    sleep(1)
    relay_door.off()
    curtain.detach()
    print("OK")


if __name__ == "__main__":
    main()
