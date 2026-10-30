#!/usr/bin/env python3
"""Generate vibration-monitor.fuxap (FUXA project) for the OPC UA servo-axis simulator.

Edit THRESHOLDS below to change warning / alarm levels, then re-run:
    python3 build_project.py
and import vibration-monitor.fuxap in FUXA (Editor -> menu -> Project -> Open/Import).
"""
import json, uuid, itertools, os

OPC_URL = os.environ.get("OPCUA_URL", "opc.tcp://localhost:4840/UA/VibrationSim")
NS = 2                       # namespace index of urn:vibmon:sim in the simulator
NAXES = 5
DEV_ID = "d_opcua_vibsim"
DEV_NAME = "VibSim"

# ---- Warning / alarm levels (your own): warn = "high", alarm = "highhigh" ---------------------------
THRESHOLDS = {
    #  signal        unit    warn   alarm
    "VelRMS":      ("mm/s",  4.5,   7.1),
    "AccRMS":      ("g",     0.50,  1.00),
    "TorqueRMS":   ("%",     70.0,  90.0),
    "Temperature": ("°C",    55.0,  70.0),
}
COL_OK, COL_WARN, COL_ALARM, COL_OFF = "#2ecc71", "#f5a623", "#e74c3c", "#7f8c8d"
AXIS_COLORS = ["#4da3ff", "#2ecc71", "#f5a623", "#e056fd", "#ff6b6b"]

_ids = itertools.count(1)
def uid(prefix): return f"{prefix}{uuid.uuid4()}"
def tid(name): return "t_" + name.replace(".", "_")
def vid(name): return tid(name)   # FUXA 1.3.x: a variable reference is the tag id itself

# ---------------------------------------------------------------- devices / tags
tags = {}
def add_tag(name, ttype="Double", daq=False, writable=True):
    t = {"id": tid(name), "name": name, "type": ttype, "address": f"ns={NS};s={name}"}
    if daq:
        t["daq"] = {"enabled": True, "interval": 1, "restored": False}
    tags[t["id"]] = t
    return name

for sig in ("Run", ):
    add_tag(f"Master.{sig}", "Boolean")
add_tag("Master.Speed")
add_tag("Master.Position")
HIST = ("VelRMS", "AccRMS", "Torque", "TorqueRMS", "Temperature", "Speed")
for n in range(1, NAXES + 1):
    for o in ("Position", "Speed", "Torque", "TorqueRMS", "VelRMS", "AccRMS", "VelPeak", "AccPeak", "Temperature"):
        add_tag(f"Axis{n}.{o}", daq=o in HIST)
    add_tag(f"Axis{n}.Enabled", "Boolean")
    for p in ("GearRatio", "CamAmplitude", "CamHarmonic", "PhaseOffset", "Inertia", "RatedTorque",
              "Friction", "Imbalance", "Looseness", "BearingWear", "Misalignment"):
        add_tag(f"Axis{n}.{p}")

device = {
    "id": DEV_ID, "name": DEV_NAME, "type": "OPCUA", "enabled": True,
    "polling": 500,
    "property": {"address": OPC_URL, "port": None, "slot": None, "rack": None,
                 "mode": {"securityMode": "None", "securityPolicy": "None"}},
    "tags": tags,
}

# ---------------------------------------------------------------- charts
def line(tag, name, color):
    return {"id": tid(tag), "name": name, "device": DEV_ID, "color": color, "label": name}

charts = []
def mk_chart(cid, name, sig):
    charts.append({"id": cid, "name": name,
                   "lines": [line(f"Axis{n}.{sig}", f"Axis {n}", AXIS_COLORS[n - 1]) for n in range(1, NAXES + 1)]})
mk_chart("c_vel", "Velocity RMS (mm/s)", "VelRMS")
mk_chart("c_acc", "Acceleration RMS (g)", "AccRMS")

