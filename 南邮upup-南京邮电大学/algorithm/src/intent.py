"""意图识别：三层级联架构。

L1 规则正则引擎  → 高频指令零延迟命中（~0.05 ms）
L2 TF-IDF + LR   → 训练样本兜底（~0.5 ms）
L3 嵌入语义匹配  → BAAI/bge-small-zh-v1.5 端侧 LLM，处理开放式自然语言（~10-30 ms）

融合策略：
- L1 命中 ≥ 0.85：直接采用（保证响应速度与可解释性）
- L1 < 0.85 且 L2 ≥ 0.55：取 L2
- 全部低置信 → 触发 L3 嵌入匹配；若相似度 ≥ 0.55 采用，否则返回 UNKNOWN
- L3 模型不存在或加载失败时优雅降级，不影响主流程
"""
from __future__ import annotations
import re
from pathlib import Path
from typing import List, Tuple
import pickle

from .schema import Intent, IntentName

# ---------------------------------------------------------------------------
# L1 规则层：每个意图给一组关键词正则，命中即赋一个置信度。
# 顺序敏感：先匹配场景模式，再匹配设备控制，最后是关怀。
# ---------------------------------------------------------------------------
_RULES: List[Tuple[str, str, float]] = [
    # (intent_name, pattern, confidence)
    (IntentName.CARE_FALL.value, r"(摔倒|跌倒|摔了|倒下|起不来|fall_detected)", 0.99),
    # 安全事件预案
    (IntentName.SAFETY_GAS_LEAK.value, r"(煤气味|燃气泄漏|燃气味|gas_leak|有股煤气|闻到煤气|味道很重)", 0.99),
    (IntentName.SAFETY_ELDER_NO_RESP.value, r"(老人没反应|老人没动静|爷爷没动|奶奶没动|叫不应|没回应)", 0.97),
    (IntentName.SAFETY_CHILD_ALONE.value, r"(孩子(一个人|独自)|小孩(一个人|独自)|child_alone)", 0.95),
    (IntentName.SAFETY_DOOR_ANOMALY.value, r"(门(没关|开着|异常)|窗户(没关|开着)|door_open_anomaly)", 0.92),
    (IntentName.SAFETY_INTRUSION.value, r"(陌生人开门|有人闯入|夜间.*开门|intrusion)", 0.95),
    (IntentName.MODE_SLEEP.value, r"(我准备睡|我要睡觉|该睡了|进入睡眠|晚安|休息了|休息状态|休息模式|睡觉模式|睡眠模式|该歇了|要躺下|我困了|困得不行|我要上床|要上床了|夜间模式|晚上睡觉的状态|睡眠状态|准备休息|现在休息|要躺会|帮我.*睡觉前.*关灯|睡觉前.*关灯)", 0.97),
    (IntentName.MODE_LEAVE.value, r"(离家|出门|外出|要走了|不在家|出去了|要离开家|去上课|去上班|上班去|去开会|去办事|出去办事|外出模式|家里没人|家中无人|不在家中|我.*出门.*安防|离家前)", 0.98),
    (IntentName.MODE_HOME.value, r"(回家了|到家|进门|刚到家|我回来|快到家|马上到家|回家模式|到家模式|回家场景|进家门|检测到.*到家)", 0.95),
    (IntentName.MODE_ENERGY.value, r"(节能模式|省电|节电|降低能耗|低功耗|省点电|省一点电|减少.*耗电|减少.*能耗|优化.*用电|优化.*能耗|能耗优化|关闭待机|不要太耗电|节能状态|省电模式|耗电.*高)", 0.92),
    (IntentName.MODE_PARTY.value, r"(聚会|派对|来客人|招待)", 0.88),
    (IntentName.MODE_MOVIE.value, r"(看电影|追剧|观影|影院模式|看投影|电影开始|电影模式|看电视.*调|看电视.*暗|看电视.*20%|看电视.*氛围|追剧模式|看片|进入观影|观影场景|影视模式|关闭客厅大灯|客厅大灯|氛围灯)", 0.96),
    (IntentName.MODE_STUDY.value, r"(写作业|学习模式|学习陪伴|安静学习|上网课|网课|英语学习|学习提醒|课业|做作业|做功课|课后辅导|孩子.*看书|看书时|儿童房.*学习|儿童房.*灯光|儿童房.*亮|关闭游戏设备|提醒孩子.*睡)", 0.95),
    (IntentName.CARE_MEDICINE.value, r"(吃药|提醒.*药|该服药|按时.*药|血压.*提醒|测量.*提醒|血糖.*提醒)", 0.96),
    (IntentName.CARE_WATER.value, r"(喝水|按时.*水|没喝水|提醒.*水)", 0.95),
    (IntentName.CARE_EYE_BREAK.value, r"(休息眼睛|护眼|让眼睛|眼睛.*休息)", 0.95),
    (IntentName.CARE_STUDY.value, r"(检查.*学习|看看(孩子|小孩|小明)|看看.*作业|看看.*写作业|查作业|检查作业|写作业了吗|做完作业|完成作业|作业.*完成)", 0.96),
    (IntentName.CARE_NIGHT.value, r"(夜里.*陪伴|半夜.*陪伴|起夜.*灯|起夜.*老人|起夜时|起夜照顾|夜间陪伴)", 0.92),
    (IntentName.CARE_GENERAL_ELDER.value, r"(老人关怀|老人.*模式|关注.*老人|老人房间|老人.*温度|老人.*冷|老人.*热|老人睡前|提醒老人|不让老人|老人不要|提醒.*老人|奶奶.*睡前|爷爷.*睡前)", 0.97),
    (IntentName.DEVICE_GAS.value, r"(燃气|煤气|gas|阀门)", 0.94),
    (IntentName.DEVICE_LOCK.value, r"(门锁|入户门|开门|锁门|解锁)", 0.92),
    (IntentName.DEVICE_AC.value, r"(空调|制冷|制热|降温|升温|温度|AC)", 0.90),
    (IntentName.DEVICE_LIGHT.value, r"(灯|照明|亮度|光线)", 0.90),
    (IntentName.DEVICE_CURTAIN.value, r"(窗帘|遮光|帘子)", 0.92),
    (IntentName.DEVICE_TV.value, r"(电视|TV|影视)", 0.90),
    (IntentName.DEVICE_SPEAKER.value, r"(音响|音箱|音乐|播放.*歌|放首歌|音量)", 0.90),
    (IntentName.DEVICE_ROBOT.value, r"(扫地|扫地机|机器人.*清洁|拖地)", 0.90),
    (IntentName.DEVICE_AIR_PURIFIER.value, r"(空气净化器|净化器|净化空气|PM2\.5|空气质量)", 0.95),
    (IntentName.DEVICE_HUMIDIFIER.value, r"(加湿器|加湿|湿度.*高|湿度.*低|有点干|空气干|太干燥)", 0.93),
    (IntentName.DEVICE_FRESH_AIR.value, r"(新风|新风系统|换气|空气有点闷|空气不流通|通风.*下)", 0.90),
    (IntentName.DEVICE_WATER_HEATER.value, r"(热水器|烧水|热水)", 0.92),
    (IntentName.QUERY_SECURITY_CHECK.value, r"(检查家里.*安全|家.*是否安全|有没有锁好|安防巡检|安全检查|安全巡检|检查.*门窗|检查.*燃气|检查.*窗户|检查.*阳台|确认.*窗户|看看.*门窗|有没有异常|启动.*安防|开启.*安防|摄像头.*状态|阳台.*关好|门窗.*没关|窗户.*关好|燃气.*正常)", 0.97),
    (IntentName.QUERY_STATUS.value, r"(状态|开着吗|关了吗|温度.*多少|现在.*几度)", 0.85),
    (IntentName.QUERY_PREFERENCE.value, r"(我.*喜欢|偏好|习惯)", 0.80),
    (IntentName.DIALOG_CONFIRM.value, r"^(确认|是的|好的|可以|执行|没错|对)$", 0.99),
    # DIALOG_CANCEL 只匹配独立短语，避免吃掉"别锁门""不要开电视"这种带否定从句
    (IntentName.DIALOG_CANCEL.value, r"^(取消|算了|停止|不用了|别了|不用|算了吧)$", 0.99),
]


