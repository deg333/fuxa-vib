// OPC UA simulator: 1 machine, virtual master axis, up to 5 servo axes with adjustable mechanisms.
// Vibration (velocity RMS mm/s, acceleration RMS g) is synthesised from the kinematics
// (follower of the master axis) plus the mechanism parameters (imbalance, looseness, bearing wear, ...).
const { OPCUAServer, Variant, DataType, StatusCodes } = require("node-opcua");

const NAXES = 5;
const TICK_MS = 20;   // physics step; the master turns 72 deg/step at 600 rpm (no aliasing)
const PORT = Number(process.env.OPCUA_PORT || 4840);
const NS_URI = "urn:vibmon:sim";

// Writable mechanism parameters, per axis (name -> [default, type]).
const AXIS_PARAMS = {
  Enabled:       [true,  DataType.Boolean],
  GearRatio:     [1.0,   DataType.Double],  // follower ratio to master
  CamAmplitude:  [0.0,   DataType.Double],  // deg, electronic cam / oscillation on top of the ratio
  CamHarmonic:   [2,     DataType.Double],  // cam cycles per master revolution
  PhaseOffset:   [0.0,   DataType.Double],  // deg
  Inertia:       [0.02,  DataType.Double],  // kg.m2 (reflected load)
  RatedTorque:   [10.0,  DataType.Double],  // Nm
  Friction:      [5.0,   DataType.Double],  // % rated
  Imbalance:     [0.0,   DataType.Double],  // 0..1 rotating imbalance severity
  Looseness:     [0.0,   DataType.Double],  // 0..1 mechanical looseness / backlash
  BearingWear:   [0.0,   DataType.Double],  // 0..1 bearing defect severity
  Misalignment:  [0.0,   DataType.Double],  // 0..1 coupling misalignment
};
const DEFAULTS = {
  1: { GearRatio: 1.0,  CamAmplitude: 0,  Inertia: 0.020, Imbalance: 0.025, Looseness: 0.03, BearingWear: 0.03, Misalignment: 0.03 },
  2: { GearRatio: 2.0,  CamAmplitude: 15, CamHarmonic: 2, Inertia: 0.030, Imbalance: 0.08, Looseness: 0.10, BearingWear: 0.05, Misalignment: 0.08 },
  3: { GearRatio: 0.5,  CamAmplitude: 10, CamHarmonic: 1, PhaseOffset: 90, Inertia: 0.030, Imbalance: 0.05, Looseness: 0.04, BearingWear: 0.04, Misalignment: 0.04 },
  4: { GearRatio: 3.0,  CamAmplitude: 8,  CamHarmonic: 4, PhaseOffset: 180, Inertia: 0.015, Imbalance: 0.05, Looseness: 0.05, BearingWear: 0.05, Misalignment: 0.05 },
  5: { Enabled: false, GearRatio: 1.5, Inertia: 0.025, Imbalance: 0.05, Looseness: 0.05, BearingWear: 0.05, Misalignment: 0.05 },
};
const OUTPUTS = ["Position", "Speed", "Torque", "TorqueRMS", "VelRMS", "AccRMS", "VelPeak", "AccPeak", "Temperature"];

const gauss = () => { let s = 0; for (let i = 0; i < 6; i++) s += Math.random(); return (s - 3) / Math.sqrt(0.5); };
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

