"""Portable Markdown, calendar and Chinese PDF exports for structured plans."""

import hashlib
import io
import re
from datetime import date, datetime, time, timezone
from html import escape

BUDGET_LABELS = {
    "tickets": "景点门票",
    "meals": "餐饮",
    "lodging": "住宿",
    "local_transport": "市内交通",
    "contingency": "机动费用",
}


def _plan(value):
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


def _money(value):
    return f"¥{float(value):,.0f}"


def _daily_events(day, include_alternatives=False):
    events = list(day["activities"])
    for meal in day.get("meals", []):
        restaurant = meal["restaurant"]
        label = "午餐" if meal["slot"] == "lunch" else "晚餐"
        details = [restaurant.get("recommendation_reason", "")]
        if restaurant.get("address"):
            details.append("地址：" + restaurant["address"])
        if restaurant.get("cuisines"):
            details.append("菜系：" + "、".join(restaurant["cuisines"]))
        if restaurant.get("rating") is not None:
            details.append(f"评分：{restaurant['rating']}")
        if restaurant.get("opening_hours"):
            details.append("营业时间：" + restaurant["opening_hours"])
        details.append(
            f"人均 {_money(restaurant['cost_per_person'])}（{restaurant.get('price_source', '餐费估算')}）"
        )
        details.extend(meal.get("notes", []))
        if include_alternatives and meal.get("alternatives"):
            details.append(
                "备选："
                + "；".join(
                    f"{option['name']} / 人均 {_money(option['cost_per_person'])}"
                    for option in meal["alternatives"]
                )
            )
        events.append(
            {
                "id": "meal:" + meal["slot"],
                "kind": "meal",
                "name": f"{label} · {restaurant['name']}",
                "start_time": meal["start_time"],
                "end_time": meal["end_time"],
                "duration_minutes": meal.get("duration_minutes", 60),
                "cost_per_person": restaurant["cost_per_person"],
                "lat": restaurant["lat"],
                "lon": restaurant["lon"],
                "description": "\n".join(filter(None, details)),
                "source": restaurant.get("source", "餐饮地点资料"),
                "source_url": restaurant.get("source_url", ""),
                "location": restaurant["name"] + " " + restaurant.get("address", ""),
            }
        )
    return sorted(events, key=lambda event: event["start_time"])


def _event_type(activity):
    if activity.get("kind") == "meal":
        return "餐饮安排"
    return "室内" if activity["indoor"] else "室外"


def export_markdown(plan):
    plan = _plan(plan)
    preferences, budget = plan["preferences"], plan["budget"]
    lines = [
        f"# {plan['title']}",
        "",
        plan.get("summary", ""),
        "",
        f"- 目的地：{preferences['destination']}",
        f"- 出发日期：{preferences['start_date']}",
        f"- 行程：{preferences['days']} 天 · {preferences['travelers']} 人",
        f"- 预算：{_money(budget['limit'])} · 预计总计：{_money(budget['total'])} · 人均：{_money(budget['per_person'])}",
        "",
    ]
    lodging = plan.get("lodging")
    if lodging:
        lines.extend(
            [
                "## 住宿安排",
                "",
                f"**{lodging['name']}**",
                "",
                f"- 每间每晚：{_money(lodging['nightly_rate'])} · {lodging['rooms']} 间 · {lodging['nights']} 晚",
                f"- 住宿合计：{_money(lodging['nightly_rate'] * lodging['rooms'] * lodging['nights'])}",
                f"- 坐标：{lodging['lat']}, {lodging['lon']}",
                f"- 来源：{lodging['source']}",
            ]
        )
        if lodging.get("source_url"):
            lines.append(f"- 来源链接：{lodging['source_url']}")
        lines.append("")
    for day in plan["days"]:
        lines.extend([f"## 第 {day['day']} 天 · {day['date']} · {day['title']}", ""])
        for activity in _daily_events(day, include_alternatives=True):
            lines.extend(
                [
                    f"### {activity['start_time']}–{activity['end_time']} {activity['name']}",
                    "",
                    activity["description"],
                    "",
                    f"- 停留：{activity['duration_minutes']} 分钟 · 单人费用：{_money(activity['cost_per_person'])} · {_event_type(activity)}",
                    f"- 坐标：{activity['lat']}, {activity['lon']}",
                    f"- 地点来源：{activity.get('source', '目的地资料')}",
                ]
            )
            if activity.get("source_url"):
                lines.append(f"- 来源链接：{activity['source_url']}")
            lines.append("")
        if day.get("meals"):
            lines.append(
                f"早餐预算：{_money(day.get('breakfast_cost_per_person', 15))} / 人；餐饮预算仅计入已选餐厅。\n"
            )
        route = day.get("route", {})
        lines.extend(
            [
                f"**当日交通：** {route.get('distance_km', 0):.1f} 公里，约 {route.get('duration_minutes', 0)} 分钟（{route.get('source', '')}）",
                f"**当日预算：** {_money(day.get('estimated_cost', 0))}",
                "",
            ]
        )
        lines.extend(f"- {note}" for note in day.get("notes", []))
        lines.append("")
    lines.extend(["## 预算明细", "", "| 项目 | 预计金额 |", "| --- | ---: |"])
    lines.extend(
        f"| {BUDGET_LABELS.get(name, name)} | {_money(value)} |"
        for name, value in budget["categories"].items()
    )
    lines.extend(
        [
            f"| 总计 | {_money(budget['total'])} |",
            "",
            f"预算余额：{_money(budget['remaining'])}",
            "",
        ]
    )
    lines.extend(
        f"- {item}"
        for item in budget.get("warnings", []) + budget.get("alternatives", [])
    )
    if plan.get("sources"):
        lines.extend(["", "## 参考资料", ""])
        for i, source in enumerate(plan["sources"], 1):
            lines.append(
                f"{i}. {source['title']}"
                + (f" — {source['url']}" if source.get("url") else "")
            )
    return "\n".join(lines).strip() + "\n"


