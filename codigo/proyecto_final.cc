/*
 * lora-raw-cu-stadium.cc
 *
 * Raw LoRa simulation — CU Stadium vehicle counting
 * NO LoRaWAN stack: solo PHY LoRa pura
 *   - Sin MAC headers (MHDR, FHDR, MIC)
 *   - Sin ventanas RX1/RX2
 *   - Sin OTAA/ABP
 *   - Sin network server / forwarder
 *   - Canal modelado con log-distance + capture effect (ΔSNR > 6 dB)
 *   - Energía: BasicEnergySource con transiciones TX/Sleep/Standby
 *
 * Módulos usados: core, network, mobility, propagation, energy
 * Compatible con ns-3.47 sin módulos externos.
 *
 * Uso:
 *   ./ns3 build scratch/lora-raw-cu-stadium
 *   ./build/scratch/ns3.47-lora-raw-cu-stadium-debug \
 *       --sf=7 --nNodes=500 --nGateways=1 --heartbeat=300 \
 *       --simTime=3600 --config=A
 */

#include "ns3/basic-energy-source-helper.h"
#include "ns3/basic-energy-source.h"
#include "ns3/command-line.h"
#include "ns3/constant-position-mobility-model.h"
#include "ns3/core-module.h"
#include "ns3/propagation-loss-model.h"
#include "ns3/mobility-helper.h"
#include "ns3/node-container.h"
#include "ns3/simulator.h"
#include "ns3/position-allocator.h"

#include <algorithm>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <vector>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("LoRaRawCUStadium");

// ═══════════════════════════════════════════════════════════════════
// Modelo de airtime LoRa raw (sin headers MAC)
// ═══════════════════════════════════════════════════════════════════
double loraAirtime(uint8_t sf, double bwHz, uint8_t crDenom, uint32_t payloadBytes)
{
    double Tsym    = std::pow(2.0, sf) / bwHz;
    double npayload = 8.0 * payloadBytes - 4.0 * sf + 28.0 + 16.0;
    double nsym_pay = 8.0 + std::max(0.0,
                        std::ceil(npayload / (4.0 * sf)) * (double)(4 + crDenom));
    return (12.25 + nsym_pay) * Tsym;
}

// Sensibilidad del receptor LoRa (SX1262) en dBm
double loraSensitivity(uint8_t sf)
{
    // SF7..SF12 → índices 0..5
    const double sens[] = {-123.0, -126.0, -129.0, -132.0, -134.5, -137.0};
    int idx = std::max(0, std::min(5, (int)sf - 7));
    return sens[idx];
}

// ═══════════════════════════════════════════════════════════════════
// Registro de paquetes en vuelo (para detección de colisiones)
// ═══════════════════════════════════════════════════════════════════
struct InFlightPkt
{
    uint32_t nodeId;
    uint32_t pktId;
    double   rxPowerDbm;   // potencia recibida en el gateway
    double   txStartS;     // tiempo de inicio (s)
    double   txEndS;       // tiempo de fin    (s)
    uint8_t  sf;
    bool     outcome;      // true = received, false = lost
};

static uint32_t            g_pktCounter  = 0;
static uint32_t            g_sent        = 0;
static uint32_t            g_received    = 0;
static uint32_t            g_collided    = 0;
static uint32_t            g_underSens   = 0;

static std::vector<InFlightPkt> g_completed;  // paquetes ya terminados

// ═══════════════════════════════════════════════════════════════════
// Parámetros globales de la simulación
// ═══════════════════════════════════════════════════════════════════
static uint8_t  G_SF          = 7;
static double   G_BW          = 125e3;
static uint8_t  G_CR          = 1;       // 4/5 → denominador extra = 1
static double   G_TXPOW_DBM   = 14.0;
static uint32_t G_PAYLOAD     = 20;      // bytes (sin MAC header)
static double   G_AIRTIME_S   = 0.0;     // calculado en main()

