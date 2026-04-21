import random
import numpy as np
import pandas as pd
from datetime import datetime

import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output, State
import plotly.graph_objs as go

MAX_POINTS   = 40       
ALERT_THRESHOLD = 15    
CRITICAL_TEMP   = 130   

C_BLUE    = "#0866ff"   
C_GREEN   = "#1a7f37"   
C_AMBER   = "#b45309"  
C_RED     = "#c0392b"   
C_INDIGO  = "#6366f1"   
C_GREY    = "#8a9099"   

BG_PAGE   = "#f0f2f5"
BG_CARD   = "#ffffff"
BG_ALT    = "#f7f8fa"
BORDER    = "#dde1e7"
INK_900   = "#111318"
INK_600   = "#444950"



def empty_store():
    return {
        "labels":       [],
        "live_s1":      [],
        "live_s2":      [],
        "live_s3":      [],
        "twin_t":       [],
        "twin_p":       [],
        "energy":       [],
        "cum_saved":    0.0,
        "tick":         0,
        "alert_cd":     0,
        "alerts":       [],   
    }


def digital_twin(inlet_t, flow, water_cut, gas_frac, set_temp):
   
    wf = 1 + (water_cut / 100) * 0.8
    gf = 1 - (gas_frac  / 100) * 0.3
    ff = flow / 45
    base  = inlet_t + 18
    opt_t = min(base * wf * gf * ff, set_temp * 0.88)
    opt_p = (opt_t - inlet_t) * flow * 0.03 * wf
    return round(opt_t, 1), round(opt_p, 1)


def noise(amplitude):
    return (random.random() - 0.5) * 2 * amplitude


def sim_tick(state, inlet_temp, flow, water_cut, gas_frac,
             set_temp, power_pct, press):

    state["tick"] += 1
    now = datetime.now().strftime("%H:%M:%S")
    state["labels"].append(now)

    s1 = inlet_temp + noise(1.5)
    s2 = set_temp   + noise(2.5)    
    s3 = set_temp * 0.83 + noise(2)
    p  = press      + noise(0.2)
    w  = water_cut  + noise(1.5)
    g  = gas_frac   + noise(1.0)

    opt_t, opt_p = digital_twin(s1, flow, w, g, set_temp)

    actual_p = (set_temp - s1) * flow * 0.03 * (1 + w / 100 * 0.5)
    saved_kwh = max(0, actual_p - opt_p)
    state["cum_saved"] += saved_kwh * 0.01

    for arr, val in [
        ("live_s1", round(s1, 1)),
        ("live_s2", round(s2, 1)),
        ("live_s3", round(s3, 1)),
        ("twin_t",  opt_t),
        ("twin_p",  opt_p),
        ("energy",  round(saved_kwh, 1)),
    ]:
        state[arr].append(val)
        if len(state[arr]) > MAX_POINTS:
            state[arr].pop(0)

    if len(state["labels"]) > MAX_POINTS:
        state["labels"].pop(0)

    state["alert_cd"] -= 1
    if state["alert_cd"] <= 0:
        state["alert_cd"] = random.randint(6, 13)
        candidates = []
        if set_temp - opt_t > 15:
            candidates.append(("warn",
                f"HSU is {set_temp - opt_t:.1f}°C above twin optimal. "
                f"Consider reducing to {opt_t:.1f}°C."))
        if w > 50:
            candidates.append(("warn",
                f"High water cut: {w:.1f}% — separator pre-check recommended."))
        if saved_kwh > 8:
            candidates.append(("ok",
                f"Twin active: {saved_kwh:.1f} kW recoverable at current inlet conditions."))
        if s2 > 130:
            candidates.append(("err",
                f"S2 heater temperature critical: {s2:.1f}°C — exceeds safe threshold."))
        if opt_t < s2 - 25:
            candidates.append(("ok",
                f"Digital twin confidence high — estimated "
                f"{int((set_temp - opt_t) * 0.5)} kWh/hr savings."))
        if candidates:
            level, msg = random.choice(candidates)
            state["alerts"].insert(0, {"time": now, "msg": msg, "level": level})
            state["alerts"] = state["alerts"][:8]   # keep last 8

    return state, s1, s2, s3, opt_t, opt_p, actual_p, saved_kwh, p, w, g



def chart_layout(y_title=""):
    return dict(
        paper_bgcolor=BG_CARD,
        plot_bgcolor=BG_CARD,
        margin=dict(l=40, r=16, t=10, b=36),
        font=dict(family="Inter, sans-serif", color=INK_600, size=11),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="left", x=0,
            font=dict(size=10), bgcolor="rgba(0,0,0,0)"
        ),
        xaxis=dict(
            showgrid=True, gridcolor="#eef0f3", gridwidth=1,
            tickfont=dict(size=10, color=C_GREY),
            linecolor=BORDER, zeroline=False,
        ),
        yaxis=dict(
            showgrid=True, gridcolor="#eef0f3", gridwidth=1,
            tickfont=dict(size=10, color=C_GREY),
            title=dict(text=y_title, font=dict(size=10, color=C_GREY)),
            linecolor=BORDER, zeroline=False,
        ),
        hovermode="x unified",
    )


