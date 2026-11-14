"""
plot_raw_lora.py
Genera todas las gráficas del reporte a partir de los datos raw LoRa.

Ejecutar desde la carpeta raíz del proyecto (proyecto_lora_raw/):
    python3 codigo/plot_raw_lora.py

Fuentes:
  - resultados/summary.csv
  - resultados/energy_raw_<config>.csv

Salida:
  - graficas/G1_sf_sweep.png ... G11_summary_table.png
"""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import os, sys

# Ejecutar siempre desde la raíz del proyecto
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

# ── Configuración global ───────────────────────────────────────────
OUT  = "graficas"
os.makedirs(OUT, exist_ok=True)

matplotlib.rcParams.update({
    "font.family":        "DejaVu Sans",
    "font.size":          11,
    "axes.spines.top":    False,
    "axes.spines.right":  False,
    "axes.grid":          True,
    "grid.alpha":         0.3,
    "grid.linestyle":     "--",
})

BLUE   = "#2196F3"
RED    = "#F44336"
GREEN  = "#4CAF50"
ORANGE = "#FF9800"
PURPLE = "#9C27B0"
TEAL   = "#009688"

def save(fig, name):
    p = f"{OUT}/{name}.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  ✓ {name}.png")

# ── Carga de datos ─────────────────────────────────────────────────
df = pd.read_csv("resultados/summary.csv")

# Sub-conjuntos por barrido (un único gateway)
sf_df  = df[(df.heartbeat==300)&(df.nodes==500)].sort_values("sf").reset_index(drop=True)
hb_df  = df[(df.sf==7)&(df.nodes==500)].sort_values("heartbeat").reset_index(drop=True)
n_df   = df[(df.sf==7)&(df.heartbeat==300)].sort_values("nodes").reset_index(drop=True)

# Parámetros hardware
BATT_J   = 13320.0
TX_W     = 0.333        # 90 mA × 3.7 V
SLEEP_W  = 0.01295e-3   # 3.5 µA × 3.7 V
MCU_W    = 0.01650      # 5 mA × 3.3 V
PKTS_DAY = 308

def airtime(sf, bw=125e3, payload=20, cr=1):
    Tsym = 2**sf / bw
    n    = 8 + max(0, np.ceil((8*payload - 4*sf + 28 + 16)/(4*sf)) * (4+cr))
    return (12.25 + n) * Tsym

print("Generando gráficas raw LoRa…")

# ══════════════════════════════════════════════════════════════════
# G1 — Barrido SF: 4 métricas en un solo panel
# ══════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(2, 2, figsize=(13, 9))
fig.suptitle("Barrido de Spreading Factor — LoRa Raw\n(1 GW · 300 s · 500 nodos)", fontsize=13)

sfs    = sf_df["sf"].apply(lambda x: f"SF{x}").tolist()
cmap   = plt.cm.RdYlGn_r(np.linspace(0.05, 0.95, len(sf_df)))

# PDR
ax = axes[0,0]
bars = ax.bar(sfs, sf_df["pdr"], color=cmap, width=0.6, edgecolor="white")
for b, v in zip(bars, sf_df["pdr"]):
    ax.text(b.get_x()+b.get_width()/2, b.get_height()+0.6,
            f"{v:.1f}%", ha="center", fontsize=9, fontweight="bold")
ax.axhline(95, color="gray", ls="--", lw=1, label="95 %")
ax.set_ylabel("PDR [%]"); ax.set_title("PDR"); ax.set_ylim(0,108); ax.legend(fontsize=8)

# Colisión
ax = axes[0,1]
bars = ax.bar(sfs, sf_df["collision_rate"], color=cmap, width=0.6, edgecolor="white")
for b, v in zip(bars, sf_df["collision_rate"]):
    ax.text(b.get_x()+b.get_width()/2, b.get_height()+0.5,
            f"{v:.1f}%", ha="center", fontsize=9)
ax.set_ylabel("Tasa de colisión [%]"); ax.set_title("Colisiones PHY")

# Consumo diario (log)
ax = axes[1,0]
bars = ax.bar(sfs, sf_df["daily_rate_J"], color=cmap, width=0.6, edgecolor="white")
for b, v in zip(bars, sf_df["daily_rate_J"]):
    ax.text(b.get_x()+b.get_width()/2, v*1.15, f"{v:.1f}", ha="center", fontsize=8)