// Energía: SX1262 + STM32L0
static const double G_TX_A        = 0.090;     // 90 mA TX
static const double G_SLEEP_A     = 0.0000035; // 3.5 µA sleep
static const double G_STANDBY_A   = 0.00446;   // 5 mA MCU @ 3.3V → 4.46 mA @ 3.7V
static const double G_BATTERY_V   = 3.7;
static const double G_BATTERY_J   = 13320.0;   // capacidad nueva: 1000 mAh × 3.7 V

// ─────────────────────────────────────────────────────────────────
// Modelo de degradación de batería LiPo — KWW (stretched exponential)
//
//   C(N) = C0 × exp(-(N / τ)^β)
//   τ = 1425 ciclos,  β = 1.424
//
// Calibrado para:
//   N = 500  → C ≈ 80 % C0  (EOL comercial)
//   N = 1000 → C ≈ 55 % C0  (límite operativo)
//
// β > 1 produce degradación acelerada (efecto "knee") realista en LiPo.
// Parámetro --daysElapsed arranca la simulación con batería envejecida.
// ─────────────────────────────────────────────────────────────────
double degradedCapacity(double daysElapsed)
{
    const double TAU  = 1425.0;
    const double BETA = 1.424;
    double factor = std::exp(-std::pow(daysElapsed / TAU, BETA));
    return G_BATTERY_J * factor;
}

// Modelo de canal
static Ptr<LogDistancePropagationLossModel> g_lossModel;
static NodeContainer g_endDevices;
static NodeContainer g_gateways;

// Energía por nodo (acumulada durante la simulación)
static std::vector<double> g_txEnergyJ;     // J gastados en TX
static std::vector<double> g_sleepEnergyJ;  // J gastados en sleep (estimado)
static std::vector<Time>   g_lastActivated; // último momento activo

// ═══════════════════════════════════════════════════════════════════
// Calcula la potencia recibida en el gateway i desde el nodo j
// ═══════════════════════════════════════════════════════════════════
double rxPowerDbm(uint32_t nodeIdx, uint32_t gwIdx)
{
    Ptr<MobilityModel> txMob =
        g_endDevices.Get(nodeIdx)->GetObject<MobilityModel>();
    Ptr<MobilityModel> rxMob =
        g_gateways.Get(gwIdx)->GetObject<MobilityModel>();

    // PropagationLossModel devuelve Prx dBm dado Ptx dBm
    return g_lossModel->CalcRxPower(G_TXPOW_DBM, txMob, rxMob);
}

// ═══════════════════════════════════════════════════════════════════
// Intento de recepción en el gateway al terminar la transmisión
// ═══════════════════════════════════════════════════════════════════
void onPacketEnd(uint32_t nodeIdx, uint32_t pktId, double txStartS,
                 double rxPow, uint8_t sf)
{
    double txEndS = txStartS + G_AIRTIME_S;
    double sens   = loraSensitivity(sf);

    bool received = false;

    if (rxPow < sens)
    {
        // Bajo sensibilidad: no decodificable
        g_underSens++;
    }
    else
    {
        // Comprobar colisiones con paquetes en vuelo al mismo tiempo y mismo SF
        bool collision = false;
        for (auto& prev : g_completed)
        {
            if (prev.sf != sf) continue;                      // SFs distintos son ortogonales
            if (prev.txEndS   < txStartS) continue;           // prev ya terminó antes
            if (prev.txStartS > txEndS)   continue;           // prev empieza después
            // Solapamiento temporal → colisión
            // Capture effect: si Δ > 6 dB, el más fuerte sobrevive
            double delta = rxPow - prev.rxPowerDbm;
            if (delta > 6.0)
            {
                // Este paquete destruye al anterior
                prev.outcome = false;
            }
            else if (delta < -6.0)
            {
                // El anterior destruye a este
                collision = true;
            }
            else
            {
                // Ambos se destruyen mutuamente
                prev.outcome = false;
                collision    = true;
            }
        }
        received = !collision;
        if (collision) g_collided++;
    }

    if (received) g_received++;
    g_completed.push_back({nodeIdx, pktId, rxPow, txStartS, txEndS, sf, received});
}