def build_live_chart(labels, s1, s2, s3):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=labels, y=s1, name="S1 Inlet",
        line=dict(color=C_BLUE, width=2),
        mode="lines+markers", marker=dict(size=3),
        fill="tozeroy", fillcolor="rgba(8,102,255,0.05)"
    ))
    fig.add_trace(go.Scatter(
        x=labels, y=s2, name="S2 Heater",
        line=dict(color=C_AMBER, width=2),
        mode="lines+markers", marker=dict(size=3),
    ))
    fig.add_trace(go.Scatter(
        x=labels, y=s3, name="S3 Outlet",
        line=dict(color=C_INDIGO, width=2),
        mode="lines+markers", marker=dict(size=3),
    ))
    fig.update_layout(**chart_layout("°C"))
    return fig


def build_twin_chart(labels, twin_t, twin_p):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=labels, y=twin_t, name="Opt. Temp (°C)",
        line=dict(color=C_GREEN, width=2),
        mode="lines+markers", marker=dict(size=3),
        fill="tozeroy", fillcolor="rgba(26,127,55,0.07)"
    ))
    fig.add_trace(go.Scatter(
        x=labels, y=twin_p, name="Opt. Power (kW)",
        line=dict(color=C_GREEN, width=1.5, dash="dash"),
        mode="lines+markers", marker=dict(size=3),
    ))
    fig.update_layout(**chart_layout("°C / kW"))
    return fig


def build_energy_chart(labels, energy):
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=labels, y=energy, name="kWh Saved",
        marker=dict(
            color="rgba(26,127,55,0.2)",
            line=dict(color=C_GREEN, width=1)
        )
    ))
    layout = chart_layout("kWh")
    layout["showlegend"] = False
    layout["margin"] = dict(l=40, r=16, t=6, b=30)
    fig.update_layout(**layout)
    return fig



SCENARIOS = {
    "High Water Cut Event": dict(water=70, temp=50, flow=60, gas=15),
    "Low Temp Inlet":       dict(water=25, temp=20, flow=40, gas=30),
    "High Flow Surge":      dict(water=30, temp=65, flow=95, gas=20),
    "Gas-Rich Stream":      dict(water=15, temp=70, flow=35, gas=55),
}




def card(children, style=None, border_color=None):
    s = {
        "background": BG_CARD,
        "border": f"1px solid {border_color or BORDER}",
        "borderRadius": "8px",
        "boxShadow": "0 1px 4px rgba(0,0,0,0.08)",
        "overflow": "hidden",
        "marginBottom": "14px",
    }
    if style:
        s.update(style)
    return html.Div(children, style=s)


def card_head(title, right=None, bg=BG_ALT):
    return html.Div([
        html.Div(title, style={
            "fontSize": "13px", "fontWeight": "600", "color": INK_900
        }),
        right or html.Span()
    ], style={
        "display": "flex", "alignItems": "center",
        "justifyContent": "space-between",
        "padding": "12px 16px",
        "borderBottom": f"1px solid {BORDER}",
        "background": bg,
    })


def section_head(text):
    return html.Div(text, style={
        "fontSize": "11px", "fontWeight": "600",
        "letterSpacing": "0.8px", "textTransform": "uppercase",
        "color": C_GREY, "marginBottom": "10px", "marginTop": "16px",
        "paddingBottom": "6px", "borderBottom": f"1px solid {BORDER}",
    })


def kpi_card(label, value_id, unit, accent_color, dot=False):
    dot_el = html.Span("● ", style={"color": accent_color, "fontSize": "9px"}) if dot else None
    return html.Div([
        html.Div([dot_el, label] if dot_el else label, style={
            "fontSize": "10px", "fontWeight": "600",
            "letterSpacing": "0.5px", "textTransform": "uppercase",
            "color": C_GREY, "marginBottom": "6px",
        }),
        html.Div("--", id=value_id, style={
            "fontSize": "26px", "fontWeight": "700",
            "letterSpacing": "-1px", "color": accent_color,
            "lineHeight": "1", "marginBottom": "4px",
        }),
        html.Div(unit, style={"fontSize": "10px", "color": C_GREY}),
        html.Div("--", id=value_id + "-delta", style={
            "fontSize": "11px", "fontWeight": "600", "marginTop": "5px",
            "padding": "2px 6px", "borderRadius": "4px", "display": "inline-block",
            "background": "#edfaf1", "color": C_GREEN,
        }),
    ], style={
        "background": BG_CARD,
        "border": f"1px solid {BORDER}",
        "borderLeft": f"3px solid {accent_color}",
        "borderRadius": "8px",
        "padding": "14px 16px",
        "boxShadow": "0 1px 2px rgba(0,0,0,0.06)",
    })


