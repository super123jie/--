# 智能家居前端 Demo · 单文件 React 组件

## 一、文件清单

| 文件 | 用途 |
| --- | --- |
| [SmartHomeDemo.jsx](SmartHomeDemo.jsx) | 完整组件（parseCommand / decideSafety / executeAction + UI） |
| [index.html](index.html) | 浏览器引导文件，CDN 加载 React/Tailwind/framer-motion/lucide-react |

## 二、运行方式（推荐，不需要装 Node）

由于浏览器禁止 `file://` 直接 import 模块，需要起一个本地 HTTP 服务器。**任选一种**：

### 方式 A：Python（最快，你电脑已有）
```bash
cd E:\1\中兴\前端Demo
python -m http.server 8000
```
然后浏览器打开 [http://localhost:8000](http://localhost:8000)

### 方式 B：VSCode Live Server 扩展
在 VSCode 中右键 `index.html` → `Open with Live Server`

### 方式 C：Node 一键
```bash
npx serve E:\1\中兴\前端Demo
```

> ❌ 不要直接双击 `index.html`，浏览器 CORS 策略会阻止 ES Module。

## 三、可识别的指令测试集（必看）

```
打开主卧空调               → 主卧空调 ON · 26.0°C
关闭主卧空调               → 主卧空调 OFF
我在主卧室，调低空调温度5°C → 主卧空调 21.0°C
打开厨房的灯               → 厨房灯 80%
把客厅灯调到80%            → 客厅灯 80%
开启扫地机器人             → robotCleaner.start
停止扫地机器人             → robotCleaner.stop
解锁入户门                 → 中风险，需点「确认」
打开燃气阀                 → 高风险，需点「确认」
```

## 四、视觉响应

- **灯**：房间中心圆点亮起 → 整个房间发出暖黄光晕 + 边框变金，亮度根据 brightness 渐变
- **空调**：墙上蓝色横条亮起 + 三道蓝色气流向下飘动
- **窗帘**：右下角 5 根竖条切换"短/长"
- **电视**：右下角矩形屏幕亮蓝色 + 内部脉冲动画
- **音响**：右侧脉冲扩散光圈（紫色）
- **空气净化器**：底部左侧扩散绿色圆环
- **加湿器**：底部右侧水滴上升消失动画
- **入户门**：底部矩形，蓝（locked）/ 橙（unlocked）
- **燃气阀**：右下角圆形，绿（closed）/ 红（open）+ 红色心跳动画
- **扫地机**：地板中央圆形，激活时旋转 + 来回移动

## 五、嵌入到现有 React 项目

如果你后续想把这个组件接到 create-react-app 或 Vite：

```bash
npm install react react-dom framer-motion lucide-react
npm install -D tailwindcss
```

然后：
```jsx
import SmartHomeDemo from "./SmartHomeDemo.jsx";

function App() {
  return <SmartHomeDemo />;
}
```

JSX 文件自身导出了三个工具函数供测试：
```js
import { parseCommand, decideSafety, executeAction } from "./SmartHomeDemo.jsx";

console.log(parseCommand("把客厅灯调到80%"));
// → [{ room:"客厅", device:"light", action:"set", value:80, raw:"..." }]
```

## 六、与 Python 后端联调（可选）

当前组件用 useState 全前端模拟 Agent。如要接你的 `algorithm/main.py:run()`：

1. 在 Pi/Windows 上跑 Streamlit 那套 Agent
2. 暴露一个 FastAPI/Flask 接口包装 `run()`
3. 把 `handleSubmit` 改成 `fetch("/api/agent", {method:"POST", body:input})`
4. 用返回的 `home_state_after` 替换前端 state

## 七、自定义房间或设备

修改 [SmartHomeDemo.jsx](SmartHomeDemo.jsx)：
- 房间布局：`House3D` 函数里调整 `RoomZone` 的 `style`（left/top/width/height）
- 设备图标：`DEVICE_ICON` 字典加映射，确保 lucide-react 已 import
- 命令识别：`DEVICE_MAP` 字典加中文同义词