# ---------------------------------------------------------------- alarms
def sub(enabled, lo, hi, text, group, bk, col):
    return {"enabled": enabled, "checkdelay": 1, "timedelay": 2, "min": lo, "max": hi,
            "text": text, "group": group, "bkcolor": bk, "color": col}
alarms = []
for n in range(1, NAXES + 1):
    for sig, (unit, warn, alm) in THRESHOLDS.items():
        label = {"VelRMS": "Velocity RMS", "AccRMS": "Acceleration RMS",
                 "TorqueRMS": "Torque RMS", "Temperature": "Temperature"}[sig]
        alarms.append({
            "name": f"Axis{n} {label}",
            "property": {"variableId": vid(f"Axis{n}.{sig}"), "variableSrc": DEV_ID, "variable": f"Axis{n}.{sig}"},
            "highhigh": sub(True, alm, 1e9, f"Axis {n} {label} ALARM > {alm} {unit}", f"Axis{n}", COL_ALARM, "#ffffff"),
            "high":     sub(True, warn, alm - 1e-9, f"Axis {n} {label} WARNING > {warn} {unit}", f"Axis{n}", COL_WARN, "#000000"),
            "low":      sub(False, 0, 0, "", "", "#ffffff", "#000000"),
            "info":     sub(False, 0, 0, "", "", "#ffffff", "#000000"),
            "actions":  {"enabled": False, "values": []},
        })

# ---------------------------------------------------------------- SVG helpers
items = {}
parts = []
P, I = parts, items          # target lists used by the widget helpers (switched per view)
BG, CARD, TXT, DIM, PANEL = "#141c26", "#202b38", "#e8eef5", "#8fa3b8", "#f4f6f9"

def esc(s): return s.replace("&", "&amp;").replace("<", "&lt;")

def rect(x, y, w, h, fill, rx=0, stroke="none"):
    return f'<rect id="{uid("svg_")}" x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="0"/>'

def text(x, y, s, size=14, fill=TXT, anchor="start", bold=False):
    w = ' font-weight="bold"' if bold else ""
    return (f'<text id="{uid("svg_")}" x="{x}" y="{y}" font-size="{size}" font-family="sans-serif" fill="{fill}" '
            f'text-anchor="{anchor}"{w} stroke-width="0" xml:space="preserve">{esc(s)}</text>')

def ev(prop, tag=None, ranges=None):
    p = {"events": [], "variable": tag or "", "variableId": vid(tag) if tag else "",
         "variableSrc": DEV_ID if tag else "", "alarmId": "", "alarmSrc": "", "alarm": "", "alarmColor": ""}
    if ranges is not None: p["ranges"] = ranges
    p.update(prop)
    return p

def value(x, y, tag, unit="", size=16, fill=TXT, anchor="end", fmt="##.##", name=None):
    wid = uid("VAL_")
    P.append(f'<g id="{wid}" type="svg-ext-value" fill="{fill}" font-size="{size}" font-family="sans-serif" '
                 f'stroke-width="0" text-anchor="{anchor}">'
                 f'<text id="{uid("VAL_")}" x="{x}" y="{y}" fill="{fill}" font-size="{size}" font-family="sans-serif" '
                 f'text-anchor="{anchor}" stroke-width="0" xml:space="preserve">{fmt}</text></g>')
    I[wid] = {"id": wid, "type": "svg-ext-value", "name": name or tag, "label": "Value",
                  "property": ev({}, tag, [{"type": "unit", "min": 0, "max": 0, "text": f" {unit}" if unit else "",
                                            "fractionDigits": len(fmt.split(".")[1]) if "." in fmt else 0}])}