(async () => {
  const server = new OPCUAServer({
    port: PORT,
    resourcePath: "/UA/VibrationSim",
    buildInfo: { productName: "VibrationMonitorSim" },
  });
  await server.initialize();
  const space = server.engine.addressSpace;
  const ns = space.registerNamespace(NS_URI);
  const nsIdx = ns.index;
  const machine = ns.addObject({ organizedBy: space.rootFolder.objects, browseName: "Machine", nodeId: "s=Machine" });

  const state = { machine: {}, axes: {} };
  const vars = {};

  function addVar(parent, name, type, initial, writable) {
    const key = `${parent.name}.${name}`;
    vars[key] = initial;
    ns.addVariable({
      componentOf: parent.obj,
      browseName: name,
      nodeId: `s=${key}`,
      dataType: type === DataType.Boolean ? "Boolean" : "Double",
      minimumSamplingInterval: 100,
      value: {
        get: () => new Variant({ dataType: type, value: vars[key] }),
        set: writable ? (v) => { vars[key] = type === DataType.Boolean ? !!v.value : Number(v.value); return StatusCodes.Good; } : undefined,
      },
    });
    return key;
  }

  const master = { name: "Master", obj: machine };
  const M = {
    Run:      addVar(master, "Run", DataType.Boolean, true, true),
    Speed:    addVar(master, "Speed", DataType.Double, 600, true),   // rpm (setpoint, writable)
    Position: addVar(master, "Position", DataType.Double, 0, false), // deg 0..360
  };

  const axes = [];
  for (let n = 1; n <= NAXES; n++) {
    const obj = ns.addObject({ componentOf: machine, browseName: `Axis${n}`, nodeId: `s=Axis${n}` });
    const a = { n, name: `Axis${n}`, obj, k: {}, p: {}, s: { vel: 0, acc: 0, ang: 0, rmsV: 0, rmsA: 0, trq2: 0, temp: 30, pkV: 0, pkA: 0, prevVel: 0 } };
    for (const [pn, [def, type]] of Object.entries(AXIS_PARAMS)) {
      const v = DEFAULTS[n][pn] !== undefined ? DEFAULTS[n][pn] : def;
      a.k[pn] = addVar(a, pn, type, v, true);
    }
    for (const on of OUTPUTS) a.k[on] = addVar(a, on, DataType.Double, on === "Temperature" ? 30 : 0, false);
    axes.push(a);
  }

  let t = 0;
  const dt = TICK_MS / 1000;
  setInterval(() => {
    t += dt;
    const run = vars[M.Run];
    const mSpeed = run ? vars[M.Speed] : 0;               // rpm
    vars[M.Position] = (vars[M.Position] + mSpeed * 6 * dt) % 360;
    const mAng = vars[M.Position];                         // deg

    for (const a of axes) {
      const g = (k) => vars[a.k[k]];
      const s = a.s;
      if (!g("Enabled")) {
        for (const on of OUTPUTS) if (on !== "Temperature") vars[a.k[on]] = 0;
        s.vel = s.acc = s.rmsV = s.rmsA = s.trq2 = s.pkV = s.pkA = 0;
        s.temp += (25 - s.temp) * 0.002; vars[a.k.Temperature] = s.temp;
        continue;
      }
      // Kinematics: follower of the virtual master with cam overlay
      const pos = g("GearRatio") * mAng + g("PhaseOffset")
                + g("CamAmplitude") * Math.sin((g("CamHarmonic") * mAng * Math.PI) / 180);
      // analytic derivative (deg/s) avoids a spike when the master angle wraps at 360
      const mRate = mSpeed * 6;                               // master deg/s
      const vel = mRate * (g("GearRatio") + g("CamAmplitude") * g("CamHarmonic") * Math.cos((g("CamHarmonic") * mAng * Math.PI) / 180) * Math.PI / 180);
      const velRpm = vel / 6;
      const filt = 0.3;
      s.vel += (velRpm - s.vel) * filt;
      const accRadS2 = ((s.vel - s.prevVel) * 2 * Math.PI / 60) / dt;
      s.prevVel = s.vel;
      s.acc += (accRadS2 - s.acc) * filt;

      // Torque (% of rated): inertia * alpha + friction * sign + viscous
      const J = g("Inertia"), Tn = g("RatedTorque");
      const trqNm = J * s.acc + (g("Friction") / 100) * Tn * Math.sign(s.vel) + 0.0004 * s.vel;
      const trqPct = clamp((trqNm / Tn) * 100 + gauss() * 0.4, -300, 300);
      s.trq2 += (trqPct * trqPct - s.trq2) * 0.004;

      // Vibration synthesis
      const f1 = Math.abs(s.vel) / 60 + 1e-6;               // shaft frequency Hz
      const w1 = 2 * Math.PI * f1;
      const load = Math.min(1, Math.abs(trqPct) / 100);
      const imb = g("Imbalance"), loose = g("Looseness"), wear = g("BearingWear"), mis = g("Misalignment");
      // acceleration amplitudes in g (peak) per component
      const comps = [
        { f: f1,      a: 0.003 + 0.55 * imb * Math.min(1, (f1 / 10) ** 2) },                 // 1x imbalance ~ w^2
        { f: 2 * f1,  a: 0.004 + 0.40 * mis + 0.15 * loose },                                // 2x misalignment
        { f: 3.5 * f1, a: 0.004 + 0.30 * loose + 0.25 * wear },                              // sub/inter harmonics
        { f: 120,     a: 0.015 + 0.60 * wear * (0.5 + 0.5 * load) },                        // bearing defect band
        { f: 40,      a: 0.01 + 0.20 * Math.min(1, Math.abs(s.acc) / 300) + 0.04 * load }, // structure excited by accel/load
      ];
      let sumA2 = 0, sumV2 = 0;
      for (const c of comps) {
        const arms = (c.a / Math.SQRT2) * (Math.abs(s.vel) < 1 ? 0.1 : 1);
        sumA2 += arms * arms;
        // v = a / (2 pi f), a in m/s2, v in mm/s
        const v = (arms * 9.80665 / (2 * Math.PI * Math.max(c.f, 1))) * 1000;
        sumV2 += v * v;
      }
      const noise = 1 + 0.04 * gauss();
      const aRms = Math.sqrt(sumA2) * noise;
      const vRms = Math.sqrt(sumV2) * noise;
      s.rmsA += (aRms - s.rmsA) * 0.04;
      s.rmsV += (vRms - s.rmsV) * 0.04;
      s.pkA = s.rmsA * (1.414 + 0.5 * wear + 0.5 * loose + 0.04 * Math.abs(gauss()));
      s.pkV = s.rmsV * (1.414 + 0.3 * loose + 0.03 * Math.abs(gauss()));

      // Temperature: ambient + torque rms heating + bearing wear
      const target = 30 + 25 * (Math.sqrt(s.trq2) / 100) ** 2 + 20 * wear + 3 * Math.min(1, Math.abs(s.vel) / 3000);
      s.temp += (target - s.temp) * 0.0006;

      vars[a.k.Position] = ((pos % 360) + 360) % 360;
      vars[a.k.Speed] = s.vel;
      vars[a.k.Torque] = trqPct;
      vars[a.k.TorqueRMS] = Math.sqrt(s.trq2);
      vars[a.k.VelRMS] = s.rmsV;
      vars[a.k.AccRMS] = s.rmsA;
      vars[a.k.VelPeak] = s.pkV;
      vars[a.k.AccPeak] = s.pkA;
      vars[a.k.Temperature] = s.temp;
    }
  }, TICK_MS);

  await server.start();
  console.log(`OPC UA simulator running at ${server.getEndpointUrl()}  (namespace index ${nsIdx}, ${NS_URI})`);
  console.log(`Node ids: ns=${nsIdx};s=Axis1.VelRMS  ns=${nsIdx};s=Machine... (Master vars: ns=${nsIdx};s=Master.Speed)`);
})();