def slider_row(label, slider_id, min_val, max_val, step, default, unit):
    return html.Div([
        html.Div([
            html.Span(label, style={
                "fontSize": "12px", "fontWeight": "600", "color": INK_600
            }),
            html.Span(f"{default}{unit}", id=f"{slider_id}-lbl", style={
                "fontSize": "13px", "fontWeight": "700", "color": INK_900
            }),
        ], style={"display": "flex", "justifyContent": "space-between", "marginBottom": "8px"}),
        dcc.Slider(
            id=slider_id,
            min=min_val, max=max_val, step=step, value=default,
            marks=None,
            tooltip={"placement": "bottom", "always_visible": False},
        ),
    ], style={
        "background": BG_ALT,
        "border": f"1px solid {BORDER}",
        "borderRadius": "6px",
        "padding": "12px 14px",
    })


def status_pill(text, level="ok"):
    colors = {
        "ok":   (C_GREEN,  "#edfaf1", "#b7e9c5"),
        "warn": (C_AMBER,  "#fffbeb", "#fcd56a"),
        "err":  (C_RED,    "#fef2f2", "#fca5a5"),
    }
    fg, bg, border = colors.get(level, colors["ok"])
    return html.Span(text, style={
        "fontSize": "11px", "fontWeight": "600",
        "padding": "3px 10px", "borderRadius": "20px",
        "color": fg, "background": bg, "border": f"1px solid {border}",
    })



app = dash.Dash(__name__, title="LIIP — Light Weight Industrial Intelligence PlatforM")
server = app.server   # for deployment