ax.set_yscale("log"); ax.set_ylabel("Consumo diario [J/día] (log)"); ax.set_title("Energía diaria")

# Vida útil
ax = axes[1,1]
bars = ax.bar(sfs, sf_df["lifetime_days"], color=cmap, width=0.6, edgecolor="white")
for b, v in zip(bars, sf_df["lifetime_days"]):
    ax.text(b.get_x()+b.get_width()/2, b.get_height()+15, f"{v:.0f}", ha="center", fontsize=8)
ax.axhline(365,   color=GREEN,  ls="--", lw=1.1, label="1 año")
ax.axhline(365*3, color=BLUE,   ls="--", lw=1.1, label="3 años")
ax.set_ylabel("Vida útil estimada [días]"); ax.set_title("Vida útil batería")
ax.legend(fontsize=8)

plt.tight_layout()
save(fig, "G1_sf_sweep")

# ══════════════════════════════════════════════════════════════════
# G3 — Barrido Heartbeat (4 paneles)
# ══════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(2, 2, figsize=(13, 9))
fig.suptitle("Barrido de Intervalo Heartbeat — LoRa Raw\n(SF7 · 1 GW · 500 nodos)", fontsize=13)

hb_x = hb_df["heartbeat"].values
mk   = dict(markersize=9, markerfacecolor="white", markeredgewidth=2.5)

ax = axes[0,0]
ax.plot(hb_x, hb_df["pdr"], "o-", color=BLUE, linewidth=2.5, **mk)
for x, y in zip(hb_x, hb_df["pdr"]):
    ax.annotate(f"{y:.1f}%", (x, y), xytext=(4, 6), textcoords="offset points", fontsize=9)
ax.axhline(95, color="gray", ls="--", lw=1, label="95 %")
ax.set_xlabel("Intervalo [s]"); ax.set_ylabel("PDR [%]"); ax.set_title("PDR")
ax.set_ylim(35, 102); ax.legend(fontsize=8)
ax.fill_between(hb_x, hb_df["pdr"], 35, alpha=0.07, color=BLUE)

ax = axes[0,1]
ax.plot(hb_x, hb_df["collision_rate"], "o-", color=RED, linewidth=2.5, **mk)
for x, y in zip(hb_x, hb_df["collision_rate"]):
    ax.annotate(f"{y:.1f}%", (x, y), xytext=(4, 6), textcoords="offset points", fontsize=9)
ax.set_xlabel("Intervalo [s]"); ax.set_ylabel("Colisiones [%]"); ax.set_title("Tasa de colisión")
ax.fill_between(hb_x, hb_df["collision_rate"], 0, alpha=0.07, color=RED)

ax = axes[1,0]
ax.plot(hb_x, hb_df["daily_rate_J"], "o-", color=ORANGE, linewidth=2.5, **mk)
for x, y in zip(hb_x, hb_df["daily_rate_J"]):
    ax.annotate(f"{y:.1f}", (x, y), xytext=(4, 6), textcoords="offset points", fontsize=9)
ax.set_xlabel("Intervalo [s]"); ax.set_ylabel("J/día"); ax.set_title("Consumo energético diario")
ax.fill_between(hb_x, hb_df["daily_rate_J"], 0, alpha=0.07, color=ORANGE)

ax = axes[1,1]
ax.plot(hb_x, hb_df["lifetime_days"], "s-", color=GREEN, linewidth=2.5, **mk)
for x, y in zip(hb_x, hb_df["lifetime_days"]):
    ax.annotate(f"{y:.0f}d", (x, y), xytext=(4, 6), textcoords="offset points", fontsize=9)
ax.axhline(365,    color=GREEN,  ls="--", lw=1, label="1 año")
ax.axhline(365*3,  color=BLUE,   ls="--", lw=1, label="3 años")
ax.axhline(365*10, color=PURPLE, ls="--", lw=1, label="10 años")
ax.set_xlabel("Intervalo [s]"); ax.set_ylabel("Días"); ax.set_title("Vida útil estimada")
ax.legend(fontsize=8)
ax.fill_between(hb_x, hb_df["lifetime_days"], 0, alpha=0.07, color=GREEN)

plt.tight_layout()
save(fig, "G3_heartbeat_sweep")

# ══════════════════════════════════════════════════════════════════
# G4 — Escalabilidad (3 paneles)
# ══════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 3, figsize=(14, 5))
fig.suptitle("Escalabilidad — LoRa Raw\n(SF7 · 1 GW · 300 s heartbeat)", fontsize=13)

