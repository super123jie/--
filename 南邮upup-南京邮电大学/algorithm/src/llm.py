"""端侧轻量 LLM 增强：基于 BAAI/bge-small-zh-v1.5 嵌入模型的语义意图匹配。

设计原则：
1. 真·端侧：模型完全本地（algorithm/models/embedder/），运行时零联网。
2. 资源极轻：模型 ~92 MB，单条推理 ~10-30ms（CPU），内存增量 < 200 MB。
3. 余弦相似度 + 类型加权：每个意图维护一组锚点句子，用户输入的嵌入与每组锚点求最大余弦相似度，最高者为预测意图。
4. 与 L1/L2 协同：仅当 L1 规则与 L2 TF-IDF 都低置信时才触发，避免重复计算。
"""
from __future__ import annotations
import os
import threading
from pathlib import Path
from typing import Optional

import numpy as np

from .schema import Intent, IntentName

_MODEL_DIR = Path(__file__).resolve().parent.parent / "models" / "embedder"

# 每个意图给一组锚点；尽量覆盖各种说法、口语化表达、同义表述
_INTENT_ANCHORS: dict[str, list[str]] = {
    IntentName.MODE_SLEEP.value: [
        "我准备睡觉了", "要去休息了", "要睡觉了", "睡觉模式", "晚安",
        "我累了想躺下", "整个家进入睡眠状态", "夜晚就寝模式",
        "我困了帮我关灯", "我要上床了", "进入睡眠模式空调调到26度",
        "把家里设置成晚上睡觉的状态", "睡觉前帮我检查门窗",
        "启动夜间模式不要太亮", "现在休息关闭电视", "准备休息把窗帘拉上",
    ],
    IntentName.MODE_LEAVE.value: [
        "我要出门了", "马上离家", "外出几小时", "我走了", "离家模式",
        "全部关掉我要走", "出去办事", "我去上课了", "上班去了",
        "家里没人了开启安防", "外出模式", "离家前帮我检查燃气",
        "我出门十分钟后就开启安防", "上班时间家里设备该关的都关掉",
    ],
    IntentName.MODE_HOME.value: [
        "我刚到家", "我进门了", "回家了", "刚回家", "我回来了",
        "快到家了提前打开客厅灯", "马上到家把空调打开",
        "到家模式启动", "回家场景", "检测到我到家",
        "进门了把窗帘打开", "设置回家模式",
    ],
    IntentName.MODE_ENERGY.value: [
        "节能模式", "省点电", "降低能耗", "节电",
        "电费有点高减少耗电", "把不用的设备关掉省点电",
        "开启低功耗家庭模式", "帮我优化一下家里的用电",
        "进入省电模式", "关闭待机设备", "减少客厅设备能耗",
        "做一次家庭能耗优化",
    ],
    IntentName.MODE_PARTY.value: [
        "聚会模式", "来客人了", "派对开始", "招待朋友",
    ],
    IntentName.MODE_MOVIE.value: [
        "我要看电影了", "开启观影模式", "影院模式", "进入观影场景",
        "看投影把窗帘拉上", "追剧氛围灯", "把客厅调成看电影的环境",
        "电影开始了调音量", "看电视把灯调暗",
    ],
    IntentName.MODE_STUDY.value: [
        "孩子要写作业了", "开启学习模式", "学习陪伴模式", "安静学习模式",
        "孩子上网课了", "儿童学习陪伴", "辅导孩子学习", "课后学习模式",
        "孩子写作业不要开电视",
    ],
    IntentName.DEVICE_LIGHT.value: [
        "把灯打开", "关灯", "光线太暗", "亮度调一下", "灯太亮",
        "客厅灯开起来", "开个台灯", "客厅太黑了", "屋里看不见",
    ],
    IntentName.DEVICE_AC.value: [
        "空调温度调一下", "有点冷", "有点热", "调节温度", "降温",
        "升温", "把空调关了", "空调开 26 度",
        "屋里太闷", "客厅好闷", "空气不流通需要通风", "屋子里憋气",
    ],
    IntentName.DEVICE_CURTAIN.value: [
        "拉窗帘", "拉开窗帘", "拉上帘子", "把窗帘合上", "开窗帘",
    ],
    IntentName.DEVICE_TV.value: [
        "打开电视", "关掉电视", "看电视",
    ],
    IntentName.DEVICE_SPEAKER.value: [
        "放点音乐", "太吵了", "停止播放", "听首歌", "放轻音乐",
    ],
    IntentName.DEVICE_LOCK.value: [
        "解锁入户门", "把门锁了", "开门", "锁门",
    ],
    IntentName.DEVICE_GAS.value: [
        "关闭燃气", "燃气阀关掉", "把煤气关了",
    ],
    IntentName.DEVICE_ROBOT.value: [
        "扫地机干活", "扫地机器人启动", "停止扫地机",
    ],
    IntentName.DEVICE_AIR_PURIFIER.value: [
        "打开空气净化器", "开启净化器", "PM2.5 有点高", "空气质量不好",
    ],
    IntentName.DEVICE_HUMIDIFIER.value: [
        "打开加湿器", "屋里太干了", "湿度太低", "晚上有点干",
        "卧室湿度高了帮我处理",
    ],
    IntentName.DEVICE_FRESH_AIR.value: [
        "打开新风", "新风系统启动", "换换气", "空气不流通",
    ],
    IntentName.DEVICE_WATER_HEATER.value: [
        "打开热水器", "烧水洗澡", "把热水器关了",
    ],
    IntentName.CARE_MEDICINE.value: [
        "提醒吃药", "该吃药了", "服药提醒",
    ],
    IntentName.CARE_STUDY.value: [
        "看看孩子学习", "检查作业", "孩子写作业了吗",
    ],
    IntentName.CARE_FALL.value: [
        "有人摔倒了", "奶奶跌倒", "紧急情况摔了",
    ],
    IntentName.CARE_NIGHT.value: [
        "夜里陪伴老人", "起夜照顾", "起夜时自动开小夜灯",
    ],
    IntentName.CARE_WATER.value: [
        "提醒奶奶喝水", "爷爷今天有没有喝水", "按时喝水提醒",
    ],
    IntentName.CARE_EYE_BREAK.value: [
        "半小时后提醒孩子休息眼睛", "护眼提醒", "让眼睛休息一下",
    ],
    IntentName.CARE_GENERAL_ELDER.value: [
        "开启老人关怀模式", "关注老人房间温度", "老人房间太冷提醒我",
        "提醒老人睡前关好门窗", "晚上提醒老人不要把空调开太低",
    ],
    IntentName.SAFETY_GAS_LEAK.value: [
        "厨房闻到煤气味", "燃气好像泄漏了", "有股很重的煤气味", "怀疑燃气泄漏",
    ],
    IntentName.SAFETY_ELDER_NO_RESP.value: [
        "老人叫不应", "爷爷半天没动静", "奶奶没回应",
    ],
    IntentName.SAFETY_CHILD_ALONE.value: [
        "孩子一个人在家", "小朋友独自在家",
    ],
    IntentName.SAFETY_DOOR_ANOMALY.value: [
        "入户门没关", "窗户开着没人关",
    ],
    IntentName.SAFETY_INTRUSION.value: [
        "夜里有陌生人开门", "有人闯进来了",
    ],
    IntentName.QUERY_STATUS.value: [
        "家里现在状态", "空调还开着吗", "现在多少度",
    ],
    IntentName.QUERY_PREFERENCE.value: [
        "我喜欢什么温度", "我习惯多少亮度",
    ],
    IntentName.QUERY_SECURITY_CHECK.value: [
        "帮我检查家里是否安全", "看看门锁有没有锁好",
        "检查厨房燃气是否正常", "确认窗户都关上了吗",
        "开启家庭安防巡检", "现在家里有没有异常",
        "检查摄像头和门锁状态", "门窗有没有没关的",
        "启动安全检查", "确认阳台窗户有没有关好",
    ],
}


