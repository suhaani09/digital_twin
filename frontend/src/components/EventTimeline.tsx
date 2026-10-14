import React from 'react';
import type { ClinicalAlert } from '../types';
import { AlertCircle, AlertTriangle, Info, Clock } from 'lucide-react';

interface EventTimelineProps {
  alerts: ClinicalAlert[];
  simTimeSec?: number;
}

export const EventTimeline: React.FC<EventTimelineProps> = ({ alerts }) => {
  return (
    <div className="card space-y-2.5">
      <div className="flex justify-between items-center border-b border-slate-800 pb-2">
        <div className="flex items-center gap-2">
          <Clock className="w-4 h-4 text-amber-400" />
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            Clinical Event Timeline & Audit Log
          </span>
        </div>
        <span className="badge badge-amber">{alerts.length} Active Events</span>
      </div>

      <div className="max-h-52 overflow-y-auto space-y-2 pr-1 divide-y divide-slate-800/40">
        {alerts.length === 0 ? (
          <div className="text-xs text-slate-500 py-6 text-center italic">
            No critical physiological alarms active. Vitals within expected limits.
          </div>
        ) : (
          alerts.map((alert) => (
            <div key={alert.alert_id} className="pt-2 flex items-start gap-2.5 text-xs">
              <div className="mt-0.5 shrink-0">
                {alert.severity === 'CRITICAL' ? (
                  <AlertCircle className="w-4 h-4 text-rose-500" />
                ) : alert.severity === 'WARNING' ? (
                  <AlertTriangle className="w-4 h-4 text-amber-500" />
                ) : (
                  <Info className="w-4 h-4 text-sky-400" />
                )}
              </div>

              <div className="flex-1 space-y-0.5">
                <div className="flex justify-between items-baseline">
                  <span className="font-semibold text-slate-200">{alert.title}</span>
                  <span className="text-[10px] text-slate-500 font-mono">
                    t = {alert.timestamp.toFixed(1)}s
                  </span>
                </div>
                <p className="text-slate-400 text-[11px]">{alert.description}</p>
                <div className="text-[10px] text-slate-500 font-mono">
                  Evidence: {JSON.stringify(alert.evidence)}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