def _ics_escape(value):
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def _fold(line):
    """RFC 5545 limits physical lines to 75 octets, not 75 code points."""
    result, current = [], ""
    for character in line:
        if len((current + character).encode("utf-8")) > 75:
            result.append(current)
            current = " " + character
        else:
            current += character
    result.append(current)
    return "\r\n".join(result)


def _calendar_datetime(day, clock):
    parsed_day = date.fromisoformat(str(day))
    parsed_time = time.fromisoformat(clock)
    return datetime.combine(parsed_day, parsed_time).strftime("%Y%m%dT%H%M%S")


def export_ics(plan, trip_id):
    plan = _plan(plan)
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Travel Assistant//Travel Plan//ZH",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:" + _ics_escape(plan["title"]),
        "X-WR-TIMEZONE:Asia/Shanghai",
        "BEGIN:VTIMEZONE",
        "TZID:Asia/Shanghai",
        "X-LIC-LOCATION:Asia/Shanghai",
        "BEGIN:STANDARD",
        "DTSTART:19920101T000000",
        "TZOFFSETFROM:+0800",
        "TZOFFSETTO:+0800",
        "TZNAME:CST",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]
    for day in plan["days"]:
        for activity in _daily_events(day):
            uid = hashlib.sha256(
                f"{trip_id}:{day['day']}:{activity['id']}".encode()
            ).hexdigest()[:32]
            description = (
                activity["description"]
                + f"\n停留 {activity['duration_minutes']} 分钟；单人费用 {_money(activity['cost_per_person'])}。\n"
                + "\n".join(day.get("notes", []))
            )
            start = _calendar_datetime(day["date"], activity["start_time"])
            end = _calendar_datetime(day["date"], activity["end_time"])
            if end <= start:
                raise ValueError("日历活动结束时间须晚于开始时间。")
            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:{uid}@travel-assistant",
                    f"DTSTAMP:{now}",
                    f"DTSTART;TZID=Asia/Shanghai:{start}",
                    f"DTEND;TZID=Asia/Shanghai:{end}",
                    "SUMMARY:" + _ics_escape(activity["name"]),
                    "DESCRIPTION:" + _ics_escape(description),
                    "LOCATION:"
                    + _ics_escape(activity.get("location", activity["name"])),
                    f"GEO:{activity['lat']};{activity['lon']}",
                    "STATUS:CONFIRMED",
                    "END:VEVENT",
                ]
            )
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def export_pdf(plan):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import (
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    plan = _plan(plan)
    font = "STSong-Light"
    if font not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(font))
    output = io.BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=44,
        rightMargin=44,
        topMargin=42,
        bottomMargin=44,
        title=plan["title"],
        author="Travel Assistant",
    )
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "TravelBody",
        parent=styles["BodyText"],
        fontName=font,
        fontSize=10,
        leading=16,
        wordWrap="CJK",
        spaceAfter=7,
        textColor=colors.HexColor("#29392f"),
    )
    title = ParagraphStyle(
        "TravelTitle", parent=body, fontSize=24, leading=32, spaceAfter=14
    )
    section = ParagraphStyle(
        "TravelSection",
        parent=body,
        fontSize=15,
        leading=22,
        spaceBefore=14,
        spaceAfter=9,
        keepWithNext=True,
        textColor=colors.HexColor("#37634c"),
    )
    heading = ParagraphStyle(
        "TravelHeading",
        parent=body,
        fontSize=11,
        leading=18,
        spaceBefore=6,
        keepWithNext=True,
    )
    small = ParagraphStyle(
        "TravelSmall",
        parent=body,
        fontSize=8.5,
        leading=13,
        textColor=colors.HexColor("#63756a"),
    )
    table_cell = ParagraphStyle("TravelCell", parent=body, spaceAfter=0, fontSize=10)

    def paragraph(value, style=body):
        # Export user/LLM content as text; never interpret it as ReportLab markup.
        clean = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value))
        return Paragraph(escape(clean).replace("\n", "<br/>"), style)

    preferences, budget = plan["preferences"], plan["budget"]
    story = [
        paragraph("TRAVEL ASSISTANT · 旅行计划", small),
        paragraph(plan["title"], title),
        paragraph(plan.get("summary", "")),
        paragraph(
            f"{preferences['destination']}  |  {preferences['start_date']} 出发  |  {preferences['days']} 天 / {preferences['travelers']} 人",
            small,
        ),
        HRFlowable(width="100%", thickness=1, color=colors.HexColor("#bbcec1")),
        Spacer(1, 10),
    ]
    overview = [
        [
            paragraph("预计总费用", table_cell),
            paragraph("人均费用", table_cell),
            paragraph("预算余额", table_cell),
        ],
        [
            paragraph(_money(budget["total"]), heading),
            paragraph(_money(budget["per_person"]), heading),
            paragraph(_money(budget["remaining"]), heading),
        ],
    ]
    overview_table = Table(overview, colWidths=[document.width / 3] * 3)
    overview_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eff4ee")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(overview_table)
    lodging = plan.get("lodging")
    if lodging:
        story.append(paragraph("住宿安排", section))
        story.append(paragraph(lodging["name"], heading))
        story.append(
            paragraph(
                f"每间每晚 {_money(lodging['nightly_rate'])}  ·  {lodging['rooms']} 间 / {lodging['nights']} 晚  ·  合计 {_money(lodging['nightly_rate'] * lodging['rooms'] * lodging['nights'])}"
            )
        )
        story.append(
            paragraph(
                f"坐标：{lodging['lat']}, {lodging['lon']}  ·  {lodging['source']}",
                small,
            )
        )
        if lodging.get("source_url"):
            story.append(paragraph(lodging["source_url"], small))
    for day in plan["days"]:
        story.append(
            paragraph(f"第 {day['day']} 天 · {day['date']} · {day['title']}", section)
        )
        for activity in _daily_events(day, include_alternatives=True):
            story.append(
                paragraph(
                    f"{activity['start_time']}–{activity['end_time']}  {activity['name']}",
                    heading,
                )
            )
            story.append(paragraph(activity["description"]))
            story.append(
                paragraph(
                    f"停留 {activity['duration_minutes']} 分钟  ·  单人费用 {_money(activity['cost_per_person'])}  ·  {_event_type(activity)}  ·  {activity.get('source', '')}",
                    small,
                )
            )
        if day.get("meals"):
            story.append(
                paragraph(
                    f"早餐预算 {_money(day.get('breakfast_cost_per_person', 15))} / 人；餐饮预算仅计入已选餐厅。",
                    small,
                )
            )
        route = day.get("route", {})
        story.append(
            paragraph(
                f"当日交通约 {route.get('distance_km', 0):.1f} 公里 / {route.get('duration_minutes', 0)} 分钟；当日预算 {_money(day.get('estimated_cost', 0))}。",
                body,
            )
        )
        if route.get("source"):
            story.append(paragraph("路线来源：" + route["source"], small))
        for note in day.get("notes", []):
            story.append(paragraph("• " + note, small))
    story.append(paragraph("预算明细", section))
    rows = [[paragraph("项目", table_cell), paragraph("预计费用", table_cell)]]
    rows += [
        [
            paragraph(BUDGET_LABELS.get(name, name), table_cell),
            paragraph(_money(value), table_cell),
        ]
        for name, value in budget["categories"].items()
    ]
    rows += [
        [paragraph("总计", table_cell), paragraph(_money(budget["total"]), table_cell)]
    ]
    table = Table(
        rows,
        colWidths=[document.width * 0.68, document.width * 0.32],
        repeatRows=1,
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e3ede5")),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f5f7f3")],
                ),
                ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#bbcec1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    story.append(table)
    for item in budget.get("warnings", []) + budget.get("alternatives", []):
        story.append(paragraph("• " + item, small))
    if plan.get("sources"):
        story.append(paragraph("参考资料", section))
        for i, source in enumerate(plan["sources"], 1):
            story.append(paragraph(f"[{i}] {source['title']}", heading))
            if source.get("excerpt"):
                story.append(paragraph(source["excerpt"], small))
            if source.get("url"):
                story.append(paragraph(source["url"], small))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor("#63756a"))
        canvas.drawString(44, 25, "Travel Assistant")
        canvas.drawRightString(A4[0] - 44, 25, f"第 {doc.page} 页")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