n_x = n_df["nodes"].values
mk2 = dict(markersize=9, markerfacecolor="white", markeredgewidth=2.5)

ax = axes[0]
ax.plot(n_x, n_df["pdr"], "o-", color=BLUE, linewidth=2.5, **mk2)
for x, y in zip(n_x, n_df["pdr"]):
    ax.annotate(f"{y:.1f}%", (x, y), xytext=(4, 5), textcoords="offset points", fontsize=9)
ax.axhline(95, color="gray", ls="--", lw=1, label="95 %")
ax.set_xlabel("Nodos"); ax.set_ylabel("PDR [%]"); ax.set_title("PDR vs Densidad")
ax.set_ylim(60, 102); ax.legend(fontsize=8)
ax.fill_between(n_x, n_df["pdr"], 60, alpha=0.07, color=BLUE)

ax = axes[1]
ax.plot(n_x, n_df["collision_rate"], "o-", color=RED, linewidth=2.5, **mk2)
for x, y in zip(n_x, n_df["collision_rate"]):
    ax.annotate(f"{y:.1f}%", (x, y), xytext=(4, 5), textcoords="offset points", fontsize=9)
# Línea de regresión
z = np.polyfit(n_x, n_df["collision_rate"], 1)
p = np.poly1d(z)
ax.plot(n_x, p(n_x), "--", color="gray", lw=1,
        label=f"Tendencia: +{z[0]*100:.2f}%/100 nodos")
ax.set_xlabel("Nodos"); ax.set_ylabel("Colisiones [%]"); ax.set_title("Colisiones vs Densidad")
ax.legend(fontsize=8)

ax = axes[2]
ax.plot(n_x, n_df["avg_energy_J"], "D-", color=PURPLE, linewidth=2.5, **mk2)
for x, y in zip(n_x, n_df["avg_energy_J"]):
    ax.annotate(f"{y:.4f} J", (x, y), xytext=(4, 5), textcoords="offset points", fontsize=8)
ax.fill_between(n_x,
                n_df["avg_energy_J"] - n_df["std_dev_J"],
                n_df["avg_energy_J"] + n_df["std_dev_J"],
                alpha=0.15, color=PURPLE, label="±1σ")
ax.set_xlabel("Nodos"); ax.set_ylabel("J/nodo/hora"); ax.set_title("Energía/nodo (invariante)")
ax.set_ylim(0.25, 0.32); ax.legend(fontsize=8)

plt.tight_layout()
save(fig, "G4_scalability")

# ══════════════════════════════════════════════════════════════════
# G5 — Distribución por nodo: SF7 vs SF12
# ══════════════════════════════════════════════════════════════════
df_sf7  = pd.read_csv("resultados/energy_raw_SF7.csv")
df_sf12 = pd.read_csv("resultados/energy_raw_SF12.csv")

fig, axes = plt.subplots(1, 2, figsize=(12, 5))
fig.suptitle("Distribución de energía consumida por nodo — 1 hora\n(500 nodos, 1 GW, 300 s)", fontsize=13)

for ax, data, color, label in [
    (axes[0], df_sf7["total_energy_J"],  BLUE, "Config A — SF7"),
    (axes[1], df_sf12["total_energy_J"], RED,  "Config B — SF12"),
]:
    ax.hist(data, bins=40, color=color, alpha=0.85, edgecolor="white", linewidth=0.4)
    ax.axvline(data.mean(), color="black", ls="--", lw=1.5,
               label=f"μ = {data.mean():.4f} J")
    ax.axvline(data.mean()-data.std(), color="gray", ls=":", lw=1)
    ax.axvline(data.mean()+data.std(), color="gray", ls=":", lw=1,
               label=f"σ = {data.std():.4f} J")
    ax.set_xlabel("Energía consumida [J]")
    ax.set_ylabel("Número de nodos")
    ax.set_title(label)
    ax.legend(fontsize=9)

plt.tight_layout()
save(fig, "G5_energy_distribution")

# ══════════════════════════════════════════════════════════════════
# G6 — Vida útil todos los escenarios con rango de degradación
# ══════════════════════════════════════════════════════════════════
df_s = df.sort_values("lifetime_days").reset_index(drop=True)
labels = [f"SF{r.sf} | {r.gw}GW | {r.heartbeat}s | {r.nodes}n"
          for _, r in df_s.iterrows()]