class _SemanticMatcher:
    """惰性加载嵌入模型并预计算所有锚点嵌入。"""
    _instance: Optional["_SemanticMatcher"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._model = None
        self._anchor_embs: Optional[np.ndarray] = None
        self._anchor_intents: list[str] = []
        self._enabled = _MODEL_DIR.exists() and (_MODEL_DIR / "config.json").exists()

    @classmethod
    def instance(cls) -> "_SemanticMatcher":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def is_available(self) -> bool:
        return self._enabled

    def _ensure_loaded(self):
        if self._model is not None:
            return
        # 离线加载：禁用 HF Hub 联网
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        from sentence_transformers import SentenceTransformer  # type: ignore
        self._model = SentenceTransformer(str(_MODEL_DIR), local_files_only=True)
        anchors = []
        labels = []
        for intent_name, examples in _INTENT_ANCHORS.items():
            for ex in examples:
                anchors.append(ex)
                labels.append(intent_name)
        embs = self._model.encode(anchors, normalize_embeddings=True,
                                   convert_to_numpy=True, show_progress_bar=False)
        self._anchor_embs = embs.astype(np.float32)
        self._anchor_intents = labels

    def predict(self, text: str) -> Intent:
        if not self._enabled:
            return Intent(name=IntentName.UNKNOWN.value, confidence=0.0, raw=text)
        try:
            self._ensure_loaded()
            q = self._model.encode([text], normalize_embeddings=True,
                                    convert_to_numpy=True, show_progress_bar=False)
            sims = (q.astype(np.float32) @ self._anchor_embs.T)[0]  # cosine
            best = int(sims.argmax())
            score = float(sims[best])
            intent_name = self._anchor_intents[best]
            # 把 [0, 1] 余弦相似度映射成 [0, 1] 置信度（弱阈值）
            return Intent(name=intent_name, confidence=score, raw=text)
        except Exception as exc:
            return Intent(name=IntentName.UNKNOWN.value, confidence=0.0,
                           raw=f"{text} | llm_err={exc}")


def predict_semantic(text: str) -> Intent:
    return _SemanticMatcher.instance().predict(text)


def is_available() -> bool:
    return _SemanticMatcher.instance().is_available()


def warmup():
    """预热：在 Demo 启动时主动加载模型，避免第一条用户输入卡顿。"""
    _SemanticMatcher.instance()._ensure_loaded()
