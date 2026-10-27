"""Text for CSV-mode results: performance audit (EN), client report (EN/AR), WhatsApp digest (EN/AR).

All numbers come from perf.analyse(); this module only words them. Arabic is MSA with platform terms
(CPA, CTR, ROAS) kept in English, matching report.py.
"""

from __future__ import annotations

from typing import Any

from commands.perf import MIN_CONV_TO_JUDGE, WEAK_CTR

T = {
    "en": {
        "roles": {"winner": "Scale", "ok": "Keep", "thin": "Too early", "loser": "Cut", "waste": "Stop", "unjudged": "-"},
        "comp": {"efficiency": "Efficiency", "conversion": "Conversion", "traffic": "Traffic quality", "concentration": "Spend spread"},
        "no_conv": "no conversions", "cpa": "CPA {v}",
        "today_track": "Check the conversion event fires and the export has the results column before touching any bid.",
        "today_waste": "Confirm tracking is live on {names}, then pause or cut the budget.",
        "today_loser": "Cut the budget of {names} by 20%.",
        "today_none": "Nothing urgent. Keep the setup and re-import next week.",
        "test_winner": "Raise {name} by up to 20% and read CPA after 7 days (now {cpa}).",
        "test_ctr": "Rewrite the hook on {name} (not the fonts) and read CTR after 7 days.",
        "test_conc": "Launch a second campaign with a different angle so one campaign does not carry the account.",
        "test_target": "Work out break-even (`economics breakeven`) and re-run with --target-cpa.",
        "test_thin": "Consolidate budget into fewer campaigns so each collects enough conversions.",
        "test_none": "No test suggested yet. Re-import after a week of data.",
        "stop_line": "{name}: {spend} spent, {cpa}",
        "stop_none": "Nothing to stop in this data.",
        "limits": ["Period is whatever the export covered; the file does not say.",
                   "Conversions are as the ad platform reports them. For cash-on-delivery, judge delivered revenue instead.",
                   "Roles and the score use fixed heuristics from this engine, not industry benchmarks."],
    },
    "ar": {
        "roles": {"winner": "وسّع", "ok": "استمر", "thin": "بيانات قليلة", "loser": "قلّل", "waste": "أوقف", "unjudged": "-"},
        "comp": {"efficiency": "الكفاءة", "conversion": "التحويل", "traffic": "جودة الزيارات", "concentration": "توزيع الإنفاق"},
        "no_conv": "بدون تحويلات", "cpa": "CPA {v}",
        "today_track": "تأكد أن حدث التحويل يعمل وأن الملف المصدَّر يحتوي عمود النتائج قبل أي تعديل على المزايدة.",
        "today_waste": "تأكد من تفعيل التتبع على {names} ثم أوقفها أو خفّض ميزانيتها.",
        "today_loser": "خفّض ميزانية {names} بنسبة 20%.",
        "today_none": "لا شيء عاجل. أبقِ الإعداد كما هو وأعد الاستيراد الأسبوع القادم.",
        "test_winner": "ارفع ميزانية {name} حتى 20% وراجع CPA بعد 7 أيام (الآن {cpa}).",
        "test_ctr": "أعد كتابة الجملة الافتتاحية في {name} (وليس الخطوط) وراجع CTR بعد 7 أيام.",
        "test_conc": "أطلق حملة ثانية برسالة مختلفة حتى لا يعتمد الحساب كله على حملة واحدة.",
        "test_target": "احسب نقطة التعادل (`economics breakeven`) ثم أعد التشغيل مع --target-cpa.",
        "test_thin": "ادمج الميزانية في حملات أقل حتى تجمع كل حملة تحويلات كافية.",
        "test_none": "لا يوجد اختبار مقترح بعد. أعد الاستيراد بعد أسبوع من البيانات.",
        "stop_line": "{name}: أُنفق {spend}، {cpa}",
        "stop_none": "لا شيء للإيقاف في هذه البيانات.",
        "limits": ["الفترة هي ما غطّاه الملف المصدَّر، ولا يذكرها الملف.",
                   "التحويلات كما تُبلّغ عنها المنصة. في الدفع عند الاستلام احكم على الإيراد المُسلَّم.",
                   "الأدوار والدرجة تعتمد على قواعد ثابتة في أداة التحليل، وليست معايير السوق."],
    },
}


def _money(value: float, currency: str | None) -> str:
    return f"{value:,.2f}" + (f" {currency}" if currency else "")


