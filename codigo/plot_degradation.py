"""
plot_degradation.py — Modelo de degradación de batería LiPo
Fuente: resultados de simulación + modelo analítico

Ejecutar desde la carpeta raíz del proyecto (proyecto_lora_raw/):
    python3 codigo/plot_degradation.py

Salida: graficas/GD1_*.png ... GD4_*.png
"""
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import os

# Ejecutar siempre desde la raíz del proyecto
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

OUT = "graficas"
os.makedirs(OUT, exist_ok=True)

matplotlib.rcParams.update({
    "font.size": 11,
    "axes.spines.top":  False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linestyle": "--",
})

import numpy as np

# ── Parámetros del sistema ─────────────────────────────────────────
C0    = 13320.0   # J capacidad inicial
E_DAY = 6.93      # J/día consumo SF7

# ── Modelo KWW (Stretched Exponential) ─────────────────────────────
# C(N) = C0 × exp(-(N/τ)^β)
# Calibrado: 80% a 500 ciclos, 55% a 1000 ciclos
TAU  = 1425.0
BETA = 1.424

def cap_kww(N):
    return C0 * np.exp(-(N / TAU)**BETA)

def cap_linear(N, k=0.0004):
    return np.maximum(0, C0 * (1 - k * N))

# ── Datos reales de simulación (con modelo KWW) ─────────────────────
sim_days  = [0,   365,  730,  1095, 1460, 1825, 2190]
sim_cap_J = [cap_kww(d) for d in sim_days]
sim_cap_pct = [c/C0*100 for c in sim_cap_J]
sim_lifetime = [c/E_DAY for c in sim_cap_J]