def semaphore(cx, cy, tag, warn, alarm, r=9, name=None):
    wid = uid("GSE_")
    P.append(f'<g id="{wid}" type="svg-ext-gauge_semaphore" fill="#000000" stroke="#000000" font-size="14" font-family="sans-serif">'
                 f'<ellipse id="{uid("GSE_")}" cx="{cx}" cy="{cy}" rx="{r}" ry="{r}" fill="{COL_OFF}" stroke="#000000"/></g>')
    I[wid] = {"id": wid, "type": "svg-ext-gauge_semaphore", "name": name or tag, "label": "HtmlSemaphore",
                  "property": ev({}, tag, [
                      {"type": "range", "min": "-1000000", "max": str(warn - 1e-9), "color": COL_OK},
                      {"type": "range", "min": str(warn), "max": str(alarm - 1e-9), "color": COL_WARN},
                      {"type": "range", "min": str(alarm), "max": "1000000", "color": COL_ALARM}])}

def progress(x, y, w, h, tag, vmax, color, name=None):
    wid = uid("GXP_")
    P.append(f'<g id="{wid}" type="svg-ext-gauge_progress" font-family="sans-serif" font-size="14" stroke="null">'
                 f'<rect id="{uid("A-GXP_")}" x="{x}" y="{y}" width="{w}" height="{h}" fill="#3a485a" stroke="null"/>'
                 f'<rect id="{uid("B-GXP_")}" x="{x}" y="{y}" width="{w/2}" height="{h}" fill="{color}" stroke="null"/>'
                 f'<foreignObject id="{uid("H-GXP_")}" x="{x}" y="{y}" width="{w}" height="{h}"/></g>')
    I[wid] = {"id": wid, "type": "svg-ext-gauge_progress", "name": name or tag, "label": "HtmlProgress",
                  "property": ev({}, tag, [{"type": "minmax", "min": 0, "max": str(vmax), "style": [True, True], "color": color}])}

def chart(x, y, w, h, chart_id, ctype, name, ymax):
    wid = uid("HXC_")
    P.append(f'<g id="{wid}" type="svg-ext-html_chart" fill="#FFFFFF" font-size="14" font-family="sans-serif" stroke="#000000">'
                 f'<rect id="{uid("svg_")}" x="{x}" y="{y}" width="{w}" height="{h}" fill="{PANEL}" stroke-width="0" stroke="null"/>'
                 f'<foreignObject id="{uid("H-HXC_")}" x="{x}" y="{y}" width="{w}" height="{h}">'
                 f'<DIV id="{uid("D-HXC_")}" style="width: 100%; height: 100%; vector-effect: non-scaling-stroke;"></DIV></foreignObject></g>')
    I[wid] = {"id": wid, "type": "svg-ext-html_chart", "name": name, "label": "HtmlChart",
                  "property": {"id": chart_id, "type": ctype, "options": {
                      "title": "", "titleHeight": 0, "legendMode": "follow", "legendFontSize": 12, "axisLabelFontSize": 11,
                      "colorBackground": PANEL, "legendBackground": PANEL, "gridLineColor": "#d0d7de",
                      "axisLabelColor": "#33414f", "axisLineColor": "#33414f", "fontFamily": "Roboto-Regular",
                      "realtime": 5, "loadOldValues": True, "lastRange": "last8h", "decimalsPrecision": 2,
                      "scaleY1min": 0, "scaleY1max": ymax, "axisLabelX": "", "axisLabelY1": "",
                      "mouseWheelScroll": False, "mouseWheelZoom": False, "staticChart": False,
                      "dateFormat": "MM_DD_YYYY", "timeFormat": "hh_mm_ss_AA", "width": w, "height": h, "series": []}}}