// ═══════════════════════════════════════════════════════════════════
// Evento de transmisión de un paquete raw LoRa
// ═══════════════════════════════════════════════════════════════════
void sendPacket(uint32_t nodeIdx, uint32_t gwIdx)
{
    double now     = Simulator::Now().GetSeconds();
    uint32_t pktId = ++g_pktCounter;
    g_sent++;

    // Potencia recibida en el gateway más cercano
    double rp = rxPowerDbm(nodeIdx, gwIdx);

    // Acumular energía de TX para este nodo
    g_txEnergyJ[nodeIdx] += G_TX_A * G_BATTERY_V * G_AIRTIME_S;

    // Registrar fin de transmisión para colisión
    Simulator::Schedule(Seconds(G_AIRTIME_S),
                        &onPacketEnd, nodeIdx, pktId, now, rp, G_SF);
}

// ═══════════════════════════════════════════════════════════════════
// Planificador periódico de paquetes por nodo
// ═══════════════════════════════════════════════════════════════════
void scheduleHeartbeat(uint32_t nodeIdx, uint32_t gwIdx,
                       double period, double stopTime)
{
    if (Simulator::Now().GetSeconds() >= stopTime) return;
    sendPacket(nodeIdx, gwIdx);
    Simulator::Schedule(Seconds(period),
                        &scheduleHeartbeat,
                        nodeIdx, gwIdx, period, stopTime);
}

void scheduleEvent(uint32_t nodeIdx, uint32_t gwIdx,
                   double meanInterval, double stopTime)
{
    if (Simulator::Now().GetSeconds() >= stopTime) return;
    sendPacket(nodeIdx, gwIdx);
    // Próximo evento: tiempo exponencial
    Ptr<ExponentialRandomVariable> rv = CreateObject<ExponentialRandomVariable>();
    rv->SetAttribute("Mean", DoubleValue(meanInterval));
    double next = rv->GetValue();
    Simulator::Schedule(Seconds(next),
                        &scheduleEvent,
                        nodeIdx, gwIdx, meanInterval, stopTime);
}