app.layout = html.Div([

    dcc.Store(id="sim-store", data=empty_store()),

    dcc.Interval(id="interval", interval=1000, n_intervals=0, disabled=False),


    html.Header([
        html.Div([
            html.Span([
                "L", html.Span("II", style={"color": C_BLUE}), "P"
            ], style={
                "fontSize": "17px", "fontWeight": "700",
                "letterSpacing": "-0.5px", "color": INK_900,
            }),
            html.Span(
                "Light Weight Industrial Intelligence PlatforM",
                style={
                    "fontSize": "11px", "color": C_GREY,
                    "paddingLeft": "10px", "marginLeft": "10px",
                    "borderLeft": f"1px solid {BORDER}",
                }
            ),
        ], style={"display": "flex", "alignItems": "baseline", "gap": "10px"}),

        html.Div([
            html.Span([
                html.Span(style={
                    "width": "6px", "height": "6px", "borderRadius": "50%",
                    "background": C_GREEN, "display": "inline-block",
                    "marginRight": "5px",
                }),
                "Sensors Active"
            ], style={
                "fontSize": "11px", "fontWeight": "600", "color": C_GREEN,
                "background": "#edfaf1", "border": "1px solid #b7e9c5",
                "padding": "3px 10px", "borderRadius": "20px",
            }),
            html.Span("--:--:--", id="clock", style={
                "fontSize": "12px", "fontWeight": "500",
                "color": INK_600, "letterSpacing": "0.5px",
                "fontVariantNumeric": "tabular-nums",
            }),
        ], style={"display": "flex", "alignItems": "center", "gap": "12px"}),
    ], style={
        "background": BG_CARD,
        "borderBottom": f"1px solid {BORDER}",
        "height": "56px",
        "display": "flex", "alignItems": "center",
        "justifyContent": "space-between",
        "padding": "0 24px",
        "position": "sticky", "top": "0", "zIndex": "100",
        "boxShadow": "0 1px 2px rgba(0,0,0,0.06)",
    }),

    html.Div([

        section_head("Live Unit Metrics"),
        html.Div([
            kpi_card("Inlet Temp",        "kpi-inlet",   "°C · S1 Inlet Sensor",      C_BLUE,  dot=True),
            kpi_card("Operator Set Temp", "kpi-settemp", "°C · Current Setpoint",      C_AMBER, dot=False),
            kpi_card("Twin Optimal Temp", "kpi-twin",    "°C · Digital Twin Predicted",C_GREEN, dot=True),
            kpi_card("Flow Rate",         "kpi-flow",    "m³/h · Inlet",               C_BLUE,  dot=True),
            kpi_card("Energy Saved",      "kpi-saved",   "kWh · This Session",         C_GREEN, dot=True),
            kpi_card("Water Cut",         "kpi-water",   "% · Inlet Composition",     C_GREY,  dot=False),
        ], style={
            "display": "grid",
            "gridTemplateColumns": "repeat(6, 1fr)",
            "gap": "10px", "marginBottom": "16px",
        }),

        section_head("Process Flow — Heating Stabilization Unit"),
        card([
            html.Div([

                html.Div([
                    html.Div("WELLHEAD INPUT", style={"fontSize":"9px","fontWeight":"700","letterSpacing":"1px","textTransform":"uppercase","color":C_GREY,"marginBottom":"4px"}),
                    html.Div("-- °C", id="f-inlet-t", style={"fontSize":"16px","fontWeight":"700","color":INK_900}),
                    html.Div("-- bar", id="f-inlet-p", style={"fontSize":"10px","color":C_GREY,"marginTop":"3px"}),
                    html.Span("S1 · INLET", style={"fontSize":"9px","fontWeight":"600","padding":"1px 6px","borderRadius":"3px","background":"#e7f0ff","color":C_BLUE,"marginTop":"5px","display":"inline-block"}),
                ], style={"background":BG_ALT,"border":f"1.5px solid {C_BLUE}","borderRadius":"6px","padding":"10px 14px","minWidth":"110px","textAlign":"center"}),

                html.Div("›", style={"color":C_GREY,"fontSize":"22px","padding":"0 8px"}),

                html.Div([
                    html.Div("HSU HEATER", style={"fontSize":"9px","fontWeight":"700","letterSpacing":"1px","textTransform":"uppercase","color":C_GREY,"marginBottom":"4px"}),
                    html.Div("-- °C", id="f-hsu-t", style={"fontSize":"16px","fontWeight":"700","color":INK_900}),
                    html.Div("-- kW",  id="f-hsu-p", style={"fontSize":"10px","color":C_GREY,"marginTop":"3px"}),
                    html.Span("S2 · MID", style={"fontSize":"9px","fontWeight":"600","padding":"1px 6px","borderRadius":"3px","background":"#fffbeb","color":C_AMBER,"marginTop":"5px","display":"inline-block"}),
                ], style={"background":"#fffbeb","border":f"1.5px solid {C_AMBER}","borderRadius":"6px","padding":"10px 14px","minWidth":"110px","textAlign":"center"}),

                html.Div("›", style={"color":C_GREY,"fontSize":"22px","padding":"0 8px"}),

                html.Div([
                    html.Div("SEPARATOR OUTLET", style={"fontSize":"9px","fontWeight":"700","letterSpacing":"1px","textTransform":"uppercase","color":C_GREY,"marginBottom":"4px"}),
                    html.Div("-- °C",  id="f-out-t", style={"fontSize":"16px","fontWeight":"700","color":INK_900}),
                    html.Div("-- % gas",id="f-out-g", style={"fontSize":"10px","color":C_GREY,"marginTop":"3px"}),
                    html.Span("S3 · OUTLET", style={"fontSize":"9px","fontWeight":"600","padding":"1px 6px","borderRadius":"3px","background":"#e7f0ff","color":C_BLUE,"marginTop":"5px","display":"inline-block"}),
                ], style={"background":BG_ALT,"border":f"1.5px solid {C_BLUE}","borderRadius":"6px","padding":"10px 14px","minWidth":"110px","textAlign":"center"}),

                html.Div("- - - ›", style={"color":C_GREY,"fontSize":"14px","padding":"0 8px","letterSpacing":"2px"}),

                html.Div([
                    html.Div("DIGITAL TWIN", style={"fontSize":"9px","fontWeight":"700","letterSpacing":"1px","textTransform":"uppercase","color":C_GREEN,"marginBottom":"4px"}),
                    html.Div("-- °C", id="f-twin-t", style={"fontSize":"16px","fontWeight":"700","color":C_GREEN}),
                    html.Div("Predicted Optimal", style={"fontSize":"10px","color":C_GREY,"marginTop":"3px"}),
                    html.Span("SIMULATED", style={"fontSize":"9px","fontWeight":"600","padding":"1px 6px","borderRadius":"3px","background":"#edfaf1","color":C_GREEN,"marginTop":"5px","display":"inline-block"}),
                ], style={"background":"#edfaf1","border":f"1.5px dashed {C_GREEN}","borderRadius":"6px","padding":"10px 14px","minWidth":"110px","textAlign":"center"}),

            ], style={
                "display": "flex", "alignItems": "center",
                "padding": "14px 20px", "overflowX": "auto", "gap": "4px",
            })
        ]),

        section_head("Sensor Dashboard vs Digital Twin"),
        html.Div([

            card([
                card_head(
                    html.Div([
                        html.Div("Live Sensor Dashboard", style={"fontWeight":"600","fontSize":"13px","color":INK_900}),
                        html.Div("All downstream sensors · S1, S2, S3", style={"fontSize":"11px","color":C_GREY,"marginTop":"2px"}),
                    ]),
                    right=html.Div([
                        html.Span("● S1 Inlet", style={"color":C_BLUE,"fontSize":"10px","marginRight":"10px","fontWeight":"500"}),
                        html.Span("● S2 Heater", style={"color":C_AMBER,"fontSize":"10px","marginRight":"10px","fontWeight":"500"}),
                        html.Span("● S3 Outlet", style={"color":C_INDIGO,"fontSize":"10px","fontWeight":"500"}),
                    ]),
                ),
                html.Div(dcc.Graph(id="chart-live", config={"displayModeBar": False},
                    style={"height": "220px"}),
                    style={"padding": "12px 16px 8px"}
                ),
            ], border_color=BORDER),

            card([
                card_head(
                    html.Div([
                        html.Div("Digital Twin Simulation", style={"fontWeight":"600","fontSize":"13px","color":INK_900}),
                        html.Div("Driven by S1 inlet only · Predictive model", style={"fontSize":"11px","color":C_GREY,"marginTop":"2px"}),
                    ]),
                    right=html.Div([
                        html.Span("— Opt. Temp", style={"color":C_GREEN,"fontSize":"10px","marginRight":"10px","fontWeight":"500"}),
                        html.Span("- - Opt. Power", style={"color":C_GREEN,"fontSize":"10px","fontWeight":"500"}),
                    ]),
                    bg="#f6fef9",
                ),
                html.Div(dcc.Graph(id="chart-twin", config={"displayModeBar": False},
                    style={"height": "220px"}),
                    style={"padding": "12px 16px 8px"}
                ),
            ], border_color="#b7e9c5"),

        ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "14px"}),

        html.Div([

            card([
                card_head(
                    "Live vs Twin Comparison",
                    right=html.Div("Within Range", id="status-pill", style={
                        "fontSize":"11px","fontWeight":"600",
                        "padding":"3px 10px","borderRadius":"20px",
                        "color":C_GREEN,"background":"#edfaf1","border":"1px solid #b7e9c5",
                    }),
                ),
                html.Div(
                    dash_table.DataTable(
                        id="cmp-table",
                        columns=[
                            {"name": "Parameter",     "id": "param"},
                            {"name": "● Live",        "id": "live"},
                            {"name": "● Twin Optimal","id": "twin"},
                            {"name": "Δ Saving",      "id": "delta"},
                        ],
                        data=[
                            {"param":"Temperature (°C)", "live":"--","twin":"--","delta":"--"},
                            {"param":"Power Draw (kW)",  "live":"--","twin":"--","delta":"--"},
                            {"param":"Pressure (bar)",   "live":"--","twin":"--","delta":"--"},
                            {"param":"Gas% at Outlet",   "live":"--","twin":"--","delta":"--"},
                        ],
                        style_table={"overflowX": "auto"},
                        style_header={
                            "backgroundColor": BG_ALT,
                            "fontWeight": "600", "fontSize": "10px",
                            "color": C_GREY, "textTransform": "uppercase",
                            "letterSpacing": "0.5px", "border": f"1px solid {BORDER}",
                        },
                        style_cell={
                            "fontFamily": "Inter, sans-serif",
                            "fontSize": "12px", "color": INK_600,
                            "padding": "9px 12px",
                            "border": f"1px solid {BORDER}",
                            "textAlign": "center",
                        },
                        style_cell_conditional=[
                            {"if": {"column_id": "param"}, "textAlign": "left",
                             "fontWeight": "500", "color": INK_900},
                            {"if": {"column_id": "live"}, "color": C_BLUE, "fontWeight": "600"},
                            {"if": {"column_id": "twin"}, "color": C_GREEN, "fontWeight": "600"},
                        ],
                        style_data_conditional=[
                            {"if": {"filter_query": '{delta} contains "↓"'},
                             "color": C_GREEN, "fontWeight": "700"},
                            {"if": {"filter_query": '{delta} contains "↑"'},
                             "color": C_RED, "fontWeight": "700"},
                        ],
                        page_action="none",
                    ),
                    style={"padding": "0"}
                ),
            ]),

            card([
                card_head("Energy Optimization", right=html.Span("Session total", style={"fontSize":"11px","color":C_GREY})),
                html.Div([
                    html.Div([
                        html.Div("--%", id="e-pct", style={
                            "fontSize": "52px", "fontWeight": "700",
                            "color": C_GREEN, "lineHeight": "1",
                            "letterSpacing": "-2px", "textAlign": "center",
                        }),
                        html.Div("potential energy reduction vs current operation", style={
                            "fontSize": "12px", "color": C_GREY, "textAlign": "center", "marginTop": "4px",
                        }),
                        # Progress bar
                        html.Div(html.Div(id="e-bar", style={
                            "height": "100%", "background": C_GREEN,
                            "borderRadius": "4px", "width": "0%",
                            "transition": "width 0.8s ease",
                        }), style={
                            "height": "8px", "background": BORDER,
                            "borderRadius": "4px", "margin": "16px 0 8px",
                        }),
                        html.Div("-- kWh saved this session", id="e-kwh", style={
                            "fontSize": "12px", "color": C_GREY, "textAlign": "center",
                        }),
                    ], style={"padding": "20px"}),
                    dcc.Graph(id="chart-energy", config={"displayModeBar": False},
                        style={"height": "110px", "padding": "0 16px 8px"}),
                ]),
            ]),

        ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "14px"}),

        section_head("Simulation Controls"),
        html.Div([

            card([
                card_head(html.Span([
                    "Inlet Feed Controls ",
                    html.Span("— S1 Sensor Simulation", style={"fontWeight":"400","fontSize":"11px","color":C_GREY}),
                ])),
                html.Div([
                    slider_row("Inlet Temperature", "sl-inlet-temp", 20, 120, 0.5, 60, "°C"),
                    slider_row("Flow Rate",         "sl-flow",        5, 100, 1,   45, " m³/h"),
                    slider_row("Water Cut",         "sl-water",       5,  80, 0.5, 30, "%"),
                    slider_row("Gas Fraction",      "sl-gas",         5,  60, 0.5, 25, "%"),
                ], style={"display":"grid","gridTemplateColumns":"1fr 1fr","gap":"10px","padding":"14px"}),
            ]),

            card([
                card_head(html.Span([
                    "Operator Setpoints ",
                    html.Span("— Current Manual Settings", style={"fontWeight":"400","fontSize":"11px","color":C_GREY}),
                ])),
                html.Div([
                    slider_row("Set Temperature",  "sl-set-temp", 50, 150, 1,  95, "°C"),
                    slider_row("Heater Power",     "sl-power",    10, 100, 1,  80, "%"),
                    html.Div(
                        slider_row("Pressure Setpoint", "sl-press", 4, 30, 0.5, 12, " bar"),
                        style={"gridColumn": "span 2"},
                    ),
                ], style={"display":"grid","gridTemplateColumns":"1fr 1fr","gap":"10px","padding":"14px"}),
            ]),

        ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "14px"}),

        section_head("System Alerts"),
        card([
            card_head("Alert Feed", right=html.Span("Auto-generated · Real-time", style={"fontSize":"11px","color":C_GREY})),
            html.Div(id="alert-feed", style={"padding": "12px 16px", "display":"flex","flexDirection":"column","gap":"6px","maxHeight":"200px","overflowY":"auto"}),
        ]),

        html.Div([
            html.Button("⏵ Simulation Running", id="btn-sim", n_clicks=0, style={
                "background": C_BLUE, "color": "#fff",
                "border": f"1px solid {C_BLUE}", "borderRadius": "6px",
                "padding": "7px 16px", "cursor": "pointer",
                "fontFamily": "Inter, sans-serif", "fontSize": "12px", "fontWeight": "600",
            }),
            html.Div([
                dcc.Dropdown(
                    id="scenario-dropdown",
                    options=[{"label": k, "value": k} for k in SCENARIOS],
                    placeholder="Inject Scenario...",
                    clearable=True,
                    style={"width": "220px", "fontSize": "12px"},
                ),
            ]),
            html.Button("Reset", id="btn-reset", n_clicks=0, style={
                "background": "white", "color": C_RED,
                "border": "1px solid #fca5a5", "borderRadius": "6px",
                "padding": "7px 16px", "cursor": "pointer",
                "fontFamily": "Inter, sans-serif", "fontSize": "12px", "fontWeight": "600",
            }),
            html.Div([
                html.Span("Speed:", style={"fontSize":"12px","color":C_GREY,"fontWeight":"500"}),
                dcc.Slider(id="sl-speed", min=1, max=5, step=1, value=2,
                    marks={i: str(i)+"×" for i in range(1, 6)},
                    tooltip={"placement": "top", "always_visible": False},
                ),
            ], style={"display":"flex","alignItems":"center","gap":"10px","marginLeft":"auto","width":"220px"}),
        ], style={
            "position": "sticky", "bottom": "0",
            "background": BG_CARD, "borderTop": f"1px solid {BORDER}",
            "padding": "10px 20px",
            "display": "flex", "alignItems": "center", "gap": "10px",
            "boxShadow": "0 -2px 8px rgba(0,0,0,0.06)", "zIndex": "100",
            "marginTop": "20px",
        }),

    ], style={"maxWidth": "1440px", "margin": "0 auto", "padding": "20px 20px 80px"}),

], style={"fontFamily": "Inter, sans-serif", "background": BG_PAGE, "minHeight": "100vh"})




