import { useCallback, useEffect, useState } from "react";

import {
  ackAlarm,
  getAlarmLimits,
  getRodEnvelope,
  moveRods,
  resetScram,
  scram,
} from "../api/endpoints";
import type { Alarm, AlarmLimits, RodEnvelope } from "../api/types";
import { useAuth } from "../auth/useAuth";
import { AlarmBanner } from "../components/AlarmBanner";
import { AlarmList } from "../components/AlarmList";
import { Gauge } from "../components/Gauge";
import { Header } from "../components/Header";
import { RodControl } from "../components/RodControl";
import { ScramControl } from "../components/ScramControl";
import { TrendChart } from "../components/TrendChart";
import { formatPeriod } from "../format";
import type { Severity } from "../format";
import { severity } from "../format";
import { useTelemetry } from "../telemetry/useTelemetry";

// Stable references so the memoised trend charts don't redraw on every telemetry message.
const POWER_DOMAIN: [number, number] = [90, 110];
const TEMP_DOMAIN: [number, number] = [306, 316];

function alarmSeverity(alarms: Alarm[], code: string): Severity {
  const alarm = alarms.find((a) => a.code === code);
  return alarm ? severity(alarm.state) : "normal";
}

export function DashboardPage() {
  const { can } = useAuth();
  const { status, telemetry, alarms, trend, retryAt } = useTelemetry(true);
  const [limits, setLimits] = useState<AlarmLimits | null>(null);
  const [envelope, setEnvelope] = useState<RodEnvelope | null>(null);

  useEffect(() => {
    // Limits can be changed by a supervisor at any time; re-read them every 30 s.
    const load = () => {
      getAlarmLimits().then(setLimits).catch(() => undefined);
    };
    load();
    getRodEnvelope().then(setEnvelope).catch(() => undefined);
    const timer = setInterval(load, 30_000);
    return () => {
      clearInterval(timer);
    };
  }, []);

  const onAck = useCallback(async (id: string) => {
    await ackAlarm(id); // the WebSocket delivers the state change
  }, []);
  const onMove = useCallback(async (target: number) => {
    await moveRods(target);
  }, []);
  const onScram = useCallback(async () => {
    await scram();
  }, []);
  const onReset = useCallback(async () => {
    await resetScram();
  }, []);

  const scrammed = telemetry?.scrammed ?? false;

  return (
    <div className="shell">
      <Header status={status} retryAt={retryAt} />
      <AlarmBanner alarms={alarms} scrammed={scrammed} />
      <main className="page">
        <div className="dashboard">
          <div className="stack">
            <section className="panel" aria-label="Reactor power">
              <Gauge
                label="Reactor power"
                value={telemetry?.power_percent ?? null}
                unit="%"
                min={0}
                max={150}
                limit={limits?.hi_power_percent}
                status={alarmSeverity(alarms, "HI_POWER")}
              />
            </section>
            <section className="panel" aria-label="Coolant temperature">
              <Gauge
                label="Coolant temperature"
                value={telemetry?.coolant_temp_c ?? null}
                unit="°C"
                min={280}
                max={340}
                limit={limits?.hi_temp_c}
                status={alarmSeverity(alarms, "HI_TEMP")}
              />
            </section>
            <section className="panel" aria-labelledby="core-title">
              <h2 className="panel-title" id="core-title">
                Core
              </h2>
              <dl className="readouts">
                <dt>Reactivity</dt>
                <dd>{telemetry ? `${telemetry.reactivity_pcm.toFixed(0)} pcm` : "–"}</dd>
                <dt>Period</dt>
                <dd>{telemetry ? formatPeriod(telemetry.reactor_period_s) : "–"}</dd>
                <dt>Simulated time</dt>
                <dd>{telemetry ? `${telemetry.sim_time_s.toFixed(0)} s` : "–"}</dd>
              </dl>
            </section>
          </div>

          <div className="trends">
            <TrendChart
              title="Reactor power"
              data={trend}
              dataKey="power"
              unit="%"
              limit={limits?.hi_power_percent}
              domain={POWER_DOMAIN}
            />
            <TrendChart
              title="Coolant temperature"
              data={trend}
              dataKey="temp"
              unit="°C"
              limit={limits?.hi_temp_c}
              domain={TEMP_DOMAIN}
            />
          </div>

          <div className="stack">
            <ScramControl
              scrammed={scrammed}
              rodPosition={telemetry?.rod_position_percent ?? null}
              canScram={can("operator")}
              canReset={can("supervisor")}
              onScram={onScram}
              onReset={onReset}
            />
            <RodControl
              position={telemetry?.rod_position_percent ?? null}
              target={telemetry?.rod_target_percent ?? null}
              scrammed={scrammed}
              envelope={envelope}
              canOperate={can("operator")}
              onMove={onMove}
            />
          </div>
        </div>
        <AlarmList alarms={alarms} canAck={can("operator")} onAck={onAck} />
      </main>
    </div>
  );
}