def _cpa(row: dict[str, Any], lang: str) -> str:
    t = T[lang]
    return t["cpa"].format(v=f"{row['cost'] / row['conversions']:,.2f}") if row["conversions"] else t["no_conv"]


def build_actions(perf: dict[str, Any], lang: str = "en") -> dict[str, list[str]]:
    t, roles, totals = T[lang], perf["by_role"], perf["totals"]
    names = lambda rows: ", ".join(r["name"] for r in rows[:3])  # noqa: E731
    today = ([t["today_track"]] if totals["cost"] > 0 and totals["conversions"] == 0 else
             [t["today_waste"].format(names=names(roles["waste"]))] if roles["waste"] else
             [t["today_loser"].format(names=names(roles["loser"]))] if roles["loser"] else [t["today_none"]])
    test = [t["test_winner"].format(name=r["name"], cpa=_cpa(r, lang)) for r in roles["winner"]]
    live = perf["campaigns"]
    if live and totals["conversions"] and totals["ctr"] < WEAK_CTR:
        test.append(t["test_ctr"].format(name=live[0]["name"]))
    if len(live) > 1 and live[0]["share"] > 0.70:
        test.append(t["test_conc"])
    if perf["target_cpa"] is None and totals["conversions"]:
        test.append(t["test_target"])
    if roles["thin"] and len(roles["thin"]) >= len(live) / 2:
        test.append(t["test_thin"])
    stop = [t["stop_line"].format(name=r["name"], spend=f"{r['cost']:,.2f}", cpa=_cpa(r, lang))
            for r in roles["waste"] + roles["loser"]]
    return {"today": today, "test": test or [t["test_none"]], "stop": stop or [t["stop_none"]]}


def _score_line(perf: dict[str, Any], lang: str) -> str:
    score = perf["score"]
    if score is None:
        return "لا توجد درجة: لا تحويلات للحكم عليها." if lang == "ar" else "No score: there are no conversions to judge."
    low = score["confidence"] == "low"
    if lang == "ar":
        return f"{score['total']:.0f}/100 (التقدير {score['grade']}){' (مبدئية: بيانات قليلة)' if low else ''}"
    return f"{score['total']:.0f}/100 (grade {score['grade']}){' (provisional)' if low else ''}"


def _campaign_table(perf: dict[str, Any], lang: str, currency: str | None) -> list[str]:
    t = T[lang]
    head = ("| Campaign | Spend | Share | Conversions | CPA | Call |" if lang == "en"
            else "| الحملة | الإنفاق | النسبة | التحويلات | CPA | القرار |")
    lines = [head, "|---|---|---|---|---|---|"]
    for r in perf["campaigns"]:
        cpa = f"{r['cost'] / r['conversions']:,.2f}" if r["conversions"] else "-"
        lines.append(f"| {r['name']} | {_money(r['cost'], currency)} | {r['share']:.0%} | {r['conversions']:,.0f} | "
                     f"{cpa} | {t['roles'][r['role']]} |")
    return lines


def format_audit(tenant: str, date: str, perf: dict[str, Any], currency: str | None) -> str:
    totals, score, t = perf["totals"], perf["score"], T["en"]
    top = perf["findings"][0]["finding"] if perf["findings"] else "No problem found in the layers this data can show."
    lines = [f"# {tenant} - Performance Audit (imported CSV) - {date}", "",
             f"**VERDICT:** {_score_line(perf, 'en')}. {top}", ""]
    if score:
        lines += ["## Score components", "| Component | Weight | Score | Evidence |", "|---|---|---|---|"]
        lines += [f"| {t['comp'][k]} | {v['weight']:.0%} | {v['score']:.0f}/100 | {v['evidence']} |"
                  for k, v in score["components"].items()]
        lines += ["", f"Confidence: **{score['confidence']}** ({totals['conversions']:,.0f} conversions in the data)."]
    lines += ["", "## Campaigns", *_campaign_table(perf, "en", currency), "", "## Top fixes (ranked)"]
    lines += [f"{i}. **{f['layer']}**: {f['finding']} Evidence: {f['evidence']}. *{f['confidence']}*. Test: {f['test']}."
              for i, f in enumerate(perf["findings"], 1)] or ["Nothing to fix in this data."]
    acts = build_actions(perf, "en")
    lines += ["", "## 30-day plan", "**Do today:**", *[f"- {a}" for a in acts["today"]],
              "**Test this week:**", *[f"- {a}" for a in acts["test"]],
              "**Stop / reduce:**", *[f"- {a}" for a in acts["stop"]],
              "", "## Honest limits", *[f"- {x}" for x in t["limits"]],
              f"- A campaign needs at least {MIN_CONV_TO_JUDGE} conversions before it is called a winner or a loser."]
    return "\n".join(lines)