def rule_predict(text: str) -> Intent:
    """规则层预测，命中第一条置信度最高的规则。"""
    text_norm = text.strip()
    best: Intent = Intent(name=IntentName.UNKNOWN.value, confidence=0.0, raw=text_norm)
    for name, pat, conf in _RULES:
        if re.search(pat, text_norm):
            if conf > best.confidence:
                best = Intent(name=name, confidence=conf, raw=text_norm)
    return best


# ---------------------------------------------------------------------------
# L2 分类器层：训练数据嵌入在代码里以保证完全离线。
# 模型在首次调用时懒加载/训练并缓存到 models/ 目录。
# ---------------------------------------------------------------------------
_TRAINING_SAMPLES = [
    # 睡眠模式
    ("我准备睡觉了", IntentName.MODE_SLEEP.value),
    ("帮我把家里调到睡觉模式", IntentName.MODE_SLEEP.value),
    ("快躺下了，整理一下", IntentName.MODE_SLEEP.value),
    ("到点休息了", IntentName.MODE_SLEEP.value),
    # 离家
    ("我要出门了", IntentName.MODE_LEAVE.value),
    ("帮我设置离家", IntentName.MODE_LEAVE.value),
    ("我出去几个小时", IntentName.MODE_LEAVE.value),
    # 回家
    ("我刚到家", IntentName.MODE_HOME.value),
    ("我进门了", IntentName.MODE_HOME.value),
    # 节能
    ("家里太费电了，省一下", IntentName.MODE_ENERGY.value),
    ("启动节能", IntentName.MODE_ENERGY.value),
    # 设备
    ("把客厅的灯打开", IntentName.DEVICE_LIGHT.value),
    ("卧室灯关一下", IntentName.DEVICE_LIGHT.value),
    ("光线太暗了", IntentName.DEVICE_LIGHT.value),
    ("空调调到 26 度", IntentName.DEVICE_AC.value),
    ("有点冷，温度高一点", IntentName.DEVICE_AC.value),
    ("拉上窗帘", IntentName.DEVICE_CURTAIN.value),
    ("把帘子打开", IntentName.DEVICE_CURTAIN.value),
    ("放点轻音乐", IntentName.DEVICE_SPEAKER.value),
    ("打开电视", IntentName.DEVICE_TV.value),
    ("让扫地机器人干活", IntentName.DEVICE_ROBOT.value),
    ("把入户门锁了", IntentName.DEVICE_LOCK.value),
    ("关闭燃气总阀", IntentName.DEVICE_GAS.value),
    # 关怀
    ("奶奶该吃降压药了", IntentName.CARE_MEDICINE.value),
    ("提醒爷爷吃药", IntentName.CARE_MEDICINE.value),
    ("看看孩子有没有写作业", IntentName.CARE_STUDY.value),
    ("查一下小明的学习", IntentName.CARE_STUDY.value),
    ("奶奶摔倒了", IntentName.CARE_FALL.value),
    ("有人摔了快帮忙", IntentName.CARE_FALL.value),
    ("夜里陪伴一下老人", IntentName.CARE_NIGHT.value),
    # 查询
    ("家里现在多少度", IntentName.QUERY_STATUS.value),
    ("空调还开着吗", IntentName.QUERY_STATUS.value),
    ("我平时喜欢什么温度", IntentName.QUERY_PREFERENCE.value),
    # 对话控制
    ("确认", IntentName.DIALOG_CONFIRM.value),
    ("好的", IntentName.DIALOG_CONFIRM.value),
    ("没错", IntentName.DIALOG_CONFIRM.value),
    ("取消", IntentName.DIALOG_CANCEL.value),
    ("算了", IntentName.DIALOG_CANCEL.value),
    ("不用了", IntentName.DIALOG_CANCEL.value),
]