// ═══════════════════════════════════════════════════════════════════
// main
// ═══════════════════════════════════════════════════════════════════
int main(int argc, char* argv[])
{
    uint32_t    nNodes          = 500;
    double      simTimeSec      = 3600.0;
    double      areaRadius      = 800.0;
    uint32_t    sf              = 7;
    uint32_t    heartbeatPeriod = 300;
    std::string config          = "A";
    double      daysElapsed     = 0.0;   // días transcurridos desde despliegue

    CommandLine cmd(__FILE__);
    cmd.AddValue("nNodes",      "Número de nodos sensor",             nNodes);
    cmd.AddValue("simTime",     "Tiempo de simulación [s]",           simTimeSec);
    cmd.AddValue("sf",          "Spreading factor (7-12)",            sf);
    cmd.AddValue("heartbeat",   "Intervalo heartbeat [s]",            heartbeatPeriod);
    cmd.AddValue("config",      "Etiqueta de configuración",          config);
    cmd.AddValue("daysElapsed", "Días desde despliegue (degradación)", daysElapsed);
    cmd.Parse(argc, argv);

    G_SF = static_cast<uint8_t>(sf);
    G_AIRTIME_S = loraAirtime(G_SF, G_BW, G_CR, G_PAYLOAD);

    // Capacidad efectiva de la batería (modelo KWW no lineal)
    double effectiveBatteryJ = degradedCapacity(daysElapsed);
    double degradePct = (1.0 - effectiveBatteryJ / G_BATTERY_J) * 100.0;

    g_txEnergyJ.assign(nNodes, 0.0);
    g_sleepEnergyJ.assign(nNodes, 0.0);

    // ── Canal: log-distance, exp 2.7, L0 = 7.7 dB @ 1 m ───────────
    g_lossModel = CreateObject<LogDistancePropagationLossModel>();
    g_lossModel->SetPathLossExponent(2.7);
    g_lossModel->SetReference(1.0, 7.7);

    // ── Nodos sensor ────────────────────────────────────────────────
    g_endDevices.Create(nNodes);

    MobilityHelper nodeMobility;
    Ptr<UniformDiscPositionAllocator> discAlloc =
        CreateObject<UniformDiscPositionAllocator>();
    discAlloc->SetX(0.0); discAlloc->SetY(0.0); discAlloc->SetRho(areaRadius);
    nodeMobility.SetPositionAllocator(discAlloc);
    nodeMobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    nodeMobility.Install(g_endDevices);

    for (uint32_t i = 0; i < nNodes; i++)
    {
        Ptr<MobilityModel> mob = g_endDevices.Get(i)->GetObject<MobilityModel>();
        Vector pos = mob->GetPosition(); pos.z = 0.0; mob->SetPosition(pos);
    }

    // ── Gateway (único, centro del área) ────────────────────────────
    g_gateways.Create(1);
    Ptr<ListPositionAllocator> gwAlloc = CreateObject<ListPositionAllocator>();
    gwAlloc->Add(Vector(0.0, 0.0, 15.0));

    MobilityHelper gwMobility;
    gwMobility.SetPositionAllocator(gwAlloc);
    gwMobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
    gwMobility.Install(g_gateways);

    // ── Aplicaciones: heartbeat + eventos raw ──────────────────────
    Ptr<UniformRandomVariable> startRv = CreateObject<UniformRandomVariable>();
    startRv->SetAttribute("Min", DoubleValue(0.0));
    startRv->SetAttribute("Max", DoubleValue((double)heartbeatPeriod));

    double meanEventInterval = 86400.0 / 20.0;  // ~20 eventos/día

    for (uint32_t i = 0; i < nNodes; i++)
    {
        double offset = startRv->GetValue();
        // Heartbeat
        Simulator::Schedule(Seconds(offset),
                            &scheduleHeartbeat,
                            i, 0u, (double)heartbeatPeriod, simTimeSec);
        // Eventos aleatorios
        Ptr<ExponentialRandomVariable> evRv = CreateObject<ExponentialRandomVariable>();
        evRv->SetAttribute("Mean", DoubleValue(meanEventInterval));
        Simulator::Schedule(Seconds(evRv->GetValue()),
                            &scheduleEvent,
                            i, 0u, meanEventInterval, simTimeSec);
    }

    // ── Modelo de energía (BasicEnergySource) ──────────────────────
    BasicEnergySourceHelper srcHelper;
    srcHelper.Set("BasicEnergySourceInitialEnergyJ", DoubleValue(effectiveBatteryJ));
    srcHelper.Set("BasicEnergySupplyVoltageV",        DoubleValue(G_BATTERY_V));
    ns3::energy::EnergySourceContainer sources = srcHelper.Install(g_endDevices);

    // ── Ejecutar simulación ─────────────────────────────────────────
    Simulator::Stop(Seconds(simTimeSec));
    Simulator::Run();

    // ── Calcular energía de sleep estimada ─────────────────────────
    // Sleep energy = (simTime - t_TX_total) × P_sleep
    // TX total por nodo = txEnergyJ[i] / (G_TX_A * G_BATTERY_V)
    for (uint32_t i = 0; i < nNodes; i++)
    {
        double tTx   = g_txEnergyJ[i] / (G_TX_A * G_BATTERY_V);
        double tSleep = simTimeSec - tTx;
        g_sleepEnergyJ[i] = G_SLEEP_A * G_BATTERY_V * tSleep;
    }

    // ── Estadísticas de energía ────────────────────────────────────
    double totalConsumed = 0.0, minConsumed = 1e12, maxConsumed = 0.0;
    std::vector<double> energyVec(nNodes);
    uint32_t deadNodes = 0;

    for (uint32_t i = 0; i < nNodes; i++)
    {
        double consumed    = g_txEnergyJ[i] + g_sleepEnergyJ[i];
        energyVec[i]       = consumed;
        totalConsumed     += consumed;
        minConsumed        = std::min(minConsumed, consumed);
        maxConsumed        = std::max(maxConsumed, consumed);
        if (consumed >= effectiveBatteryJ) deadNodes++;
    }

    double avgConsumed  = totalConsumed / nNodes;
    double dailyRate    = avgConsumed / (simTimeSec / 86400.0);
    double lifetimeDays = effectiveBatteryJ / dailyRate;

    double variance = 0.0;
    for (auto& e : energyVec)
        variance += (e - avgConsumed) * (e - avgConsumed);
    double stdDev = std::sqrt(variance / nNodes);

    Simulator::Destroy();

    // ── Recalcular colisiones después de Destroy ──────────────────
    // (los outcomes ya están en g_completed, resultado final)
    uint32_t finalReceived = 0;
    for (auto& p : g_completed)
        if (p.outcome) finalReceived++;

    double pdr           = (g_sent > 0) ? finalReceived * 100.0 / g_sent : 0.0;
    double collisionRate = (g_sent > 0) ? g_collided    * 100.0 / g_sent : 0.0;
    double underSensRate = (g_sent > 0) ? g_underSens   * 100.0 / g_sent : 0.0;

    // ── Imprimir resultados ─────────────────────────────────────────
    std::cout << "\n============================================================\n"
              << "  LoRa RAW — Config " << config
              << "  |  SF"  << (int)G_SF
              << "  |  1 GW"
              << "  |  "    << heartbeatPeriod << " s heartbeat"
              << "  |  "    << nNodes << " nodos\n"
              << "  Airtime: " << std::fixed << std::setprecision(1)
              << G_AIRTIME_S * 1000.0 << " ms"
              << "  |  Sensibilidad: " << loraSensitivity(G_SF) << " dBm\n"
              << "  Batería: " << std::setprecision(1) << effectiveBatteryJ << " J"
              << "  (" << std::setprecision(1) << (100.0 - degradePct) << "% capacidad"
              << "  |  día " << (int)daysElapsed << " de vida)\n"
              << "============================================================\n\n";

    std::cout << "--- Estadísticas de Paquetes (Raw LoRa PHY) ---\n"
              << "Paquetes enviados     : " << g_sent         << "\n"
              << "Paquetes recibidos    : " << finalReceived  << "\n"
              << "PDR                   : " << std::fixed << std::setprecision(2)
                                            << pdr  << " %\n"
              << "Tasa de colisión      : " << collisionRate  << " %\n"
              << "Bajo sensibilidad     : " << underSensRate  << " %\n\n";

    std::cout << "--- Estadísticas de Energía (por nodo, " << simTimeSec << " s) ---\n"
              << std::fixed << std::setprecision(5)
              << "Avg consumido/nodo    : " << avgConsumed   << " J\n"
              << "Desv. estándar        : " << stdDev        << " J\n"
              << "Min / Max             : " << minConsumed
              << " / " << maxConsumed << " J\n"
              << "Tasa diaria estimada  : " << dailyRate     << " J/día\n"
              << "Vida útil estimada    : " << std::setprecision(1)
                                            << lifetimeDays  << " días\n"
              << "Nodos agotados        : " << deadNodes     << "\n"
              << "============================================================\n\n";

    // ── Línea resumen CSV ──────────────────────────────────────────
    std::cout << std::fixed << std::setprecision(4)
              << "SUMMARY,"
              << config         << ","
              << (int)G_SF      << ","
              << 1              << ","
              << heartbeatPeriod << ","
              << nNodes         << ","
              << g_sent         << ","
              << finalReceived  << ","
              << pdr            << ","
              << collisionRate  << ","
              << avgConsumed    << ","
              << stdDev         << ","
              << dailyRate      << ","
              << std::setprecision(1)
              << lifetimeDays   << ","
              << (int)daysElapsed << ","
              << std::setprecision(2)
              << (100.0 - degradePct) << "\n";

    // ── CSV por nodo ───────────────────────────────────────────────
    std::string csvName = "energy_raw_" + config + ".csv";
    std::ofstream csv(csvName);
    csv << "node_id,tx_energy_J,sleep_energy_J,total_energy_J\n";
    for (uint32_t i = 0; i < nNodes; i++)
        csv << i << "," << g_txEnergyJ[i] << ","
            << g_sleepEnergyJ[i] << ","
            << energyVec[i] << "\n";
    csv.close();
    std::cout << "CSV por nodo: " << csvName << "\n\n";

    return 0;
}