dot_colors = [GREEN if v >= 365 else ORANGE if v >= 180 else RED
              for v in df_s["lifetime_days"]]

fig, ax = plt.subplots(figsize=(14, 7.5))

# Barra de rango: desde vida útil a año 5 hasta batería nueva
ax.barh(range(len(df_s)),
        df_s["lifetime_days"] - df_s["lifetime_yr5_days"],
        left=df_s["lifetime_yr5_days"],
        color="lightblue", alpha=0.4, height=0.6,
        label="Rango degradación (año 0 → año 5)")

# Línea base (batería nueva)
ax.hlines(range(len(df_s)), 0, df_s["lifetime_days"],
          color="lightgray", linewidth=1)

# Punto batería nueva
ax.scatter(df_s["lifetime_days"], range(len(df_s)),
           color=dot_colors, s=90, zorder=4, label="Batería nueva (día 0)")

# Punto EOL 80%
ax.scatter(df_s["lifetime_eol_days"], range(len(df_s)),
           color="gray", s=50, marker="D", zorder=4,
           alpha=0.7, label="EOL 80% (día 500)")

# Punto año 5
ax.scatter(df_s["lifetime_yr5_days"], range(len(df_s)),
           color="tomato", s=50, marker="v", zorder=4,
           alpha=0.8, label="Año 5 (día 1825, 27%)")

ax.set_yticks(range(len(df_s)))
ax.set_yticklabels(labels, fontsize=9)
ax.set_xlabel("Vida útil de reserva sin recarga solar [días]")
ax.set_title("Vida útil estimada — rango de degradación\n"
             "◆ = batería nueva   ◆ = EOL 80%   ▼ = año 5 (27%)")

for ref, col, lbl in [(365, GREEN, "1 año"), (365*3, BLUE, "3 años")]:
    ax.axvline(ref, color=col, ls="--", lw=1.2, label=lbl)

for i, r in df_s.iterrows():
    ax.text(r["lifetime_days"] + 20, i,
            f"{r['lifetime_days']:.0f}→{r['lifetime_yr5_days']:.0f}d",
            va="center", fontsize=7.5, color=dot_colors[i])

ax.legend(loc="lower right", fontsize=9)
plt.tight_layout()
save(fig, "G6_lifetime_all")

# ══════════════════════════════════════════════════════════════════
# G7 — Mapa de calor: Vida útil (SF × Heartbeat)
# ══════════════════════════════════════════════════════════════════
sub   = df[(df.gw==1)&(df.nodes==500)]
sfs_u = sorted(sub["sf"].unique())
hbs_u = sorted(sub["heartbeat"].unique())

mat = np.full((len(sfs_u), len(hbs_u)), np.nan)
for i, s in enumerate(sfs_u):
    for j, h in enumerate(hbs_u):
        r = sub[(sub.sf==s)&(sub.heartbeat==h)]
        if not r.empty:
            mat[i, j] = r.iloc[0]["lifetime_days"]

fig, ax = plt.subplots(figsize=(10, 6))
im = ax.imshow(mat, aspect="auto", cmap="RdYlGn", vmin=0, vmax=5000)
ax.set_xticks(range(len(hbs_u)))
ax.set_xticklabels([f"{h}s" for h in hbs_u])
ax.set_yticks(range(len(sfs_u)))
ax.set_yticklabels([f"SF{s}" for s in sfs_u])
ax.set_xlabel("Intervalo heartbeat")
ax.set_ylabel("Spreading Factor")
ax.set_title("Mapa de calor: Vida útil estimada [días]\n(1 GW · 500 nodos · LoRa raw)")
plt.colorbar(im, ax=ax, label="Vida útil [días]")

for i in range(len(sfs_u)):
    for j in range(len(hbs_u)):
        if not np.isnan(mat[i, j]):
            tc = "white" if mat[i, j] < 800 else "black"
            ax.text(j, i, f"{mat[i,j]:.0f}", ha="center", va="center",
                    fontsize=10, fontweight="bold", color=tc)

plt.tight_layout()
save(fig, "G7_lifetime_heatmap")