def alarm_table(x, y, w, h):
    wid = uid("OXC_")
    P.append(f'<g id="{wid}" type="svg-ext-own_ctrl-table" fill="#FFFFFF" font-size="14" font-family="sans-serif" stroke="#000000">'
                 f'<rect id="{uid("svg_")}" x="{x}" y="{y}" width="{w}" height="{h}" fill="{PANEL}" stroke-width="0" stroke="null"/>'
                 f'<foreignObject id="{uid("H-OXC_")}" x="{x}" y="{y}" width="{w}" height="{h}">'
                 f'<DIV id="{uid("D-OXC_")}" style="width: 100%; height: 100%; vector-effect: non-scaling-stroke;"></DIV></foreignObject></g>')
    col = lambda i, label, width: {"id": i, "type": "label", "label": label, "width": width, "align": "left"}
    I[wid] = {"id": wid, "type": "svg-ext-own_ctrl-table", "name": "Active alarms", "label": "HtmlTable",
                  "property": {"type": "alarms", "options": {
                      "paginator": {"show": False}, "filter": {"show": False}, "daterange": {"show": False},
                      "realtime": False, "lastRange": "last8h", "gridColor": "#d0d7de",
                      "header": {"show": True, "height": 22, "fontSize": 12, "background": "#e6ebf1", "color": "#40505f"},
                      "row": {"height": 22, "fontSize": 11, "background": "#ffffff", "color": "#000000"},
                      "selection": {"background": "#3059AF", "color": "#FFFFFF", "fontBold": True},
                      "columns": [], "reportsColumns": [], "reportFilter": {"filterA": []}, "rows": [],
                      "alarmFilter": {"filterA": [], "filterB": [], "filterC": []},
                      "alarmsColumns": [col("ontime", "Time", 120), col("text", "Alarm", 330),
                                        col("type", "Level", 70), col("status", "State", 70), col("ack", "Ack", 50)]}}}

def nav_button(plist, idict, x, y, w, h, label, view_id, name):
    wid = uid("HXB_")
    plist.append(f'<g id="{wid}" type="svg-ext-html_button" fill="#FFFFFF" font-size="13" font-family="sans-serif" stroke="#000000">'
                 f'<rect id="{uid("svg_")}" x="{x}" y="{y}" width="{w}" height="{h}" fill="#3059AF" stroke-width="0" stroke="#ffffff"/>'
                 f'<foreignObject id="{uid("H-HXB_")}" x="{x}" y="{y}" width="{w}" height="{h}">'
                 f'<BUTTON id="{uid("B-HXB_")}" style="width: 100%; height: 100%; vector-effect: non-scaling-stroke; background-color: #3059AF; color: #ffffff;" '
                 f'class="md-btn  md-btn-raised">{label}</BUTTON></foreignObject></g>')
    idict[wid] = {"id": wid, "type": "svg-ext-html_button", "name": label,  # FUXA shows the widget name as caption
                   "label": "HtmlButton",
                  "property": ev({"events": [{"type": "click", "action": "onpage", "actparam": view_id, "actoptions": {}}]})}

def axis_key(x_right, y):
    """coloured axis key in a chart header row (the charts use hover tooltips instead of a legend)"""
    for n in range(NAXES, 0, -1):
        parts.append(text(x_right, y, f"■ Axis {n}", 12, AXIS_COLORS[n - 1], "end", True))
        x_right -= 78

# ---------------------------------------------------------------- Overview view (1600 x 900)
W, H = 1600, 960
parts.append(rect(0, 0, W, H, BG))

# header: machine status (left), ALARMS (top middle), thresholds (right)
parts.append(text(20, 34, "VIBRATION MONITOR", 24, TXT, bold=True))
parts.append(text(20, 58, "Machine 1 · servo axes following virtual master", 13, DIM))
parts.append(text(20, 92, "Master speed", 14, DIM));  value(260, 92, "Master.Speed", "rpm", 16, TXT, "end", "###0.0", name="Master speed")
parts.append(text(20, 116, "Master angle", 14, DIM));  value(260, 116, "Master.Position", "°", 16, TXT, "end", "##0.0", name="Master angle")
parts.append(text(20, 80 - 0, "", 1))

parts.append(text(800, 14, "ACTIVE ALARMS", 11, DIM, "middle", True))
alarm_table(480, 18, 640, 118)
nav_button(parts, items, 1150, 16, 150, 26, "Mechanism setup", "v_setup", "Go to setup")

