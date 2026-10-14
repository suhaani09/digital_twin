/**
 * Central API & WebSocket configuration for Digital Twin Dashboard.
 * Ready for future Unity client connection.
 */

export const CONFIG = {
  API_BASE_URL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  WS_URL: import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws',
  DEFAULT_PATIENT_ID: '100',
  ECG_FS: 360,
  MAX_ECG_POINTS: 720, // 2.0 seconds at 360Hz
  MAX_TREND_POINTS: 60,
};

