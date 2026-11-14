#!/bin/bash
# run_raw_scenarios.sh
# Ejecutar desde la raíz de ns-3.47:
#   bash proyecto_lora_raw/codigo/run_raw_scenarios.sh
#
# Requiere compilar primero:
#   ./ns3 build scratch/lora-raw-cu-stadium
#
# Genera:
#   proyecto_lora_raw/resultados/summary.csv           (16 escenarios)
#   proyecto_lora_raw/resultados/summary_degradacion.csv (7 escenarios)
#   proyecto_lora_raw/resultados/energy_raw_*.csv      (energía por nodo)

BIN="./build/scratch/ns3.47-lora-raw-cu-stadium-debug"
OUT="proyecto_lora_raw/resultados"
mkdir -p "$OUT"

SIM=3600

# ── Función genérica de ejecución ──────────────────────────────────
run() {
    local label="$1" sf="$2" hb="$3" n="$4" days="${5:-0}"
    local log="$OUT/log_${label}.txt"
    echo "[START] $label  SF$sf  1GW  ${hb}s  ${n}n  día=${days}"
    "$BIN" --config="$label" --sf="$sf" \
           --heartbeat="$hb" --nNodes="$n" --simTime="$SIM" \
           --daysElapsed="$days" \
           2>/dev/null > "$log"
    [ -f "energy_raw_${label}.csv" ] && mv "energy_raw_${label}.csv" "$OUT/"
    echo "[DONE]  $label"
}

# ══════════════════════════════════════════════════════════════════
# Barrido 1: Spreading Factor (SF7–SF12)
# ══════════════════════════════════════════════════════════════════
SUMMARY="$OUT/summary.csv"
echo "config,sf,gw,heartbeat,nodes,sent,received,pdr,collision_rate,"\
"avg_energy_J,std_dev_J,daily_rate_J,lifetime_days,days_elapsed,capacity_pct" \
  > "$SUMMARY"

for sf in 7 8 9 10 11 12; do
    run "SF${sf}" "$sf" 300 500 &
done

# Barrido 2: Heartbeat
for hb in 60 150 600 1200; do run "HB${hb}" 7 "$hb" 500 & done

# Barrido 3: Nodos
for n in 100 250 750 1000; do run "N${n}" 7 300 "$n" & done

wait

# Consolida summary principal
for label in SF7 SF8 SF9 SF10 SF11 SF12 HB60 HB150 HB600 HB1200 N100 N250 N750 N1000; do
    grep "^SUMMARY," "$OUT/log_${label}.txt" 2>/dev/null \
      | sed 's/^SUMMARY,//' >> "$SUMMARY"
done

# ══════════════════════════════════════════════════════════════════
# Barrido 5: Degradación de batería (SF7, días 0–2190)
# ══════════════════════════════════════════════════════════════════
SUMMARY_DEG="$OUT/summary_degradacion.csv"
echo "config,sf,gw,heartbeat,nodes,sent,received,pdr,collision_rate,"\
"avg_energy_J,std_dev_J,daily_rate_J,lifetime_days,days_elapsed,capacity_pct" \
  > "$SUMMARY_DEG"

for days in 0 365 730 1095 1460 1825 2190; do
    run "D${days}" 7 300 500 "$days" &
done

wait

for days in 0 365 730 1095 1460 1825 2190; do
    grep "^SUMMARY," "$OUT/log_D${days}.txt" 2>/dev/null \
      | sed 's/^SUMMARY,//' >> "$SUMMARY_DEG"
done

# ══════════════════════════════════════════════════════════════════
echo ""
echo "=========================================="
echo " Todos los escenarios completados."
echo "=========================================="
echo " Resultados principales : $SUMMARY"
echo " Resultados degradación : $SUMMARY_DEG"
echo ""
echo " Gráficas principales:"
echo "   python3 proyecto_lora_raw/codigo/plot_raw_lora.py"
echo ""
echo " Gráficas de degradación:"
echo "   python3 proyecto_lora_raw/codigo/plot_degradation.py"
echo "=========================================="