th = THRESHOLDS
parts.append(text(1580, 40, "Warning / Alarm levels", 12, DIM, "end", True))
parts.append(text(1580, 62,  f"Velocity RMS   {th['VelRMS'][1]} / {th['VelRMS'][2]} mm/s", 12, TXT, "end"))
parts.append(text(1580, 80,  f"Accel RMS   {th['AccRMS'][1]} / {th['AccRMS'][2]} g", 12, TXT, "end"))
parts.append(text(1580, 98,  f"Torque RMS   {th['TorqueRMS'][1]} / {th['TorqueRMS'][2]} %", 12, TXT, "end"))
parts.append(text(1580, 116, f"Temperature   {th['Temperature'][1]} / {th['Temperature'][2]} °C", 12, TXT, "end"))

# centre: trends
parts.append(text(20, 156, "VELOCITY RMS (mm/s)  –  live", 12, DIM, "start", True))
parts.append(text(810, 156, "ACCELERATION RMS (g)  –  live", 12, DIM, "start", True))
chart(20, 162, 770, 224, "c_vel", "realtime1", "Live velocity", 10)
chart(810, 162, 770, 224, "c_acc", "realtime1", "Live acceleration", 1.2)
parts.append(text(20, 404, "VELOCITY RMS (mm/s)  –  history", 12, DIM, "start", True))
parts.append(text(810, 404, "ACCELERATION RMS (g)  –  history", 12, DIM, "start", True))
chart(20, 410, 770, 224, "c_vel", "history", "History velocity", 10)
chart(810, 410, 770, 224, "c_acc", "history", "History acceleration", 1.2)

for _y in (156, 404):
    axis_key(790, _y); axis_key(1580, _y)

# bottom: servo cards
CW, GAP, X0, CY, CH = 300, 15, 20, 648, 190
for n in range(1, NAXES + 1):
    x = X0 + (n - 1) * (CW + GAP)
    a = f"Axis{n}"
    parts.append(rect(x, CY, CW, CH, CARD, 6))
    parts.append(rect(x, CY, 6, CH, AXIS_COLORS[n - 1], 3))
    parts.append(text(x + 20, CY + 28, f"AXIS {n}", 18, TXT, bold=True))
    parts.append(text(x + CW - 56, CY + 24, "V", 11, DIM, "middle")); semaphore(x + CW - 56, CY + 40, f"{a}.VelRMS", th["VelRMS"][1], th["VelRMS"][2], 8, f"{a} vel status")
    parts.append(text(x + CW - 24, CY + 24, "A", 11, DIM, "middle")); semaphore(x + CW - 24, CY + 40, f"{a}.AccRMS", th["AccRMS"][1], th["AccRMS"][2], 8, f"{a} acc status")
    rows = [("Velocity RMS", "VelRMS", "mm/s", "#0.00"), ("Accel RMS", "AccRMS", "g", "#0.000"),
            ("Velocity peak", "VelPeak", "mm/s", "#0.00"), ("Accel peak", "AccPeak", "g", "#0.000"),
            ("Speed", "Speed", "rpm", "###0.0"), ("Temperature", "Temperature", "°C", "#0.0")]
    for i, (lbl, sig, unit, fmt) in enumerate(rows):
        yy = CY + 62 + i * 21
        parts.append(text(x + 20, yy, lbl, 13, DIM))
        value(x + CW - 20, yy, f"{a}.{sig}", unit, 14, TXT, "end", fmt, f"{a} {lbl}")