def format_report(tenant: str, date: str, perf: dict[str, Any], currency: str | None, lang: str) -> str:
    totals, acts = perf["totals"], build_actions(perf, lang)
    cpa = f"{totals['cpa']:,.2f}" if totals["cpa"] else "-"
    if lang == "ar":
        lines = [f"# {tenant} - تقرير الأداء - {date}", "",
                 f"**الخلاصة:** الدرجة {_score_line(perf, 'ar')}. أُنفق {_money(totals['cost'], currency)} "
                 f"وحققنا {totals['conversions']:,.0f} تحويلات (CPA {cpa}).", "",
                 "## الأرقام", "| المؤشر | القيمة |", "|---|---|",
                 f"| الإنفاق | {_money(totals['cost'], currency)} |", f"| التحويلات | {totals['conversions']:,.0f} |",
                 f"| CPA | {cpa} |", f"| CTR | {totals['ctr']:.2f}% |", f"| مرات الظهور | {totals['impressions']:,.0f} |", "",
                 "## الحملات", *_campaign_table(perf, "ar", currency), "",
                 "## الإجراءات", "**افعل اليوم:**", *[f"- {a}" for a in acts["today"]],
                 "**اختبر هذا الأسبوع:**", *[f"- {a}" for a in acts["test"]],
                 "**أوقف / قلّل:**", *[f"- {a}" for a in acts["stop"]], "",
                 "## ملاحظات", *[f"- {x}" for x in T["ar"]["limits"]], "", "*مسودة: تحتاج مراجعة المشغّل قبل إرسالها للعميل.*"]
    else:
        lines = [f"# {tenant} - Performance Report - {date}", "",
                 f"**VERDICT:** Score {_score_line(perf, 'en')}. {_money(totals['cost'], currency)} spent for "
                 f"{totals['conversions']:,.0f} conversions (CPA {cpa}).", "",
                 "## The numbers", "| Metric | Value |", "|---|---|",
                 f"| Spend | {_money(totals['cost'], currency)} |", f"| Conversions | {totals['conversions']:,.0f} |",
                 f"| CPA | {cpa} |", f"| CTR | {totals['ctr']:.2f}% |", f"| Impressions | {totals['impressions']:,.0f} |", "",
                 "## Campaigns", *_campaign_table(perf, "en", currency), "",
                 "## Actions", "**Do today:**", *[f"- {a}" for a in acts["today"]],
                 "**Test this week:**", *[f"- {a}" for a in acts["test"]],
                 "**Stop / reduce:**", *[f"- {a}" for a in acts["stop"]], "",
                 "## Notes", *[f"- {x}" for x in T["en"]["limits"]], "", "*Draft: operator review needed before it goes to the client.*"]
    return "\n".join(lines)


def format_whatsapp(tenant: str, date: str, perf: dict[str, Any], currency: str | None, lang: str) -> str:
    totals, acts = perf["totals"], build_actions(perf, lang)
    cpa = f"{totals['cpa']:,.2f}" if totals["cpa"] else "-"
    if lang == "ar":
        return "\n".join([f"*ملخص الأداء - {tenant}* ({date})", "",
                          f"📌 *الخلاصة:* الدرجة {_score_line(perf, 'ar')}", "",
                          f"• الإنفاق: {_money(totals['cost'], currency)}", f"• التحويلات: {totals['conversions']:,.0f} (CPA {cpa})",
                          f"• CTR: {totals['ctr']:.2f}%", "", "*افعل اليوم:*", *[f"• {a}" for a in acts["today"]],
                          "*أوقف / قلّل:*", *[f"• {a}" for a in acts["stop"]]])
    return "\n".join([f"*{tenant} - Performance Digest* ({date})", "", f"📌 *VERDICT:* Score {_score_line(perf, 'en')}", "",
                      f"• Spend: {_money(totals['cost'], currency)}", f"• Conversions: {totals['conversions']:,.0f} (CPA {cpa})",
                      f"• CTR: {totals['ctr']:.2f}%", "", "*Do today:*", *[f"• {a}" for a in acts["today"]],
                      "*Stop / reduce:*", *[f"• {a}" for a in acts["stop"]]])
