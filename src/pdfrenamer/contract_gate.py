# -*- coding: utf-8 -*-
"""合同文档类型闸门（V1.1.1，纯规则）。

真实样本里出现过「财政支出绩效评价报告 / 工作方案」被误当成合同：
它们封面写着「项目名称：…」，而旧预设把「项目名称」列为合同名称同义词，
于是生成了「项目名_未知_未知_未知.pdf」这类错误文件名。

本模块用确定性的关键词/正则做文档级判定：合同要素加分、报告专属要素减分，
命中白名单强信号可直接放行。全部是字符串匹配，不含任何模型、推理或网络调用。

判定只看「首页未重排原文」与「正文文本层」，不采用 PDF 元数据 title——
实测样本 043b… 的 title 是「绩效评价项目评价工作方案」，与首页真实标题不一致。
"""
from __future__ import annotations

import re

# 首页独立大标题（无冒号、长度受控）里含合同类名词
CONTRACT_TITLE = re.compile(
    r"[\s\u4e00-\u9fffA-Za-z0-9（）()·\-—_《》]{0,16}"
    r"(?:合同|协议书?|契约|合约)"
    r"[\s\u4e00-\u9fffA-Za-z0-9（）()·\-—_《》]{0,16}")

# 甲乙双方标签：必须带冒号，避免正文「后，甲方支付」「材料费，乙方免」这类碎片误触
PARTY_LABEL = re.compile(
    r"(甲\s*方|乙\s*方|供\s*方|需\s*方|委托方|受托方|发包方|承包方|出租方|承租方)"
    r"[^\r\n]{0,8}[：:]")
SIGN_MARK = re.compile(
    r"签订日期|签署日期|签约日期|合同编号|签订地点|盖章|签章|公章|签订|签署|签约")
# 「合同金额」强制冒号，避免绩效评价报告正文里的表格表头误触
CONTRACT_LABEL = re.compile(r"合同名称|合同编号|合同金额[：:]|合同价款|签订日期|签订地点")
# 白名单硬信号：出现即认为是合同（仍要求没有报告专属负信号）
STRONG_POSITIVE = re.compile(r"合同编号[：:]|甲乙双方?盖章|签订地点[：:]")

# 负信号只收「明确专属」的词，绝不收「项目/单位/金额/日期」等合同也会有的泛词
NEGATIVE_TITLE = re.compile(
    r"绩效评价|财政支出|评价报告|评价工作方案|工作方案|绩效跟踪|评价结论|绩效目标|自评报告")
NEGATIVE_LABEL = re.compile(
    r"评价机构|委托单位|委托部门|项目单位|主管(?:预算)?单位|预算单位|"
    r"成文年月|评价时段|评价类型|评价方式|评价方法|评价指标")
PROJECT_NAME_ONLY = re.compile(r"项目名称[：:]")


def contract_score(head_text: str, text: str,
                   metadata: dict | None = None) -> tuple[int, dict]:
    """返回 (得分, 明细)。得分 >= threshold 视为合同文档。

    metadata 仅为兼容调用方签名保留，不参与判定（实测元数据 title 不可靠）。
    """
    head = head_text or ""
    first = "\n".join(head.splitlines()[:25])          # 首页信息区
    scope = "\n".join((text or "").splitlines()[:200])  # 正文前若干行
    score = 0
    reasons: list[str] = []

    # --- 正向 ---
    for ln in first.splitlines()[:15]:
        c = ln.strip()
        if c and not re.search(r"[:：]", c) and CONTRACT_TITLE.fullmatch(c):
            score += 3
            reasons.append("首页合同大标题")
            break

    parties = {re.sub(r"\s", "", p) for p in PARTY_LABEL.findall(scope)}
    if len(parties) >= 2:
        score += 2
        reasons.append("甲乙双方标签对")
    elif parties:
        score += 1
        reasons.append("单方标签")

    marks = SIGN_MARK.findall(scope)
    if marks:
        score += 1 + (1 if len(marks) >= 3 else 0)
        reasons.append(f"签订/盖章标记x{len(marks)}")
    if CONTRACT_LABEL.search(scope):
        score += 1
        reasons.append("合同专有标签")

    # --- 负向 ---
    neg = 0
    if NEGATIVE_TITLE.search(first):
        neg += 3
        reasons.append("绩效评价类标题")
    if NEGATIVE_LABEL.search(first):
        neg += 2
        reasons.append("评价报告专属标签")
    if PROJECT_NAME_ONLY.search(first) and not re.search(r"合同名称[：:]", first):
        neg += 2
        reasons.append("仅项目名称标签")
    elif NEGATIVE_TITLE.search(scope):
        neg += 1
        reasons.append("正文含评价报告字样")

    score -= neg
    return score, {
        "score": score,
        "hard": bool(STRONG_POSITIVE.search(scope)),
        "neg": neg,
        "parties": sorted(parties),
        "reasons": reasons,
    }


def is_contract_document(head_text: str, text: str,
                         metadata: dict | None = None,
                         threshold: int = 2) -> tuple[bool, dict]:
    """判定是否为合同类文档。阈值与开关由调用方（配置）控制，便于复核与关闭。"""
    score, info = contract_score(head_text, text, metadata)
    if info["hard"] and info["neg"] == 0:
        info["verdict"] = "合同"
        info["reason"] = "白名单硬信号放行"
        return True, info
    ok = score >= int(threshold)
    info["verdict"] = "合同" if ok else "非合同文档"
    info["reason"] = "、".join(info["reasons"]) or "合同要素不足"
    return ok, info