# footer: torque
FY = 848
parts.append(rect(20, FY, 1560, 96, CARD, 6))
parts.append(text(34, FY + 20, "TORQUE", 12, DIM, "start", True))
for n in range(1, NAXES + 1):
    x = X0 + (n - 1) * (CW + GAP)
    a = f"Axis{n}"
    progress(x + 20, FY + 30, 16, 56, f"{a}.TorqueRMS", 100, AXIS_COLORS[n - 1], f"{a} torque bar")   # vertical bar, % rated (RMS)
    parts.append(text(x + 52, FY + 42, f"Axis {n}", 14, TXT, "start", True))
    semaphore(x + CW - 30, FY + 36, f"{a}.TorqueRMS", th["TorqueRMS"][1], th["TorqueRMS"][2], 8, f"{a} torque status")
    parts.append(text(x + 52, FY + 62, "Torque", 12, DIM)); value(x + 150, FY + 62, f"{a}.Torque", "%", 14, TXT, "end", "#0.0", f"{a} torque")
    parts.append(text(x + 170, FY + 62, "RMS", 12, DIM)); value(x + CW - 20, FY + 62, f"{a}.TorqueRMS", "%", 14, TXT, "end", "#0.0", f"{a} torque rms")
    parts.append(text(x + 52, FY + 82, "Temperature", 12, DIM)); value(x + 150, FY + 82, f"{a}.Temperature", "°C", 14, TXT, "end", "#0.0", f"{a} temp (footer)")

overview = {"id": "v_overview", "name": "Overview", "type": "svg", "profile": {"width": W, "height": H, "bkcolor": BG},
            "items": items, "variables": {},
            "svgcontent": f'<svg width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg" xmlns:svg="http://www.w3.org/2000/svg" '
                          f'xmlns:html="http://www.w3.org/1999/xhtml"><g><title>Layer 1</title>{"".join(parts)}</g></svg>'}

# ---------------------------------------------------------------- Mechanism setup view
items2, parts2 = {}, []
P, I = parts2, items2
def input_box(x, y, w, h, tag, name):
    wid = uid("HXI_")
    parts2.append(f'<g id="{wid}" type="svg-ext-html_input" stroke="#000000" font-family="sans-serif" font-size="13" fill="#f1f1f1ff">'
                  f'<rect id="{uid("svg_")}" x="{x}" y="{y}" width="{w}" height="{h}" fill="#ffffff" stroke-width="0" stroke="null"/>'
                  f'<foreignObject id="{uid("H-HXI_")}" x="{x}" y="{y}" width="{w}" height="{h}">'
                  f'<INPUT id="{uid("I-HXI_")}" style="width: calc(100% - 7px); height: calc(100% - 7px); text-align: right; border: unset; '
                  f'background-color: rgb(255, 255, 255); color: rgb(0, 0, 0); vector-effect: non-scaling-stroke;" type="text"/></foreignObject></g>')
    items2[wid] = {"id": wid, "type": "svg-ext-html_input", "name": name, "label": "HtmlInput",
                    "property": ev({"options": {"updated": True, "type": "number", "numeric": True}}, tag)}   # updated=True: show the live value

def sw_button(x, y, w, h, tag, label, val, color, name):
    wid = uid("HXB_")
    parts2.append(f'<g id="{wid}" type="svg-ext-html_button" fill="#FFFFFF" font-size="13" font-family="sans-serif" stroke="#000000">'
                  f'<rect id="{uid("svg_")}" x="{x}" y="{y}" width="{w}" height="{h}" fill="{color}" stroke-width="0" stroke="#ffffff"/>'
                  f'<foreignObject id="{uid("H-HXB_")}" x="{x}" y="{y}" width="{w}" height="{h}">'
                  f'<BUTTON id="{uid("B-HXB_")}" style="width: 100%; height: 100%; vector-effect: non-scaling-stroke; background-color: {color}; color: #ffffff;" '
                  f'class="md-btn  md-btn-raised">{label}</BUTTON></foreignObject></g>')
    items2[wid] = {"id": wid, "type": "svg-ext-html_button", "name": label, "label": "HtmlButton",
                   "property": ev({"events": [{"type": "click", "action": "onSetValue", "actparam": str(val)}]}, tag)}

