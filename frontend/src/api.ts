import { CONFIG } from './config';
import type {
  DigitalTwinState,
  RawObservationItem,
  ClinicalAlert,
  ScenarioDefinition,
  ScenarioComparisonResult,
  SimulationStateResponse,
} from './types';

export class ApiClient {
  private static async request<T>(path: string, options?: RequestInit): Promise<T> {
    const res = await fetch(`${CONFIG.API_BASE_URL}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(options?.headers || {}),
      },
    });
    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`API error ${res.status} on ${path}: ${errText}`);
    }
    return res.json();
  }

  static async getHealth() {
    return this.request<{
      status: string;
      service: string;
      active_sessions: string[];
      current_patient: string;
      replay_status: string;
      ws_clients: number;
    }>('/health');
  }

  static async getTwinState(patientId?: string, sessionId?: string): Promise<DigitalTwinState> {
    const query = new URLSearchParams();
    if (patientId) query.set('patient_id', patientId);
    if (sessionId) query.set('session_id', sessionId);
    return this.request<DigitalTwinState>(`/twin/state?${query.toString()}`);
  }

  static async selectSession(patientId: string, sessionId: string = 'SESSION_1') {
    return this.request<{ message: string; patient_id: string; session_id: string }>(
      `/twin/select-session?patient_id=${encodeURIComponent(patientId)}&session_id=${encodeURIComponent(sessionId)}`,
      { method: 'POST' }
    );
  }

  static async resetTwin(patientId?: string, sessionId?: string) {
    const query = new URLSearchParams();
    if (patientId) query.set('patient_id', patientId);
    if (sessionId) query.set('session_id', sessionId);
    return this.request<{ message: string }>(`/twin/reset?${query.toString()}`, { method: 'POST' });
  }

  static async controlReplay(action: 'start' | 'pause' | 'resume' | 'stop' | 'reset' | 'speed' | 'seek', params?: {
    patient_id?: string;
    speed?: number;
    seek_seconds?: number;
  }) {
    return this.request<{
      action: string;
      replay_status: string;
      patient_id: string;
      session_id: string;
      speed: number;
    }>('/replay/control', {
      method: 'POST',
      body: JSON.stringify({ action, ...params }),
    });
  }

  static async getHistory(patientId?: string, sessionId?: string): Promise<{
    patient_id: string;
    count: number;
    history: RawObservationItem[];
  }> {
    const query = new URLSearchParams();
    if (patientId) query.set('patient_id', patientId);
    if (sessionId) query.set('session_id', sessionId);
    return this.request(`/twin/history?${query.toString()}`);
  }

  static async getAlerts(patientId?: string, sessionId?: string): Promise<{
    patient_id: string;
    alerts: ClinicalAlert[];
  }> {
    const query = new URLSearchParams();
    if (patientId) query.set('patient_id', patientId);
    if (sessionId) query.set('session_id', sessionId);
    return this.request(`/twin/alerts?${query.toString()}`);
  }

  static async getSimulationState(): Promise<SimulationStateResponse> {
    return this.request<SimulationStateResponse>('/simulation/state');
  }

  static async controlSimulation(action: string, advance_seconds: number = 1.0) {
    return this.request<{ action: string; sim_time_sec: number; summary: any }>('/simulation/control', {
      method: 'POST',
      body: JSON.stringify({ action, advance_seconds }),
    });
  }

  static async listPresetScenarios(): Promise<{ scenarios: ScenarioDefinition[] }> {
    return this.request<{ scenarios: ScenarioDefinition[] }>('/simulation/scenarios');
  }

  static async runScenario(payload: {
    scenario_id?: string;
    title?: string;
    parameter_overrides?: Record<string, number>;
    duration_sec?: number;
  }): Promise<ScenarioComparisonResult> {
    return this.request<ScenarioComparisonResult>('/simulation/scenarios/run', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // --- Feature 1: Time-Aware ECG Explorer APIs ---
  static async getECGMetadata(patientId?: string) {
    const query = new URLSearchParams();
    if (patientId) query.set('patient_id', patientId);
    const qs = query.toString() ? `?${query.toString()}` : '';
    return this.request<import('./types').ECGRecordingMetadata>(`/ecg/metadata${qs}`);
  }

  static async getECGWindow(timestamp: number, windowSec: number = 2.0, patientId?: string) {
    const query = new URLSearchParams({
      timestamp: String(timestamp),
      window_sec: String(windowSec),
    });
    if (patientId) query.set('patient_id', patientId);
    return this.request<import('./types').ECGWindowResponse>(
      `/ecg/window?${query.toString()}`
    );
  }

  // --- Feature 2: Evidence Ingestion APIs ---
  static async uploadEvidence(file: File, patientId?: string, sessionId?: string) {
    const formData = new FormData();
    formData.append('file', file);
    const query = new URLSearchParams();
    if (patientId) query.set('patient_id', patientId);
    if (sessionId) query.set('session_id', sessionId);

    const res = await fetch(`${CONFIG.API_BASE_URL}/evidence/upload?${query.toString()}`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      const err = await res.text();
      throw new Error(`Upload error ${res.status}: ${err}`);
    }
    return res.json();
  }

  static async listEvidence(sessionId?: string) {
    const query = new URLSearchParams();
    if (sessionId) query.set('session_id', sessionId);
    return this.request<{ session_id: string; evidence: import('./types').EvidenceItem[] }>(
      `/evidence/list?${query.toString()}`
    );
  }

  // --- Feature 3: Clinical Event Timeline & Audit Log APIs ---
  static async getEvents(params?: {
    session_id?: string;
    event_type?: string;
    severity?: string;
    category?: string;
    min_timestamp?: number;
    max_timestamp?: number;
    limit?: number;
  }) {
    const query = new URLSearchParams();
    if (params?.session_id) query.set('session_id', params.session_id);
    if (params?.event_type) query.set('event_type', params.event_type);
    if (params?.severity) query.set('severity', params.severity);
    if (params?.category) query.set('category', params.category);
    if (params?.min_timestamp !== undefined) query.set('min_timestamp', String(params.min_timestamp));
    if (params?.max_timestamp !== undefined) query.set('max_timestamp', String(params.max_timestamp));
    if (params?.limit) query.set('limit', String(params.limit));

    return this.request<{
      session_id: string;
      count: number;
      events: import('./types').ClinicalEventItem[];
    }>(`/events?${query.toString()}`);
  }
}


