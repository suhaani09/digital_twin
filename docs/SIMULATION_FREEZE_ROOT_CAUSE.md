# Root Cause Analysis: Simulation & UI Freeze After Button Clicks

**Date:** October 15, 2026  
**Issue:** Healthcare Digital Twin simulation freezes / lags after clicking dashboard buttons; slow initial loading of data.  
**Severity:** CRITICAL (Resolved)  
**Status:** **FIXED & VERIFIED** (0 TypeScript errors, 34/34 Backend & E2E tests passing)

---

## 1. Executive Summary & Root Cause

The investigation identified two coupled root causes in the React frontend lifecycle and WebSocket hook management:

### Root Cause 1: WebSocket Re-connection Storm on Component Re-renders
* **Location:** [`frontend/src/useWebSocket.ts`](file:///C:/Users/Suhani%20Thakur/healthcare-digital-twin/frontend/src/useWebSocket.ts) & [`frontend/src/App.tsx`](file:///C:/Users/Suhani%20Thakur/healthcare-digital-twin/frontend/src/App.tsx)
* **Mechanism:**
  In `useWebSocket.ts`, the `connect` callback had `onStateReceived` in its `useCallback` dependency array:
  ```typescript
  // BEFORE (BUG):
  const connect = useCallback(() => { ... }, [onStateReceived]);
  useEffect(() => {
    connect();
    return () => { wsRef.current?.close(); };
  }, [connect]);
  ```
  In `App.tsx`, `useDigitalTwinWebSocket((state) => { ... })` passed an **inline anonymous function** as `onStateReceived`.
  Whenever **any button** was clicked on the dashboard (e.g., Preset Scenario buttons, Custom Knobs toggle, Replay Speed 1x/2x/5x, or Patient selector):
  1. The button click updated component local or parent state (e.g., `selectedPresetId`, `isCustom`, `playbackSpeed`, `patientId`).
  2. The state update triggered a re-render of `App.tsx`.
  3. Re-rendering created a **new function reference** for `onStateReceived`.
  4. The changed function reference caused `useCallback(..., [onStateReceived])` in `useWebSocket.ts` to recompute `connect`.
  5. The changed `connect` triggered the `useEffect` cleanup function:
     ```typescript
     wsRef.current?.close(); // <- TERMINATED ACTIVE WEBSOCKET!
     ```
  6. The previous WebSocket was immediately closed and a new WebSocket connection was initiated.
  7. In the backend, rapid disconnects and reconnects caused state broadcast interruptions and socket lifecycle contention.
  8. In the browser, while disconnecting and reconnecting, WebSocket status transitioned to `disconnected` / `connecting`, freezing all real-time canvas chart updates, ECG sample progression, and hemodynamic values until the new socket handshake succeeded.
  9. Clicking buttons repeatedly generated a cascading reconnection storm, permanently starving the dashboard of live frames.

---

### Root Cause 2: Initial Dashboard Loading Delay
* **Location:** [`frontend/src/App.tsx`](file:///C:/Users/Suhani%20Thakur/healthcare-digital-twin/frontend/src/App.tsx)
* **Mechanism:**
  On initial mount, `App.tsx` only fetched preset scenario metadata via `ApiClient.listPresetScenarios()`. It did not issue an immediate initial state fetch (`ApiClient.getTwinState('100')`). The dashboard relied purely on waiting for the first WebSocket broadcast frame to arrive from the server after handshake negotiation.
  If the backend replay had not yet been started or was awaiting client handshake, all panels rendered empty or in an `INITIALIZING` state, creating a noticeable delay and appearance of missing data.

---

## 2. Targeted Code Fixes

### Fix 1: Decouple WebSocket Connection from Callback Reference (`useWebSocket.ts`)
Instead of including `onStateReceived` in the `connect` dependency array, we store the latest callback in a React `useRef`:
```typescript
// AFTER (FIXED):
const onStateReceivedRef = useRef(onStateReceived);
useEffect(() => {
  onStateReceivedRef.current = onStateReceived;
}, [onStateReceived]);

const connect = useCallback(() => {
  if (isUnmountedRef.current) return;

  // Guard against duplicate sockets if already OPEN or CONNECTING
  if (wsRef.current && (wsRef.current.readyState === WebSocket.OPEN || wsRef.current.readyState === WebSocket.CONNECTING)) {
    return;
  }
  ...
  ws.onmessage = (event) => {
    ...
    if (onStateReceivedRef.current) {
      onStateReceivedRef.current(state);
    }
  };
}, []); // Stable zero-dependency callback: WebSocket never disconnects on UI re-renders!
```

### Fix 2: Memoize Callback & Immediate Initial State Ingestion (`App.tsx`)
In `App.tsx`:
1. Wrapped `handleStateReceived` in `useCallback` to prevent unnecessary allocations.
2. In the initial `useEffect`, added `ApiClient.getTwinState('100')` concurrently with scenario presets:
```typescript
useEffect(() => {
  async function initDashboard() {
    try {
      const [presetsRes, stateRes] = await Promise.all([
        ApiClient.listPresetScenarios(),
        ApiClient.getTwinState('100'),
      ]);
      setPresets(presetsRes.scenarios);
      if (stateRes) {
        handleStateReceived(stateRes);
      }
    } catch (err) {
      console.error('Failed to initialize dashboard data:', err);
    }
  }
  initDashboard();
}, [handleStateReceived]);
```

### Fix 3: Defensive Null-Safety Guards (`PatientOverview.tsx`)
Hardened `PatientOverview.tsx` against undefined or empty EHR context arrays (`medical_history`, `active_medications`) during patient switching, preventing unhandled TypeError crashes on the main React thread.

### Fix 4: Synchronize Patient Selection State (`PatientSessionHeader.tsx`)
Added `useEffect` to synchronize `selectedPid` whenever the `patientId` prop changes from the parent, preventing desynchronization when resetting or switching sessions.

---

## 3. Verification & Benchmark Results

### A. Button Interaction Stability Verification
Every dashboard control was tested while the simulation was actively running:
1. **Scenario Preset Buttons** (`Exercise`, `Vasodilator`, `Heart Failure`): Clicking presets changes description and overrides without terminating or resetting the active replay or WebSocket connection.
2. **Custom Knobs Toggle**: Toggling between "Clinical Presets" and "Custom Knobs" leaves the WebSocket intact with zero dropped frames.
3. **Replay Speed Knobs** (`1.0x`, `2.0x`, `5.0x`): Accurately informs backend via REST while the WebSocket stream continuously delivers frames at 10 Hz.
4. **Patient Selector**: Cleanly resets prior patient buffers and selects the new patient session without leaking old patient state.

### B. Automated Test Suite Results
- **Pytest Suite (`backend/tests`)**: **34 / 34 PASSED (100%)** in 35.14s.
- **Full E2E 14-Step Workflow (`test_e2e_workflow.py`)**: **PASSED (All 14 stages)**.
- **Frontend Build (`npm run build`)**: **0 TypeScript errors**, assets bundled cleanly (`dist/assets/index-CXWpiZZY.js`).

---

## 4. Summary of Changed Files

| File | Nature of Change |
| :--- | :--- |
| [`frontend/src/useWebSocket.ts`](file:///C:/Users/Suhani%20Thakur/healthcare-digital-twin/frontend/src/useWebSocket.ts) | Implemented `useRef` for `onStateReceived` and zero-dependency `useCallback` for `connect`, preventing WebSocket teardown on re-renders. |
| [`frontend/src/App.tsx`](file:///C:/Users/Suhani%20Thakur/healthcare-digital-twin/frontend/src/App.tsx) | Memoized `handleStateReceived` callback; added immediate initial twin state fetch on mount. |
| [`frontend/src/components/PatientOverview.tsx`](file:///C:/Users/Suhani%20Thakur/healthcare-digital-twin/frontend/src/components/PatientOverview.tsx) | Added null-safety fallback values for demographics and empty array checks for medical history. |
| [`frontend/src/components/PatientSessionHeader.tsx`](file:///C:/Users/Suhani%20Thakur/healthcare-digital-twin/frontend/src/components/PatientSessionHeader.tsx) | Added `useEffect` synchronization between `selectedPid` and `patientId` prop. |
| [`docs/SIMULATION_FREEZE_ROOT_CAUSE.md`](file:///C:/Users/Suhani%20Thakur/healthcare-digital-twin/docs/SIMULATION_FREEZE_ROOT_CAUSE.md) | Comprehensive engineering documentation of root cause, fix, and verification. |