# ══════════════════════════════════════════════════════════════════
# G8 — Desglose analítico de energía diaria por SF
# ══════════════════════════════════════════════════════════════════
sfs_all = [7, 8, 9, 10, 11, 12]
E_tx    = [TX_W   * airtime(s) * PKTS_DAY for s in sfs_all]
E_sl    = [SLEEP_W * max(0, 86400 - airtime(s)*PKTS_DAY) for s in sfs_all]
E_tot   = [t + s for t, s in zip(E_tx, E_sl)]

x = np.arange(len(sfs_all)); w = 0.5
lbl = [f"SF{s}" for s in sfs_all]
cm  = plt.cm.RdYlGn_r(np.linspace(0.05, 0.95, len(sfs_all)))

fig, ax = plt.subplots(figsize=(10, 5.5))
bars_tx = ax.bar(x, E_tx, w, color=RED,   alpha=0.85, label="TX (SX1262)")
bars_sl = ax.bar(x, E_sl, w, bottom=E_tx, color=BLUE, alpha=0.85, label="Sleep")

for i, tot in enumerate(E_tot):
    ax.text(i, tot + tot*0.02, f"{tot:.1f} J", ha="center", fontsize=9, fontweight="bold")

# Porcentaje TX dentro de la barra
for i, (et, etot) in enumerate(zip(E_tx, E_tot)):
    ax.text(i, et*0.5, f"{et/etot*100:.0f}%\nTX", ha="center", va="center",
            fontsize=8, color="white", fontweight="bold")

ax.set_xticks(x); ax.set_xticklabels(lbl)
ax.set_yscale("log")
ax.set_ylabel("Energía diaria [J/día]  (escala log)")
ax.set_title("Desglose de energía diaria por estado del nodo\n(308 paquetes/día · sin ventanas RX · LoRa raw)")
ax.legend()
plt.tight_layout()
save(fig, "G8_energy_breakdown")

# ══════════════════════════════════════════════════════════════════
# G9 — Balance solar: cosecha vs consumo por SF
# ══════════════════════════════════════════════════════════════════
# Panel: 5V/55mA = 275 mW, η=0.166, Hsun=5.5h
E_harvest = 275e-3 * 0.166 * 5.5 * 3600  # J/día ≈ 909 J

fig, ax = plt.subplots(figsize=(10, 5))
bars = ax.bar(lbl, E_tot, color=cm, width=0.55, label="Consumo diario (nodo)")
ax.axhline(E_harvest, color=GREEN, lw=2.5, ls="-",
           label=f"Cosecha solar (panel 275 mW) = {E_harvest:.0f} J/día")

for b, v in zip(bars, E_tot):
    ratio = E_harvest / v
    txt   = f"×{ratio:.0f}" if ratio >= 1 else f"÷{1/ratio:.0f}"
    col   = GREEN if ratio >= 1 else RED
    ax.text(b.get_x()+b.get_width()/2, max(v, E_harvest)*1.03,
            txt, ha="center", fontsize=10, fontweight="bold", color=col)

ax.set_yscale("log")
ax.set_ylabel("Energía diaria [J/día]  (escala log)")
ax.set_title("Balance energético solar vs consumo por SF\n(Boulder CO: 5.5 h pico solar/día)")
ax.legend(fontsize=9)
ax.set_ylim(0.5, E_harvest * 5)
plt.tight_layout()
save(fig, "G9_solar_balance")

# ══════════════════════════════════════════════════════════════════
# G10 — Comparación PDR: SF vs Heartbeat vs Nodos
# ══════════════════════════════════════════════════════════════════
fig, axes = plt.subplots(1, 3, figsize=(15, 5))
fig.suptitle("PDR — Comparación de los barridos principales\n(LoRa raw, ns-3.47, 1 GW)", fontsize=13)

# SF
ax = axes[0]
cmap_sf = plt.cm.RdYlGn_r(np.linspace(0.05, 0.95, len(sf_df)))
bars = ax.bar(sfs, sf_df["pdr"], color=cmap_sf, width=0.6)
for b, v in zip(bars, sf_df["pdr"]):
    ax.text(b.get_x()+b.get_width()/2, b.get_height()+0.5,
            f"{v:.1f}%", ha="center", fontsize=8, fontweight="bold")
ax.axhline(95, color="gray", ls="--", lw=1)
ax.set_title("Barrido SF\n(300 s, 500 nodos)"); ax.set_ylabel("PDR [%]"); ax.set_ylim(0, 108)