class _ClassifierProxy:
    """惰性加载/训练 sklearn 分类器，并把模型缓存到磁盘。"""
    def __init__(self, model_path: Path):
        self.model_path = model_path
        self._pipeline = None

    def _build_and_train(self):
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        import jieba

        def _tok(s: str):
            return list(jieba.cut(s))

        pipe = Pipeline([
            ("tfidf", TfidfVectorizer(tokenizer=_tok, token_pattern=None,
                                       ngram_range=(1, 2), min_df=1)),
            ("clf", LogisticRegression(max_iter=500, C=2.0)),
        ])
        X = [t for t, _ in _TRAINING_SAMPLES]
        y = [c for _, c in _TRAINING_SAMPLES]
        pipe.fit(X, y)
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.model_path, "wb") as f:
            pickle.dump(pipe, f)
        return pipe

    def _load(self):
        if self._pipeline is not None:
            return self._pipeline
        if self.model_path.exists():
            try:
                with open(self.model_path, "rb") as f:
                    self._pipeline = pickle.load(f)
                return self._pipeline
            except Exception:
                pass
        self._pipeline = self._build_and_train()
        return self._pipeline

    def predict(self, text: str) -> Intent:
        try:
            pipe = self._load()
            probs = pipe.predict_proba([text])[0]
            classes = pipe.classes_
            top_idx = int(probs.argmax())
            return Intent(name=str(classes[top_idx]), confidence=float(probs[top_idx]), raw=text)
        except Exception as exc:
            return Intent(name=IntentName.UNKNOWN.value, confidence=0.0, raw=f"{text} | err={exc}")