@app.callback(Output("clock", "children"), Input("interval", "n_intervals"))
def update_clock(_):
    return datetime.now().strftime("%H:%M:%S")

@app.callback(Output("interval", "interval"), Input("sl-speed", "value"))
def set_speed(speed):
    return max(400, int(2000 / speed))


@app.callback(
    Output("interval", "disabled"),
    Output("btn-sim", "children"),
    Output("btn-sim", "style"),
    Input("btn-sim", "n_clicks"),
    State("interval", "disabled"),
)
def toggle_sim(n, disabled):
    if n == 0:
        return False, "⏵ Simulation Running", {
            "background": C_BLUE, "color": "#fff",
            "border": f"1px solid {C_BLUE}", "borderRadius": "6px",
            "padding": "7px 16px", "cursor": "pointer",
            "fontFamily": "Inter, sans-serif", "fontSize": "12px", "fontWeight": "600",
        }
    if disabled:
        return False, "⏵ Simulation Running", {
            "background": C_BLUE, "color": "#fff",
            "border": f"1px solid {C_BLUE}", "borderRadius": "6px",
            "padding": "7px 16px", "cursor": "pointer",
            "fontFamily": "Inter, sans-serif", "fontSize": "12px", "fontWeight": "600",
        }
    else:
        return True, "⏸ Paused", {
            "background": "white", "color": INK_900,
            "border": f"1px solid {BORDER}", "borderRadius": "6px",
            "padding": "7px 16px", "cursor": "pointer",
            "fontFamily": "Inter, sans-serif", "fontSize": "12px", "fontWeight": "600",
        }


