import React, { useState, useEffect } from 'react';
import { ApiClient } from '../api';
import type { ClinicalEventItem, ClinicalAlert } from '../types';
import { Clock, AlertCircle, AlertTriangle, Info, Filter, ArrowUpDown } from 'lucide-react';

interface EventTimelineProps {
  alerts: ClinicalAlert[];
  simTimeSec?: number;
  sessionId?: string;
  onEventSelected?: (timestamp: number) => void;
}

export const EventTimeline: React.FC<EventTimelineProps> = ({
  alerts,
  sessionId,
  onEventSelected,
}) => {
  const [events, setEvents] = useState<ClinicalEventItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [filterType, setFilterType] = useState<string>('ALL');
  const [filterSeverity, setFilterSeverity] = useState<string>('ALL');
  const [sortOrder, setSortOrder] = useState<'DESC' | 'ASC'>('DESC');

  const fetchEvents = async () => {
    setIsLoading(true);
    try {
      const res = await ApiClient.getEvents({
        session_id: sessionId,
        event_type: filterType !== 'ALL' ? filterType : undefined,
        severity: filterSeverity !== 'ALL' ? filterSeverity : undefined,
        limit: 150,
      });
      setEvents(res.events);
    } catch (err) {
      console.error('Failed to query clinical events:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchEvents();
    // Poll every 3 seconds for new events
    const interval = setInterval(fetchEvents, 3000);
    return () => clearInterval(interval);
  }, [sessionId, filterType, filterSeverity]);

  // Combine live active alerts with historical events
  const sortedEvents = [...events].sort((a, b) => {
    return sortOrder === 'DESC' ? b.timestamp - a.timestamp : a.timestamp - b.timestamp;
  });

  const handleEventClick = (timestamp: number) => {
    if (onEventSelected) {
      onEventSelected(timestamp);
    }
  };

  return (
    <div className="card space-y-2.5">
      {/* Header bar */}
      <div className="flex flex-wrap justify-between items-center gap-2 border-b border-slate-800 pb-2">
        <div className="flex items-center gap-2">
          <Clock className="w-4 h-4 text-amber-400" />
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            Clinical Event Timeline & Audit Log
          </span>
          <span className="badge badge-amber">{alerts.length} Active Alarms</span>
          <span className="badge badge-purple">{events.length} Historical Logs</span>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-2 text-[11px]">
          <div className="flex items-center gap-1 text-slate-400">
            <Filter className="w-3 h-3" />
            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              className="bg-slate-950 border border-slate-800 text-slate-300 rounded px-1.5 py-0.5 text-[11px]"
            >
              <option value="ALL">All Types</option>
              <option value="REPLAY">Replay</option>
              <option value="EVIDENCE_UPLOAD">Evidence Upload</option>
              <option value="ML_INFERENCE">ML Classification</option>
              <option value="ALERT">Clinical Alert</option>
              <option value="SCENARIO">What-If Scenario</option>
            </select>
          </div>

          <div className="flex items-center gap-1 text-slate-400">
            <select
              value={filterSeverity}
              onChange={(e) => setFilterSeverity(e.target.value)}
              className="bg-slate-950 border border-slate-800 text-slate-300 rounded px-1.5 py-0.5 text-[11px]"
            >
              <option value="ALL">All Severities</option>
              <option value="CRITICAL">Critical</option>
              <option value="WARNING">Warning</option>
              <option value="INFO">Info</option>
            </select>
          </div>

          <button
            onClick={() => setSortOrder(sortOrder === 'DESC' ? 'ASC' : 'DESC')}
            title="Toggle sort direction"
            className="p-1 rounded bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-300"
          >
            <ArrowUpDown className="w-3 h-3" />
          </button>
        </div>
      </div>

      {/* Events Stream */}
      <div className="max-h-56 overflow-y-auto space-y-1.5 pr-1 divide-y divide-slate-800/40 text-xs">
        {isLoading && events.length === 0 ? (
          <div className="text-slate-500 py-6 text-center italic text-[11px]">
            Loading clinical events...
          </div>
        ) : sortedEvents.length === 0 ? (
          <div className="text-slate-500 py-6 text-center italic text-[11px]">
            No clinical events recorded for this session yet. Start replay or upload evidence to generate audit trail.
          </div>
        ) : (
          sortedEvents.map((evt) => (
            <div
              key={evt.event_id}
              onClick={() => handleEventClick(evt.timestamp)}
              className="pt-1.5 flex items-start gap-2.5 cursor-pointer hover:bg-slate-900/60 p-1 rounded transition"
              title="Click to jump ECG explorer to this timestamp"
            >
              <div className="mt-0.5 shrink-0">
                {evt.severity === 'CRITICAL' ? (
                  <AlertCircle className="w-4 h-4 text-rose-500" />
                ) : evt.severity === 'WARNING' ? (
                  <AlertTriangle className="w-4 h-4 text-amber-400" />
                ) : (
                  <Info className="w-4 h-4 text-sky-400" />
                )}
              </div>

              <div className="flex-1 min-w-0 space-y-0.5">
                <div className="flex justify-between items-baseline gap-2">
                  <div className="flex items-center gap-1.5 truncate">
                    <span className="font-semibold text-slate-200 text-[11px] truncate">
                      {evt.description}
                    </span>
                    <span className="text-[10px] px-1 py-0.2 rounded bg-slate-800 text-slate-400 font-mono">
                      {evt.event_type}
                    </span>
                  </div>
                  <span className="text-[10px] text-sky-400 hover:underline font-mono shrink-0">
                    t = {evt.timestamp.toFixed(2)}s
                  </span>
                </div>

                <div className="flex justify-between items-center text-[10px] text-slate-500 font-mono">
                  <span>Source: {evt.source_provenance}</span>
                  <span>[{evt.category}]</span>
                </div>

                {evt.metadata && Object.keys(evt.metadata).length > 0 && (
                  <div className="text-[10px] text-slate-400 font-mono bg-slate-950 p-1 rounded border border-slate-900 truncate">
                    {JSON.stringify(evt.metadata)}
                  </div>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