_DEFAULT_MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "intent_clf.pkl"
_classifier_proxy = _ClassifierProxy(_DEFAULT_MODEL_PATH)


def _zh_len(text: str) -> int:
    return sum(1 for c in text if not c.isspace())


def predict_intent(text: str, use_classifier: bool = True,
                    use_semantic: bool = True,
                    last_intent: Intent | None = None) -> Intent:
    """对外的统一意图预测入口（三层融合 + 上下文继承）。

    last_intent: 可选，多轮场景下上一轮的意图。短文本且本轮规则无强命中时优先继承。
    """
    rule_hit = rule_predict(text)
    if rule_hit.confidence >= 0.85:
        return rule_hit

    # 上下文继承：短文本（≤ 6 字）且规则置信 < 0.5 且有上轮意图 → 沿用
    # 这样可以稳健处理 "再低一点" / "卧室也是" 等省略式表达，避免 L3 误判
    # dialog.* 是控制流意图（确认/取消/澄清），不参与跨轮继承
    if (last_intent is not None
            and last_intent.name != IntentName.UNKNOWN.value
            and not last_intent.name.startswith("dialog.")):
        if _zh_len(text) <= 6 and rule_hit.confidence < 0.5:
            return Intent(name=last_intent.name,
                          confidence=max(0.7, last_intent.confidence * 0.85),
                          raw=text + " [继承上轮意图]")

    clf_hit = None
    if use_classifier:
        clf_hit = _classifier_proxy.predict(text)
        if clf_hit.confidence >= 0.55 and clf_hit.confidence > rule_hit.confidence:
            return clf_hit

    # L3：嵌入语义匹配（懒加载，模型不存在时优雅降级）
    if use_semantic:
        try:
            from . import llm
            if llm.is_available():
                sem_hit = llm.predict_semantic(text)
                # 阈值 0.66：经验值，对短文本/范畴外查询更保守，避免硬塞最近邻
                if sem_hit.confidence >= 0.66:
                    return sem_hit
        except Exception:
            pass

    if rule_hit.confidence > 0:
        return rule_hit
    if clf_hit is not None and clf_hit.confidence > 0:
        return clf_hit
    return Intent(name=IntentName.UNKNOWN.value, confidence=0.0, raw=text)