@app.callback(
    Output("sl-inlet-temp", "value"),
    Output("sl-flow",       "value"),
    Output("sl-water",      "value"),
    Output("sl-gas",        "value"),
    Input("scenario-dropdown", "value"),
    prevent_initial_call=True,
)
def inject_scenario(scenario):
    if not scenario:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update
    s = SCENARIOS[scenario]
    return s["temp"], s["flow"], s["water"], s["gas"]


@app.callback(
    Output("sim-store", "data", allow_duplicate=True),
    Input("btn-reset", "n_clicks"),
    prevent_initial_call=True,
)
def reset(_):
    return empty_store()


@app.callback(
    Output("sl-inlet-temp-lbl", "children"),
    Output("sl-flow-lbl",       "children"),
    Output("sl-water-lbl",      "children"),
    Output("sl-gas-lbl",        "children"),
    Output("sl-set-temp-lbl",   "children"),
    Output("sl-power-lbl",      "children"),
    Output("sl-press-lbl",      "children"),
    Input("sl-inlet-temp", "value"),
    Input("sl-flow",       "value"),
    Input("sl-water",      "value"),
    Input("sl-gas",        "value"),
    Input("sl-set-temp",   "value"),
    Input("sl-power",      "value"),
    Input("sl-press",      "value"),
)
def update_labels(inlet, flow, water, gas, set_t, power, press):
    return (
        f"{inlet}°C", f"{flow} m³/h", f"{water}%", f"{gas}%",
        f"{set_t}°C", f"{power}%", f"{press} bar"
    )