# Heartbeat
ax = axes[1]
cmap_hb = plt.cm.Blues(np.linspace(0.4, 0.9, len(hb_df)))
bars = ax.bar([f"{h}s" for h in hb_df["heartbeat"]], hb_df["pdr"], color=cmap_hb, width=0.6)
for b, v in zip(bars, hb_df["pdr"]):
    ax.text(b.get_x()+b.get_width()/2, b.get_height()+0.5,
            f"{v:.1f}%", ha="center", fontsize=8, fontweight="bold")
ax.axhline(95, color="gray", ls="--", lw=1)
ax.set_title("Barrido Heartbeat\n(SF7, 500 nodos)"); ax.set_ylim(0, 108)

# Nodos
ax = axes[2]
cmap_n = plt.cm.Greens(np.linspace(0.4, 0.9, len(n_df)))
bars = ax.bar(n_df["nodes"].astype(str), n_df["pdr"], color=cmap_n, width=0.6)
for b, v in zip(bars, n_df["pdr"]):
    ax.text(b.get_x()+b.get_width()/2, b.get_height()+0.5,
            f"{v:.1f}%", ha="center", fontsize=8, fontweight="bold")
ax.axhline(95, color="gray", ls="--", lw=1)
ax.set_title("Barrido Nodos\n(SF7, 300 s)"); ax.set_ylim(0, 108)

plt.tight_layout()
save(fig, "G10_pdr_comparison")

# ══════════════════════════════════════════════════════════════════
# G11 — Tabla resumen visual (coloreada por PDR)
# ══════════════════════════════════════════════════════════════════
df_tbl = df.sort_values(["sf", "gw", "heartbeat", "nodes"]).reset_index(drop=True)

fig, ax = plt.subplots(figsize=(14, 8))
ax.axis("off")

cols = ["Config", "SF", "GW", "HB[s]", "Nodos", "PDR%", "Colisión%",
        "J/día", "Vida nueva", "EOL 80%", "Año 5 (27%)"]
rows = []
for _, r in df_tbl.iterrows():
    rows.append([r["config"], int(r["sf"]), int(r["gw"]), int(r["heartbeat"]),
                 int(r["nodes"]), f"{r['pdr']:.1f}", f"{r['collision_rate']:.1f}",
                 f"{r['daily_rate_J']:.2f}", f"{r['lifetime_days']:.0f}",
                 f"{r['lifetime_eol_days']:.0f}", f"{r['lifetime_yr5_days']:.0f}"])

tbl = ax.table(cellText=rows, colLabels=cols, loc="center", cellLoc="center")
tbl.auto_set_font_size(False); tbl.set_fontsize(10); tbl.scale(1, 1.6)

# Colorear por PDR
for i, row in enumerate(rows):
    pdr_val = float(row[5])
    if   pdr_val >= 90: c = "#C8E6C9"
    elif pdr_val >= 70: c = "#FFF9C4"
    else:               c = "#FFCDD2"
    for j in range(len(cols)):
        tbl[i+1, j].set_facecolor(c)

for j in range(len(cols)):
    tbl[0, j].set_facecolor("#1565C0")
    tbl[0, j].set_text_props(color="white", fontweight="bold")

ax.set_title("Resumen de los 16 escenarios — LoRa Raw (ns-3.47)\n"
             "Verde: PDR ≥ 90%   Amarillo: 70–90%   Rojo: < 70%",
             fontsize=12, pad=20)
plt.tight_layout()
save(fig, "G11_summary_table")

# ══════════════════════════════════════════════════════════════════
# Resumen en consola
# ══════════════════════════════════════════════════════════════════
print(f"\n{'='*75}")
print(f"{'Config':<10} {'SF':>4} {'GW':>4} {'HB[s]':>7} {'Nodos':>6} "
      f"{'PDR%':>7} {'Col%':>7} {'J/día':>8} {'Vida[d]':>9}")
print("-"*75)
for _, r in df.sort_values(["sf","gw","heartbeat","nodes"]).iterrows():
    print(f"{r['config']:<10} {int(r['sf']):>4} {int(r['gw']):>4} "
          f"{int(r['heartbeat']):>7} {int(r['nodes']):>6} "
          f"{r['pdr']:>7.1f} {r['collision_rate']:>7.1f} "
          f"{r['daily_rate_J']:>8.2f} {r['lifetime_days']:>9.0f}")
print(f"{'='*75}")
print(f"\n11 gráficas guardadas en: {os.path.abspath(OUT)}/")