parts2.append(rect(0, 0, W, H, BG))
parts2.append(text(20, 34, "MECHANISM SETUP", 24, TXT, bold=True))
nav_button(parts2, items2, 1430, 16, 150, 26, "Overview", "v_overview", "Go to overview")
parts2.append(text(20, 58, "Adjust the simulated mechanisms; every axis follows the virtual master axis (position = ratio × master + phase + cam).", 13, DIM))
parts2.append(rect(20, 74, 1560, 66, CARD, 6))
parts2.append(text(40, 100, "Master speed (rpm)", 14, TXT)); input_box(200, 82, 90, 24, "Master.Speed", "Master speed setpoint")
parts2.append(text(310, 100, "Actual", 12, DIM)); value(400, 100, "Master.Speed", "rpm", 14, TXT, "end", "###0.0", "Master speed actual")
sw_button(460, 82, 90, 24, "Master.Run", "RUN", 1, "#27ae60", "Master run")
sw_button(560, 82, 90, 24, "Master.Run", "STOP", 0, "#c0392b", "Master stop")
parts2.append(text(40, 126, "Fault injection: raise Imbalance / Looseness / BearingWear / Misalignment (0 = healthy … 1 = severe) and watch the Overview.", 12, DIM))

params = [("Enabled", "Enabled (1/0)"), ("GearRatio", "Gear ratio"), ("CamAmplitude", "Cam amplitude (°)"),
          ("CamHarmonic", "Cam harmonic"), ("PhaseOffset", "Phase offset (°)"), ("Inertia", "Inertia (kg·m²)"),
          ("RatedTorque", "Rated torque (Nm)"), ("Friction", "Friction (% rated)"),
          ("Imbalance", "Imbalance 0..1"), ("Looseness", "Looseness 0..1"),
          ("BearingWear", "Bearing wear 0..1"), ("Misalignment", "Misalignment 0..1")]
cw, cg = 300, 15
for n in range(1, NAXES + 1):
    x = 20 + (n - 1) * (cw + cg)
    parts2.append(rect(x, 156, cw, 40 + len(params) * 38 + 12, CARD, 6))
    parts2.append(rect(x, 156, 6, 40 + len(params) * 38 + 12, AXIS_COLORS[n - 1], 3))
    parts2.append(text(x + 20, 184, f"AXIS {n}", 18, TXT, bold=True))
    for i, (p, lbl) in enumerate(params):
        yy = 222 + i * 38
        parts2.append(text(x + 20, yy + 4, lbl, 13, DIM))
        input_box(x + 190, yy - 14, 90, 24, f"Axis{n}.{p}", f"Axis{n} {lbl}")
setup = {"id": "v_setup", "name": "Mechanism setup", "type": "svg", "profile": {"width": W, "height": H, "bkcolor": BG},
         "items": items2, "variables": {},
         "svgcontent": f'<svg width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg" xmlns:svg="http://www.w3.org/2000/svg" '
                       f'xmlns:html="http://www.w3.org/1999/xhtml"><g><title>Layer 1</title>{"".join(parts2)}</g></svg>'}

# ---------------------------------------------------------------- project
project = {
    "version": "1.01",
    "name": "Vibration Monitor",
    "devices": {DEV_ID: device},
    "hmi": {
        "views": [overview, setup],
        "layout": {"start": "v_overview",
                   "navigation": {"mode": "over", "type": "inline",
                                  "items": [{"icon": "dashboard", "view": "v_overview", "link": "", "text": "Overview"},
                                            {"icon": "tune", "view": "v_setup", "link": "", "text": "Mechanism setup"}]},
                   "header": {"title": "Vibration Monitor"}},
    },
    "charts": charts,
    "alarms": alarms,
    "server": {"id": "0", "name": "FUXA Server", "type": "FuxaServer", "property": {}},
}

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vibration-monitor.fuxap")
with open(out, "w") as f:
    json.dump(project, f, indent=1)
print("wrote", out, f"({len(tags)} tags, {len(alarms)} alarms, {len(charts)} charts)")
