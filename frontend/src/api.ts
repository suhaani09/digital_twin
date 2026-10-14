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
}