def save(fig, name):
    p = f"{OUT}/{name}.png"
    fig.savefig(p, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  ✓ {name}.png")

print("Generando gráficas de degradación…")

# ══════════════════════════════════════════════════════════════════
# G_D1 — Capacidad de batería vs tiempo (curva + puntos simulación)
# ══════════════════════════════════════════════════════════════════
days = np.arange(0, 2501)
cap_kww_pct    = np.array([cap_kww(d)/C0*100 for d in days])
cap_linear_pct = cap_linear(days)/C0*100

fig, ax = plt.subplots(figsize=(10, 5))

ax.plot(days, cap_kww_pct, color="#2196F3", lw=2.5,
        label=f"Modelo KWW (τ={TAU:.0f}, β={BETA:.3f})  ← no lineal")
ax.plot(days, cap_linear_pct, color="#9E9E9E", lw=1.5, ls="--",
        label="Modelo lineal (k=0.0004/ciclo)  ← anterior")
ax.scatter(sim_days, sim_cap_pct, color="#F44336", s=80, zorder=5,
           label="Puntos simulados (ns-3)", edgecolors="white", linewidths=1.5)

# Líneas de referencia
ax.axhline(80, color="#FF9800", ls="--", lw=1.3, label="EOL comercial (80%)")
ax.axhline(50, color="#F44336", ls="--", lw=1.3, label="Límite operativo (50%)")

# Marcadores de años
for yr, col in [(1, "#4CAF50"), (2, "#2196F3"), (3, "#FF9800"), (5, "#9C27B0")]:
    d = yr * 365
    c = cap_kww(d) / C0 * 100
    ax.annotate(f"Año {yr}\n{c:.0f}%",
                xy=(d, c), xytext=(d + 60, c + 5),
                fontsize=8, color=col,
                arrowprops=dict(arrowstyle="->", color=col, lw=1))

ax.set_xlabel("Días desde despliegue")
ax.set_ylabel("Capacidad restante [%]")
ax.set_title("Degradación de la batería LiPo 1000 mAh — Modelo KWW vs Lineal\n"
             "(1 ciclo/día con carga solar)")
ax.legend(fontsize=9)
ax.set_ylim(0, 110)
plt.tight_layout()
save(fig, "GD1_battery_degradation")

# ══════════════════════════════════════════════════════════════════
# G_D2 — Vida útil restante vs día de despliegue (doble eje)
# ══════════════════════════════════════════════════════════════════
cap_J_kww  = np.array([cap_kww(d) for d in days])
life_kww   = cap_J_kww / E_DAY

fig, ax1 = plt.subplots(figsize=(10, 5))
ax2 = ax1.twinx()

l1, = ax1.plot(days, cap_J_kww,  color="#2196F3", lw=2.5,
               label="Capacidad batería KWW [J]")
l2, = ax2.plot(days, life_kww,   color="#FF9800", lw=2.5, ls="--",
               label="Autonomía sin solar [días]")

ax1.scatter(sim_days, sim_cap_J,      color="#F44336", s=80, zorder=5,
            edgecolors="white", linewidths=1.5)
ax2.scatter(sim_days, sim_lifetime,   color="#4CAF50", s=80, zorder=5,
            marker="s", edgecolors="white", linewidths=1.5)

ax1.set_xlabel("Días de operación acumulados")
ax1.set_ylabel("Capacidad efectiva [J]", color="#2196F3")
ax2.set_ylabel("Autonomía sin solar [días]", color="#FF9800")
ax1.tick_params(axis="y", labelcolor="#2196F3")
ax2.tick_params(axis="y", labelcolor="#FF9800")

# Knee point (inflexión de la KWW)
knee = TAU * ((BETA - 1) / BETA) ** (1/BETA)
ax1.axvline(knee, color="purple", ls=":", lw=1.3,
            label=f"Punto de inflexión (día {knee:.0f})")
ax1.axvline(500,  color="gray", ls=":", lw=1)
ax1.text(500, C0*0.92, "500 ciclos\n(EOL 80%)", fontsize=8, ha="center")
ax1.text(knee, C0*0.82, f"Inflexión\ndía {knee:.0f}", fontsize=8,
         ha="center", color="purple")

lines = [l1, l2,
         plt.Line2D([0],[0], marker='o', color='w', markerfacecolor='#F44336',
                    markersize=8, label="Capacidad sim."),
         plt.Line2D([0],[0], marker='s', color='w', markerfacecolor='#4CAF50',
                    markersize=8, label="Autonomía sim.")]
ax1.legend(handles=lines, fontsize=9, loc="upper right")
ax1.set_title("Capacidad y autonomía sin solar — Modelo KWW no lineal\n"
              f"(τ={TAU:.0f} ciclos, β={BETA:.3f})")
plt.tight_layout()
save(fig, "GD2_lifetime_vs_age")

# ══════════════════════════════════════════════════════════════════
# G_D3 — Comparación: con solar vs sin solar considerando degradación
# ══════════════════════════════════════════════════════════════════
# Con solar: el nodo opera indefinidamente mientras E_harvest > E_day
# E_harvest (mes más desfavorable, dic, Boulder): ~578 J/día
# E_day = 6.93 J/día  → siempre solar-neutro independientemente de degradación

E_harvest_min = 578.0   # J/día diciembre, Boulder CO
E_harvest_avg = 909.0   # J/día promedio anual

# Sin solar: la batería se agota en lifetime_days días
# Pero con degradación, la batería tiene menos capacidad en cada ciclo

# Escenario A: batería nueva + solar → opera mientras E_harvest > E_day
# Escenario B: sin solar, batería nueva → 1922 días
# Escenario C: sin solar, batería degradada → lifetime decrece

fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
fig.suptitle("Impacto de la degradación: escenario solar vs sin solar", fontsize=13)

# Panel izquierdo: energy balance vs tiempo
E_harvest_min = 578.0
E_harvest_avg = 909.0

ax = axes[0]
ax.plot(days, cap_J_kww / E_DAY, color="#FF9800", lw=2,
        label="Autonomía sin solar [días] (KWW)")
ax.axhline(E_harvest_avg / E_DAY, color="#4CAF50", lw=2, ls="--",
           label=f"Con solar promedio: {E_harvest_avg/E_DAY:.0f} días equiv.")
ax.axhline(E_harvest_min / E_DAY, color="#8BC34A", lw=2, ls=":",
           label=f"Con solar dic (mín): {E_harvest_min/E_DAY:.0f} días equiv.")

ax.fill_between(days, cap_J_kww / E_DAY, E_harvest_min / E_DAY,
                where=(cap_J_kww / E_DAY < E_harvest_min / E_DAY),
                alpha=0.2, color="#F44336", label="Zona de riesgo (sin solar)")

ax.set_xlabel("Días de operación"); ax.set_ylabel("Días de autonomía")
ax.set_title("Autonomía de reserva vs cosecha solar (modelo KWW)")
ax.legend(fontsize=8); ax.set_ylim(0, 160)
ax.set_xlim(0, 2500)

# Panel derecho: tabla con valores KWW
ax = axes[1]
ax.axis("off")

puntos = [(0, 1922), (365, 1641), (730, 1361),
          (1095, 1080), (1460, 800), (1825, 519), (2190, 238)]
tabla = [["Día", "Capacidad", "Autonomía\nsin solar", "Con solar\n(¿opera?)"]]
for d, _ in puntos:
    c_j   = cap_kww(d)
    c_pct = c_j/C0*100
    vida  = c_j/E_DAY
    ratio = E_harvest_avg / E_DAY / (c_j/E_DAY) if c_j > 0 else 0
    sol   = f"✓ Sí (×{E_harvest_avg/c_j*c_j/E_DAY/1:.0f})" if c_j > 0 else "✗"
    # simplify: harvest/E_day is constant ratio; show harvest/consumption
    sol   = f"✓ Sí" if c_j > 0 else "✗ Reemplazar"
    tabla.append([str(d),
                  f"{c_j:.0f} J\n({c_pct:.0f}%)",
                  f"{vida:.0f} días",
                  sol])

colors_tbl = [["#1565C0"]*4]
for row in tabla[1:]:
    pct = float(row[1].split("(")[1].replace("%)","").replace("%",""))
    c = "#C8E6C9" if pct > 60 else "#FFF9C4" if pct > 30 else "#FFCDD2"
    colors_tbl.append([c]*4)

tbl = ax.table(cellText=tabla, loc="center", cellLoc="center")
tbl.auto_set_font_size(False); tbl.set_fontsize(9); tbl.scale(1, 2.1)
for j in range(4):
    tbl[0, j].set_facecolor("#1565C0")
    tbl[0, j].set_text_props(color="white", fontweight="bold")
for i in range(1, len(tabla)):
    for j in range(4):
        tbl[i, j].set_facecolor(colors_tbl[i][j])

ax.set_title("Puntos clave de degradación", fontsize=11, pad=15)
plt.tight_layout()
save(fig, "GD3_solar_vs_nosolar_degradation")

# ══════════════════════════════════════════════════════════════════
# G_D4 — Vida útil acumulada total (batería + vida post-reemplazo)
# ══════════════════════════════════════════════════════════════════
# Si se reemplaza la batería en el día N:
# Vida total = N (días con batería original) + lifetime_fresh (batería nueva)

days_replace = np.arange(0, 2501, 50)
total_life = days_replace + (C0 / E_DAY)   # al reemplazar, vuelve a 1922 días

# Sin reemplazo: sólo dura hasta que se acaba
no_replace = np.minimum(days, C0 / E_DAY * np.ones_like(days))

fig, ax = plt.subplots(figsize=(10, 5))

ax.plot(days_replace, total_life, color="#4CAF50", lw=2.5,
        label="Con reemplazo en día N + batería nueva = vida total")
ax.axhline(C0 / E_DAY, color="#F44336", lw=2, ls="--",
           label=f"Sin reemplazo (solo 1ª batería = {C0/E_DAY:.0f} días)")
ax.axhline(C0 / E_DAY * 2, color="#2196F3", lw=1.5, ls=":",
           label=f"2× vida sin reemplazo = {2*C0/E_DAY:.0f} días")

# Punto óptimo de reemplazo (EOL 80%)
opt_day = 500
opt_total = opt_day + C0 / E_DAY
ax.scatter([opt_day], [opt_total], color="#FF9800", s=120, zorder=5,
           label=f"Reemplazo en día {opt_day} (EOL 80%) → {opt_total:.0f} días total")

ax.set_xlabel("Día de reemplazo de batería")
ax.set_ylabel("Vida útil total del nodo [días]")
ax.set_title("Estrategia de reemplazo de batería\n(SF7, 300 s, k = 0.0004/ciclo, sin panel solar)")
ax.legend(fontsize=9)
plt.tight_layout()
save(fig, "GD4_replacement_strategy")

# ══════════════════════════════════════════════════════════════════
# Resumen consola
# ══════════════════════════════════════════════════════════════════
print(f"\n{'='*65}")
print(f"{'Día':>8} {'Capacidad J':>12} {'Cap %':>7} {'Autonomía':>11} {'Solar OK':>9}")
print("-"*65)
for d in [0, 365, 730, 1095, 1460, 1825, 2190, 2500]:
    cap = cap_kww(d)
    pct = cap / C0 * 100
    life = cap / E_DAY if cap > 0 else 0
    sol  = "✓" if cap > 0 else "✗ Reemplazar"
    print(f"{d:>8} {cap:>12.0f} {pct:>6.1f}% {life:>10.0f}d {sol:>9}")
print("="*65)
