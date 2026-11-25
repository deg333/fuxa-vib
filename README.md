# FUXA Vibration & Energy Monitor (OPC UA)

Servo-axis vibration monitor (up to 5 axes) + energy monitor and manual load shedding for 7 AC units.

| File | What it is |
|---|---|
| `vibration-monitor.fuxap` | The FUXA project (import this) |
| `build_project.py` | Generator for the project: edit thresholds / layout, re-run `python3 build_project.py` |
| `sim/server.js` | OPC UA simulator: virtual master axis + 5 follower servo axes with adjustable mechanisms |

## Run it

```bash
# 1. simulator (OPC UA on opc.tcp://localhost:4840/UA/VibrationSim)
cd sim && npm install && npm start

# 2. FUXA (needs the OPC UA plugin: `npm i node-opcua` next to FUXA if it says "plugin is missing")
npm i -g @frangoteam/fuxa && fuxa            # UI on http://localhost:1881
```

In the FUXA editor: **menu ▸ Project ▸ Open/Import** and pick `vibration-monitor.fuxap`, then open **Home**.
If FUXA runs somewhere else than the simulator, change the device address in *Connections ▸ VibSim*
(or `OPCUA_URL=opc.tcp://host:4840/UA/VibrationSim python3 build_project.py`).

## Screens
* **Energy** – KPI tiles (total kW, kWh since start, units running, power shed), live + history trends (power per
  unit, total power) and one card per AC unit (power, current, power factor, energy, room temp, setpoint, rated kW,
  running light).
* **Load shedding** – one row per AC unit with a **switch** (ON / SHED), a **state light** (green = running,
  red = shed/off, driven by the unit's real `Running` state, not the switch), live power / room temp / energy / current
  and an editable room-temperature setpoint. A unit switched back on restarts after a 3 s lock-out.
* **Overview** – alarm list top-middle, live + history trends (velocity RMS, acceleration RMS) in the centre,
  one card per servo axis (RMS / peak / speed / temperature, V and A status lights) below, torque footer.
* **Mechanism setup** – master speed + RUN/STOP and every simulated mechanism parameter per axis
  (gear ratio, cam amplitude/harmonic, phase, inertia, friction, imbalance, looseness, bearing wear, misalignment).
  Type a value and press Enter. Axis 5 is disabled by default (set *Enabled* to 1).

### AC unit OPC UA nodes (simulator)
`AC1..AC7`: `Enable` (writable switch), `Running`, `SetTemp` (writable), `RatedPower`, `Power` (kW), `Current` (A),
`PowerFactor`, `Energy` (kWh), `RoomTemp`; `Energy.TotalPower`, `TotalEnergy`, `ShedPower` (estimate), `UnitsRunning`,
`UnitsShed`. For real meters/AC controllers keep the tag names or edit the addresses in the FUXA device; wire the
real shed command to whatever writes your unit's run/enable.

## Alarm levels (edit `THRESHOLDS` in `build_project.py`)
| Signal | Warning | Alarm |
|---|---|---|
| Velocity RMS | 4.5 mm/s | 7.1 mm/s |
| Acceleration RMS | 0.5 g | 1.0 g |
| Torque RMS | 70 % | 90 % |
| Temperature | 55 °C | 70 °C |

20 FUXA alarms (4 signals × 5 axes), each with a warning (high) and alarm (high-high) level, 1 s check / 2 s delay.

## Try a fault
Mechanism setup ▸ Axis 2 ▸ *Imbalance* 0.45 → velocity RMS rises above 7.1 mm/s and an alarm appears.
Bearing wear raises acceleration RMS and temperature; looseness/misalignment raise 2x and sub-harmonic content.

## Simulator model
Axis position = `ratio × master + phase + camAmp·sin(harmonic × master)`; velocity is the analytic derivative, torque =
inertia × acceleration + friction. Vibration is synthesised per axis from 1x (imbalance, ∝ rpm²), 2x (misalignment),
sub-harmonics (looseness / wear), a bearing band and a structural term, then converted to acceleration RMS (g) and
velocity RMS (mm/s). It is a plausible demo signal, not a physical model – replace the OPC UA nodes with your
drive/sensor tags (same names, or edit the tag addresses in the device) for real hardware.