@app.callback(
    Output("sim-store", "data"),
    Output("kpi-inlet",        "children"),
    Output("kpi-inlet-delta",  "children"),
    Output("kpi-settemp",      "children"),
    Output("kpi-settemp-delta","children"),
    Output("kpi-twin",         "children"),
    Output("kpi-twin-delta",   "children"),
    Output("kpi-flow",         "children"),
    Output("kpi-flow-delta",   "children"),
    Output("kpi-saved",        "children"),
    Output("kpi-saved-delta",  "children"),
    Output("kpi-water",        "children"),
    Output("kpi-water-delta",  "children"),
    Output("f-inlet-t", "children"),
    Output("f-inlet-p", "children"),
    Output("f-hsu-t",   "children"),
    Output("f-hsu-p",   "children"),
    Output("f-out-t",   "children"),
    Output("f-out-g",   "children"),
    Output("f-twin-t",  "children"),
    Output("chart-live",   "figure"),
    Output("chart-twin",   "figure"),
    Output("chart-energy", "figure"),
    Output("cmp-table", "data"),
    Output("status-pill", "children"),
    Output("status-pill", "style"),
    Output("e-pct", "children"),
    Output("e-bar", "style"),
    Output("e-kwh", "children"),
    Output("alert-feed", "children"),
    Input("interval", "n_intervals"),
    State("sim-store",    "data"),
    State("sl-inlet-temp","value"),
    State("sl-flow",      "value"),
    State("sl-water",     "value"),
    State("sl-gas",       "value"),
    State("sl-set-temp",  "value"),
    State("sl-power",     "value"),
    State("sl-press",     "value"),
    prevent_initial_call=False,
)
def main_tick(n, state, inlet_temp, flow, water_cut, gas_frac,
              set_temp, power_pct, press):

    state, s1, s2, s3, opt_t, opt_p, actual_p, saved_kwh, p, w, g = sim_tick(
        state, inlet_temp, flow, water_cut, gas_frac,
        set_temp, power_pct, press
    )

    labels    = state["labels"]
    cum_saved = state["cum_saved"]

    diff = set_temp - opt_t
    twin_delta_txt = f"↓ {diff:.1f}°C below setpoint" if diff > 0 else "At setpoint"

    f_inlet_t = f"{s1:.1f} °C"
    f_inlet_p = f"{p:.1f} bar"
    f_hsu_t   = f"{s2:.1f} °C"
    f_hsu_p   = f"{power_pct * 0.8:.0f} kW"
    f_out_t   = f"{s3:.1f} °C"
    f_out_g   = f"{g * 0.7:.1f}% gas"
    f_twin_t  = f"{opt_t:.1f} °C"

    fig_live   = build_live_chart(labels, state["live_s1"], state["live_s2"], state["live_s3"])
    fig_twin   = build_twin_chart(labels, state["twin_t"], state["twin_p"])
    fig_energy = build_energy_chart(labels, state["energy"])

    def delta_str(val, unit):
        if val > 0.5:   return f"↓ {val:.1f}{unit}"
        elif val < -0.5: return f"↑ {abs(val):.1f}{unit}"
        else:            return f"≈ 0{unit}"

    cmp_data = [
        {"param":"Temperature (°C)", "live":f"{set_temp:.1f}", "twin":f"{opt_t:.1f}", "delta": delta_str(set_temp - opt_t, "°C")},
        {"param":"Power Draw (kW)",  "live":f"{actual_p:.1f}", "twin":f"{opt_p:.1f}", "delta": delta_str(actual_p - opt_p, " kW")},
        {"param":"Pressure (bar)",   "live":f"{p:.1f}",        "twin":f"{p*0.97:.1f}", "delta": delta_str(p * 0.03, " bar")},
        {"param":"Gas% at Outlet",   "live":f"{g:.1f}%",       "twin":f"{g*0.95:.1f}%","delta": delta_str(g * 0.05, "%")},
    ]

    if s2 > CRITICAL_TEMP:
        pill_txt   = "● Critical — Overtemp"
        pill_style = {"fontSize":"11px","fontWeight":"600","padding":"3px 10px","borderRadius":"20px","color":C_RED,"background":"#fef2f2","border":"1px solid #fca5a5"}
    elif (set_temp - opt_t) > ALERT_THRESHOLD:
        pill_txt   = "● Overheating — Waste Detected"
        pill_style = {"fontSize":"11px","fontWeight":"600","padding":"3px 10px","borderRadius":"20px","color":C_AMBER,"background":"#fffbeb","border":"1px solid #fcd56a"}
    else:
        pill_txt   = "● Within Range"
        pill_style = {"fontSize":"11px","fontWeight":"600","padding":"3px 10px","borderRadius":"20px","color":C_GREEN,"background":"#edfaf1","border":"1px solid #b7e9c5"}

    pct = min(int((saved_kwh / max(actual_p, 1)) * 100), 38)
    e_bar_style = {
        "height":"100%","background":C_GREEN,"borderRadius":"4px",
        "width":f"{pct*2.6}%","transition":"width 0.8s ease",
    }

    level_styles = {
        "ok":   {"background":"#edfaf1","border":"1px solid #b7e9c5","color":C_GREEN},
        "warn": {"background":"#fffbeb","border":"1px solid #fcd56a","color":C_AMBER},
        "err":  {"background":"#fef2f2","border":"1px solid #fca5a5","color":C_RED},
    }

    alert_divs = []
    for a in state["alerts"]:
        s = {**level_styles.get(a["level"], level_styles["ok"]),
             "padding":"8px 12px","borderRadius":"6px",
             "fontSize":"12px","display":"flex","gap":"10px","alignItems":"flex-start"}
        alert_divs.append(html.Div([
            html.Span(a["time"], style={"opacity":"0.6","flexShrink":"0","fontVariantNumeric":"tabular-nums","paddingTop":"1px"}),
            html.Span(a["msg"]),
        ], style=s))

    if not alert_divs:
        alert_divs = [html.Div("System initializing — awaiting simulation data.",
            style={"fontSize":"12px","color":C_GREY,"padding":"8px"})]

    return (
        state,
        # KPIs
        f"{s1:.1f}", "S1 Active",
        f"{set_temp:.0f}", "Max Safety Margin",
        f"{opt_t:.1f}", twin_delta_txt,
        f"{flow:.1f}", "—",
        f"{cum_saved:.1f}", "↑ Cumulative",
        f"{w:.1f}", "—",
        # Flow
        f_inlet_t, f_inlet_p, f_hsu_t, f_hsu_p, f_out_t, f_out_g, f_twin_t,
        # Charts
        fig_live, fig_twin, fig_energy,
        # Table
        cmp_data,
        # Pill
        pill_txt, pill_style,
        # Energy
        f"{pct}%", e_bar_style, f"{cum_saved:.2f} kWh saved this session",
        # Alerts
        alert_divs,
    )

if __name__ == "__main__":
    print("\n" + "="*60)
    print("  LIIP — Light Weight Industrial Intelligence PlatforM")
    print("  Starting server...")
    print("  Open your browser at:  http://127.0.0.1:8050")
    print("="*60 + "\n")
    app.run(debug=True)
