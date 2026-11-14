"""
add_degradation_columns.py
Agrega columnas de vida útil corregida por degradación al summary.csv.

La tasa de consumo (daily_rate_J) es independiente de la batería,
por lo que se puede calcular analíticamente sin re-simular.

Modelo: C(N) = C0 * (1 - k*N),  k = 0.0004/ciclo
Vida útil en punto X = C(N_X) / daily_rate_J

Columnas añadidas:
  lifetime_eol_days    → batería al EOL comercial (500 ciclos, 80%)
  lifetime_yr1_days    → batería con 1 año de uso   (365 ciclos, 85.4%)
  lifetime_yr3_days    → batería con 3 años de uso  (1095 ciclos, 56.2%)
  lifetime_yr5_days    → batería con 5 años de uso  (1825 ciclos, 27%)
  backup_90d_threshold → día en que la reserva cae por debajo de 90 días

Ejecutar desde proyecto_lora_raw/:
    python3 codigo/add_degradation_columns.py
"""

import os, sys
import pandas as pd
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

import numpy as np
from scipy.optimize import brentq

C0   = 13320.0
TAU  = 1425.0   # parámetro escala KWW
BETA = 1.424    # parámetro forma KWW (β > 1 → degradación acelerada)

def capacity(N):
    """Modelo KWW: C(N) = C0 × exp(-(N/τ)^β)"""
    return C0 * np.exp(-( N / TAU)**BETA)

def lifetime_at(N, daily_rate):
    return capacity(N) / daily_rate if daily_rate > 0 else 0

def backup_threshold_day(daily_rate, min_backup_days=90):
    """Día en que C(N)/daily_rate cae por debajo de min_backup_days."""
    target = min_backup_days * daily_rate
    if capacity(0) < target:
        return 0
    try:
        return brentq(lambda N: capacity(N) - target, 0, 5000)
    except ValueError:
        return 5000

# ── Procesar summary principal ──────────────────────────────────────
df = pd.read_csv("resultados/summary.csv")

df["lifetime_eol_days"]   = df["daily_rate_J"].apply(lambda r: round(lifetime_at(500,  r)))
df["lifetime_yr1_days"]   = df["daily_rate_J"].apply(lambda r: round(lifetime_at(365,  r)))
df["lifetime_yr3_days"]   = df["daily_rate_J"].apply(lambda r: round(lifetime_at(1095, r)))
df["lifetime_yr5_days"]   = df["daily_rate_J"].apply(lambda r: round(lifetime_at(1825, r)))
df["backup_90d_threshold"]= df["daily_rate_J"].apply(lambda r: round(backup_threshold_day(r, 90)))

df.to_csv("resultados/summary.csv", index=False)
print("✓ summary.csv actualizado")

# ── Tabla de verificación ───────────────────────────────────────────
print(f"\n{'Config':<10} {'J/día':>8} {'Fresh':>8} {'EOL(80%)':>10} "
      f"{'Yr1(85%)':>10} {'Yr3(56%)':>10} {'Yr5(27%)':>10} "
      f"{'<90d backup':>13}")
print("-"*85)
df_s = df.sort_values(["sf","gw","heartbeat","nodes"])
for _, r in df_s.iterrows():
    print(f"{r['config']:<10} {r['daily_rate_J']:>8.2f} "
          f"{r['lifetime_days']:>8.0f} "
          f"{r['lifetime_eol_days']:>10.0f} "
          f"{r['lifetime_yr1_days']:>10.0f} "
          f"{r['lifetime_yr3_days']:>10.0f} "
          f"{r['lifetime_yr5_days']:>10.0f} "
          f"{r['backup_90d_threshold']:>13.0f}")
print("-"*85)
print("(días = reserva sin solar desde ese punto de degradación)")
print("\nNota: PDR y tasa de colisión son idénticos en todos los puntos de degradación.")
