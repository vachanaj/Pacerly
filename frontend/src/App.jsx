import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clipboard,
  ClipboardCheck,
  Flame,
  Footprints,
  Gauge,
  Play,
  Plus,
  RefreshCw,
  Server,
  Sliders,
  Sparkles,
  TrendingUp,
  User,
  Wifi,
  WifiOff,
  Zap,
} from 'lucide-react';

// --- Constants & Helpers matching Pacerly backend services ---
const DEFAULT_USER_ID = '11111111-1111-1111-1111-111111111111';
const PRESET_USERS = [
  { id: '11111111-1111-1111-1111-111111111111', label: 'Demo Runner (Default Test UUID)' },
  { id: '22222222-2222-2222-2222-222222222222', label: 'Endurance Athlete #2' },
  { id: '33333333-3333-3333-3333-333333333333', label: 'Marathon Block Runner #3' },
];

const DEFAULT_BASELINE_PACE_SEC = 330; // 5:30 /km

const INITIAL_SHOES = [
  {
    shoe_id: 'aaaa1111-1111-1111-1111-111111111111',
    brand: 'Adidas',
    model: 'Supernova Rise 3',
    nickname: 'Daily Trainer',
    current_mileage_km: 412.5,
    max_lifespan_km: 800,
    is_default: true,
  },
  {
    shoe_id: 'bbbb2222-2222-2222-2222-222222222222',
    brand: 'ASICS',
    model: 'Superblast 2',
    nickname: 'Long & Tempo',
    current_mileage_km: 585.0,
    max_lifespan_km: 700,
    is_default: false,
  },
  {
    shoe_id: 'cccc3333-3333-3333-3333-333333333333',
    brand: 'Nike',
    model: 'Vaporfly 3',
    nickname: 'Race / Intervals',
    current_mileage_km: 198.0,
    max_lifespan_km: 400,
    is_default: false,
  },
];

const INITIAL_LEDGER = [
  {
    activity_id: '90000001-0000-0000-0000-000000000001',
    title: 'Morning Aerobic Base',
    workout_type: 'easy',
    distance_km: 10.0,
    duration_sec: 3420,
    avg_pace_sec_per_km: 342,
    training_load_score: 4.67,
    activity_date: new Date(Date.now() - 1 * 86400000).toISOString(),
  },
  {
    activity_id: '90000002-0000-0000-0000-000000000002',
    title: 'Threshold Cruise Intervals',
    workout_type: 'tempo',
    distance_km: 12.0,
    duration_sec: 3600,
    avg_pace_sec_per_km: 300,
    training_load_score: 8.25,
    activity_date: new Date(Date.now() - 3 * 86400000).toISOString(),
  },
  {
    activity_id: '90000003-0000-0000-0000-000000000003',
    title: 'Sunday Progressive Long Run',
    workout_type: 'long',
    distance_km: 18.0,
    duration_sec: 6120,
    avg_pace_sec_per_km: 340,
    training_load_score: 11.38,
    activity_date: new Date(Date.now() - 5 * 86400000).toISOString(),
  },
];

function formatPace(secondsPerKm) {
  if (!secondsPerKm || secondsPerKm <= 0) return '--:--';
  const mins = Math.floor(secondsPerKm / 60);
  const secs = Math.round(secondsPerKm % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function formatDuration(totalSeconds) {
  const hrs = Math.floor(totalSeconds / 3600);
  const mins = Math.floor((totalSeconds % 3600) / 60);
  const secs = totalSeconds % 60;
  if (hrs > 0) {
    return `${hrs}h ${mins.toString().padStart(2, '0')}m`;
  }
  return `${mins}m ${secs.toString().padStart(2, '0')}s`;
}

// Mirrors compute_workout_load in backend/adaptive-pacing-service/app/main.py
function computeWorkoutLoad(
  durationSec,
  avgPaceSecPerKm,
  workoutType,
  baselinePaceSec = DEFAULT_BASELINE_PACE_SEC
) {
  const durationMin = durationSec / 60.0;
  const intensityRatio = baselinePaceSec / Math.max(avgPaceSecPerKm, 1);
  const weights = {
    easy: 0.85,
    recovery: 0.70,
    long: 1.15,
    tempo: 1.25,
    interval: 1.35,
  };
  const typeWeight = weights[(workoutType || '').toLowerCase()] ?? 1.0;
  const clampedIntensity = Math.max(0.75, Math.min(1.4, intensityRatio));
  return Math.round(durationMin * clampedIntensity * typeWeight * 0.1 * 100) / 100;
}

// Mirrors derive_pace_targets in backend/adaptive-pacing-service/app/main.py
function derivePaceTargets(rolling7dFatigueScore, baselinePaceSec = DEFAULT_BASELINE_PACE_SEC) {
  let fatigue_state = 'fresh';
  let pace_adjustment_factor = 0.99;

  if (rolling7dFatigueScore >= 120) {
    fatigue_state = 'overreaching';
    pace_adjustment_factor = 1.06;
  } else if (rolling7dFatigueScore >= 75) {
    fatigue_state = 'fatigued';
    pace_adjustment_factor = 1.03;
  } else if (rolling7dFatigueScore >= 25) {
    fatigue_state = 'optimal';
    pace_adjustment_factor = 1.0;
  }

  return {
    fatigue_state,
    pace_adjustment_factor,
    target_easy_pace_sec: Math.round(baselinePaceSec * 1.15 * pace_adjustment_factor),
    target_long_run_pace_sec: Math.round(baselinePaceSec * 1.10 * pace_adjustment_factor),
    target_tempo_pace_sec: Math.round(baselinePaceSec * 0.96 * pace_adjustment_factor),
    target_interval_pace_sec: Math.round(baselinePaceSec * 0.88 * pace_adjustment_factor),
  };
}

function generateUUID() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

const FATIGUE_THEME = {
  fresh: {
    label: 'Fresh & Primed',
    description: 'Low 7-day load. Targets slightly sharpened (-1%) for quality execution.',
    badge: 'bg-cyan-50 text-cyan-800 border-cyan-200',
    bar: 'bg-cyan-500',
  },
  optimal: {
    label: 'Optimal Load',
    description: 'Productive 7-day training stimulus. Targets locked at 1.00x baseline zones.',
    badge: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    bar: 'bg-emerald-500',
  },
  fatigued: {
    label: 'Elevated Fatigue',
    description: 'High 7-day accumulation. Targets eased by +3% to protect recovery.',
    badge: 'bg-amber-50 text-amber-800 border-amber-200',
    bar: 'bg-amber-500',
  },
  overreaching: {
    label: 'Overreaching Risk',
    description: 'Acute load spike detected. Targets throttled (+6%) to prevent injury.',
    badge: 'bg-rose-50 text-rose-800 border-rose-200',
    bar: 'bg-rose-500',
  },
};

export default function App() {
  // Connection & Auth Header state
  const [userId, setUserId] = useState(DEFAULT_USER_ID);
  const [customUserId, setCustomUserId] = useState(DEFAULT_USER_ID);
  const [pacingApiUrl, setPacingApiUrl] = useState('http://localhost:8003');
  const [activityApiUrl, setActivityApiUrl] = useState('http://localhost:8001');
  const [simulationMode, setSimulationMode] = useState(false);

  // Live service status
  const [serviceHealth, setServiceHealth] = useState('checking');
  const [apiError, setApiError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isRecalculating, setIsRecalculating] = useState(false);

  // Local reactive state
  const [ledger, setLedger] = useState(INITIAL_LEDGER);
  const [shoes, setShoes] = useState(INITIAL_SHOES);
  const [liveProfile, setLiveProfile] = useState(null);

  // Workout Logger form state
  const [title, setTitle] = useState('Evening Tempo Progression');
  const [workoutType, setWorkoutType] = useState('tempo');
  const [distanceKm, setDistanceKm] = useState('10.0');
  const [durationMin, setDurationMin] = useState('50');
  const [selectedShoeId, setSelectedShoeId] = useState(INITIAL_SHOES[0].shoe_id);
  const [lastEmittedEvent, setLastEmittedEvent] = useState(null);
  const [copiedPayload, setCopiedPayload] = useState(false);
  const [toastMessage, setToastMessage] = useState(null);

  const showToast = (msg) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 4000);
  };

  const simulatedProfile = useMemo(() => {
    const cutoff = Date.now() - 7 * 86400000;
    const recent = ledger.filter((item) => new Date(item.activity_date).getTime() >= cutoff);
    const rolling_7d_distance_km =
      Math.round(recent.reduce((acc, item) => acc + Number(item.distance_km), 0) * 10) / 10;
    const rolling_7d_fatigue_score =
      Math.round(recent.reduce((acc, item) => acc + Number(item.training_load_score), 0) * 100) /
      100;

    const derived = derivePaceTargets(rolling_7d_fatigue_score, DEFAULT_BASELINE_PACE_SEC);
    return {
      user_id: userId,
      rolling_7d_distance_km,
      rolling_7d_fatigue_score,
      ...derived,
      last_recalculated_at: new Date().toISOString(),
    };
  }, [ledger, userId]);

  const activeProfile = simulationMode || !liveProfile ? simulatedProfile : liveProfile;
  const theme = FATIGUE_THEME[activeProfile.fatigue_state] || FATIGUE_THEME.fresh;

  const fetchLivePaces = useCallback(async () => {
    if (simulationMode) {
      setServiceHealth('offline');
      setApiError(null);
      return;
    }

    setIsLoading(true);
    setApiError(null);
    try {
      const cleanBase = pacingApiUrl.replace(/\/+$/, '');
      const res = await fetch(`${cleanBase}/paces`, {
        headers: {
          'X-User-Id': userId,
          Accept: 'application/json',
        },
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${await res.text()}`);
      }
      const data = await res.json();
      setLiveProfile(data);
      setServiceHealth('online');
    } catch (err) {
      setServiceHealth('offline');
      setApiError(
        `Could not reach ${pacingApiUrl}/paces (${err.message}). Ensure FastAPI is running on port 8003 with CORSMiddleware enabled, or switch to Simulation Mode.`
      );
    } finally {
      setIsLoading(false);
    }
  }, [pacingApiUrl, userId, simulationMode]);

  useEffect(() => {
    fetchLivePaces();
  }, [fetchLivePaces]);

  const handleRecalculate = async () => {
    setIsRecalculating(true);
    setApiError(null);

    if (simulationMode) {
      await new Promise((r) => setTimeout(r, 250));
      setLedger((prev) => [...prev]);
      setIsRecalculating(false);
      showToast('Recalculated 7-day rolling fatigue & target paces in simulation.');
      return;
    }

    try {
      const cleanBase = pacingApiUrl.replace(/\/+$/, '');
      const res = await fetch(`${cleanBase}/paces/recalculate`, {
        method: 'POST',
        headers: {
          'X-User-Id': userId,
          Accept: 'application/json',
        },
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const data = await res.json();
      setLiveProfile(data);
      setServiceHealth('online');
      showToast('Live profile recalculated via POST /paces/recalculate');
    } catch (err) {
      setApiError(`Recalculation failed: ${err.message}. Check CORS or service status.`);
    } finally {
      setIsRecalculating(false);
    }
  };

  const handleLogWorkout = async (e) => {
    e.preventDefault();
    const dist = parseFloat(distanceKm);
    const durSec = Math.round(parseFloat(durationMin) * 60);
    if (isNaN(dist) || dist <= 0 || isNaN(durSec) || durSec <= 0) return;

    const avgPace = Math.max(1, Math.round(durSec / dist));
    const activityId = generateUUID();
    const startedAt = new Date().toISOString();

    const eventPayload = {
      activity_id: activityId,
      user_id: userId,
      shoe_id: selectedShoeId || null,
      workout_type: workoutType,
      total_distance_km: dist,
      total_duration_sec: durSec,
      avg_pace_sec_per_km: avgPace,
      started_at: startedAt,
    };

    setLastEmittedEvent(eventPayload);

    const loadScore = computeWorkoutLoad(durSec, avgPace, workoutType, DEFAULT_BASELINE_PACE_SEC);
    setLedger((prev) => [
      {
        activity_id: activityId,
        title: title.trim() || `${workoutType.toUpperCase()} Run`,
        workout_type: workoutType,
        distance_km: dist,
        duration_sec: durSec,
        avg_pace_sec_per_km: avgPace,
        training_load_score: loadScore,
        activity_date: startedAt,
      },
      ...prev,
    ]);

    if (selectedShoeId) {
      setShoes((prev) =>
        prev.map((s) =>
          s.shoe_id === selectedShoeId
            ? { ...s, current_mileage_km: Math.round((s.current_mileage_km + dist) * 10) / 10 }
            : s
        )
      );
    }

    if (!simulationMode) {
      try {
        const cleanActBase = activityApiUrl.replace(/\/+$/, '');
        const res = await fetch(`${cleanActBase}/activities`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-User-Id': userId,
          },
          body: JSON.stringify({
            title: title.trim() || 'Logged Run',
            workout_type: workoutType,
            total_distance_km: dist,
            total_duration_sec: durSec,
            shoe_id: selectedShoeId || null,
            started_at: startedAt,
          }),
        });
        if (res.ok) {
          showToast('Workout sent to Activity Service -> RabbitMQ -> Adaptive Pacing!');
          setTimeout(fetchLivePaces, 450);
          return;
        }
      } catch {
        // Activity service might not be running yet
      }
    }

    showToast(
      simulationMode
        ? `Simulated activity.logged (+${loadScore} fatigue load)`
        : 'Event payload generated! Copy JSON into RabbitMQ Exchange pacerly.events to test live consumer.'
    );
  };

  const copyEventJson = () => {
    if (!lastEmittedEvent) return;
    navigator.clipboard.writeText(JSON.stringify(lastEmittedEvent, null, 2));
    setCopiedPayload(true);
    setTimeout(() => setCopiedPayload(false), 2000);
  };

  const fatigueProgressPct = Math.min(
    100,
    Math.round((activeProfile.rolling_7d_fatigue_score / 140) * 100)
  );

  const paceZones = [
    {
      name: 'Easy Aerobic',
      code: 'ZONE 2 • RECOVERY & BASE',
      sec: activeProfile.target_easy_pace_sec,
      multiplier: '1.15x base',
      accent: 'border-emerald-200 bg-emerald-50 text-emerald-700',
      icon: Footprints,
    },
    {
      name: 'Long Endurance',
      code: 'AEROBIC DURABILITY',
      sec: activeProfile.target_long_run_pace_sec,
      multiplier: '1.10x base',
      accent: 'border-cyan-200 bg-cyan-50 text-cyan-700',
      icon: TrendingUp,
    },
    {
      name: 'Lactate Tempo',
      code: 'THRESHOLD CRUISE',
      sec: activeProfile.target_tempo_pace_sec,
      multiplier: '0.96x base',
      accent: 'border-amber-200 bg-amber-50 text-amber-700',
      icon: Flame,
    },
    {
      name: 'VO2 Max Intervals',
      code: 'HIGH-OUTPUT SPEED',
      sec: activeProfile.target_interval_pace_sec,
      multiplier: '0.88x base',
      accent: 'border-rose-200 bg-rose-50 text-rose-700',
      icon: Zap,
    },
  ];

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 font-sans selection:bg-emerald-200">
      {/* Top Navigation & Connection Bar */}
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3.5 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-emerald-500 to-cyan-600 flex items-center justify-center text-white font-black shadow-sm">
              <Activity className="h-6 w-6 stroke-[2.5]" />
            </div>
            <div>
              <div className="flex items-center gap-2.5 flex-wrap">
                <h1 className="text-lg font-bold tracking-tight text-slate-900">Pacerly</h1>
                <span className="text-[11px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200">
                  Adaptive Pacing
                </span>
                {simulationMode ? (
                  <span className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-0.5 rounded-full bg-amber-50 text-amber-800 border border-amber-200">
                    <Sparkles className="h-3 w-3" /> Simulation Mode
                  </span>
                ) : serviceHealth === 'online' ? (
                  <span className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-0.5 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200">
                    <Wifi className="h-3 w-3" /> FastAPI Connected
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-0.5 rounded-full bg-rose-50 text-rose-800 border border-rose-200">
                    <WifiOff className="h-3 w-3" /> API Unreachable
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-600">
                Dynamic Gear &amp; Endurance Platform • Event-Driven Microservice UI
              </p>
            </div>
          </div>

          {/* Controls: Mode Toggle, User Selector, Endpoint */}
          <div className="flex flex-wrap items-center gap-2.5">
            <div className="flex items-center bg-slate-100 border border-slate-200 rounded-lg p-1">
              <button
                type="button"
                onClick={() => setSimulationMode(false)}
                className={`px-2.5 py-1 rounded-md text-xs font-medium transition ${
                  !simulationMode
                    ? 'bg-emerald-600 text-white font-semibold'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Live API
              </button>
              <button
                type="button"
                onClick={() => setSimulationMode(true)}
                className={`px-2.5 py-1 rounded-md text-xs font-medium transition ${
                  simulationMode
                    ? 'bg-amber-500 text-white font-semibold'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                Simulate
              </button>
            </div>

            <div className="flex items-center gap-1.5 bg-white border border-slate-200 rounded-lg px-2.5 py-1.5">
              <User className="h-3.5 w-3.5 text-slate-500" />
              <select
                aria-label="Select User UUID"
                value={PRESET_USERS.some((u) => u.id === userId) ? userId : 'custom'}
                onChange={(e) => {
                  if (e.target.value !== 'custom') {
                    setUserId(e.target.value);
                    setCustomUserId(e.target.value);
                  }
                }}
                className="bg-transparent text-xs text-slate-800 focus:outline-none"
              >
                {PRESET_USERS.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.label}
                  </option>
                ))}
                <option value="custom">Custom X-User-Id...</option>
              </select>
            </div>

            {!simulationMode && (
              <div className="flex items-center gap-1.5 bg-white border border-slate-200 rounded-lg px-2.5 py-1.5">
                <Server className="h-3.5 w-3.5 text-slate-500" />
                <input
                  type="text"
                  value={pacingApiUrl}
                  onChange={(e) => setPacingApiUrl(e.target.value)}
                  className="bg-transparent text-xs text-slate-800 w-36 focus:outline-none"
                  placeholder="http://localhost:8003"
                />
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {/* Toast Banner */}
        {toastMessage && (
          <div className="flex items-center justify-between gap-3 px-4 py-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-900 text-sm">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
              <span>{toastMessage}</span>
            </div>
          </div>
        )}

        {/* API Connection / CORS Helper Banner */}
        {!simulationMode && apiError && (
          <div className="rounded-xl bg-rose-50 border border-rose-200 p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="flex items-start gap-3">
              <AlertTriangle className="h-5 w-5 text-rose-600 shrink-0 mt-0.5" />
              <div className="space-y-1">
                <p className="text-sm font-medium text-rose-900">{apiError}</p>
                <p className="text-xs text-rose-700">
                  Tip: Browser requests to{' '}
                  <code className="bg-rose-100 px-1 rounded">localhost:8003</code> require{' '}
                  <code className="bg-rose-100 px-1 rounded">CORSMiddleware</code> in FastAPI, or
                  click <strong className="text-rose-950">Switch to Simulate</strong> to test the
                  full pacing &amp; RabbitMQ flow right now.
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <button
                type="button"
                onClick={fetchLivePaces}
                className="px-3 py-1.5 rounded-lg bg-white hover:bg-slate-100 text-xs font-medium text-slate-800 border border-slate-300 transition"
              >
                Retry Live
              </button>
              <button
                type="button"
                onClick={() => setSimulationMode(true)}
                className="px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-600 text-xs font-semibold text-white transition"
              >
                Switch to Simulate
              </button>
            </div>
          </div>
        )}

        {/* Custom X-User-Id Bar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-4 py-2.5 rounded-xl bg-white border border-slate-200 text-xs text-slate-600 shadow-sm">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-slate-800">Active Header:</span>
            <code className="px-2 py-0.5 rounded bg-slate-100 text-emerald-700 border border-slate-200">
              X-User-Id: {userId}
            </code>
          </div>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={customUserId}
              onChange={(e) => setCustomUserId(e.target.value)}
              placeholder="Paste custom UUID..."
              className="bg-slate-50 border border-slate-300 rounded-lg px-2.5 py-1 text-xs text-slate-900 w-64 focus:outline-none focus:border-emerald-500"
            />
            <button
              type="button"
              onClick={() => {
                if (customUserId.trim()) setUserId(customUserId.trim());
              }}
              className="px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-800 font-medium border border-slate-200 transition"
            >
              Apply UUID
            </button>
          </div>
        </div>

        {/* Hero Section: 7-Day Fatigue Load & Pace Adjustment Factor */}
        <section className="rounded-2xl bg-white border border-slate-200 p-6 shadow-sm">
          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
            <div className="space-y-2 max-w-2xl">
              <div className="flex flex-wrap items-center gap-2.5">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  7-Day Fatigue Load &amp; Readiness
                </span>
                <span
                  className={`text-xs font-semibold px-2.5 py-0.5 rounded-full border uppercase tracking-wide ${theme.badge}`}
                >
                  {activeProfile.fatigue_state} • {theme.label}
                </span>
              </div>
              <h2 className="text-2xl sm:text-3xl font-bold text-slate-900 tracking-tight">
                Adaptive Pace Factor:{' '}
                <span className="text-emerald-600">
                  {Number(activeProfile.pace_adjustment_factor).toFixed(2)}x
                </span>
              </h2>
              <p className="text-sm text-slate-600">{theme.description}</p>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={fetchLivePaces}
                disabled={isLoading || simulationMode}
                className="inline-flex items-center gap-2 px-3.5 py-2.5 rounded-xl bg-white hover:bg-slate-50 disabled:opacity-40 text-xs font-semibold text-slate-800 border border-slate-300 transition"
              >
                <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
                Refresh
              </button>
              <button
                type="button"
                onClick={handleRecalculate}
                disabled={isRecalculating}
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-xs font-bold text-white shadow-sm transition"
              >
                <Sliders className={`h-4 w-4 ${isRecalculating ? 'animate-spin' : ''}`} />
                {isRecalculating ? 'Recalculating...' : 'Recalculate Paces'}
              </button>
            </div>
          </div>

          {/* Metrics & Fatigue Gauge */}
          <div className="mt-6 pt-6 border-t border-slate-200 grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="md:col-span-2 space-y-2.5">
              <div className="flex items-center justify-between text-xs flex-wrap gap-2">
                <span className="text-slate-600 font-medium">
                  Rolling 7-Day Fatigue Score:{' '}
                  <strong className="text-slate-900 text-sm">
                    {Number(activeProfile.rolling_7d_fatigue_score).toFixed(1)}
                  </strong>{' '}
                  / 140 pts
                </span>
                <span className="text-slate-600">
                  Thresholds: <span className="text-cyan-700 font-medium">&lt;25 Fresh</span> •{' '}
                  <span className="text-emerald-700 font-medium">25–74 Optimal</span> •{' '}
                  <span className="text-amber-700 font-medium">75–119 Fatigued</span> •{' '}
                  <span className="text-rose-700 font-medium">120+ Overreaching</span>
                </span>
              </div>
              <div className="h-3 w-full rounded-full bg-slate-100 border border-slate-200 overflow-hidden p-0.5">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${theme.bar}`}
                  style={{ width: `${fatigueProgressPct}%` }}
                />
              </div>
              <p className="text-[11px] text-slate-500">
                Last recalculated:{' '}
                {new Date(activeProfile.last_recalculated_at).toLocaleString()}
              </p>
            </div>

            <div className="flex items-center justify-between md:justify-end gap-6 bg-slate-50 border border-slate-200 rounded-xl px-4 py-3">
              <div>
                <p className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold">
                  7-Day Volume
                </p>
                <p className="text-2xl font-bold text-slate-900">
                  {Number(activeProfile.rolling_7d_distance_km).toFixed(1)}{' '}
                  <span className="text-sm font-normal text-slate-500">km</span>
                </p>
              </div>
              <div className="h-8 w-px bg-slate-200" />
              <div>
                <p className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold">
                  Baseline Pace
                </p>
                <p className="text-2xl font-bold text-slate-900">
                  {formatPace(DEFAULT_BASELINE_PACE_SEC)}{' '}
                  <span className="text-sm font-normal text-slate-500">/km</span>
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* 4 Adaptive Target Pace Cards */}
        <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {paceZones.map((zone) => {
            const Icon = zone.icon;
            return (
              <div
                key={zone.name}
                className="rounded-2xl bg-white border border-slate-200 hover:border-slate-300 p-5 shadow-sm transition flex flex-col justify-between gap-4"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                      {zone.code}
                    </p>
                    <h3 className="text-base font-bold text-slate-900 mt-0.5">{zone.name}</h3>
                  </div>
                  <div className={`p-2 rounded-xl border ${zone.accent}`}>
                    <Icon className="h-4 w-4" />
                  </div>
                </div>

                <div>
                  <div className="flex items-baseline gap-1.5">
                    <span className="text-3xl font-extrabold tracking-tight text-slate-900">
                      {formatPace(zone.sec)}
                    </span>
                    <span className="text-xs font-medium text-slate-500">/km</span>
                  </div>
                  <div className="mt-2 flex items-center justify-between text-xs text-slate-500">
                    <span>{zone.sec} sec/km</span>
                    <span className="px-2 py-0.5 rounded bg-slate-100 border border-slate-200 text-slate-700 text-[11px]">
                      {zone.multiplier}
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </section>

        {/* Bottom Grid: Workout / Event Logger + Gear Wear & 7-Day Ledger */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left Column: Log Workout & RabbitMQ activity.logged Simulator */}
          <section className="lg:col-span-5 rounded-2xl bg-white border border-slate-200 p-6 shadow-sm space-y-5">
            <div>
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <Play className="h-4 w-4 text-emerald-600" />
                Log Workout / Emit Event
              </h3>
              <p className="text-xs text-slate-600 mt-0.5">
                Publishes <code className="text-emerald-700 font-medium">activity.logged</code>{' '}
                &amp; updates 7-day load + shoe wear
              </p>
            </div>

            <form onSubmit={handleLogWorkout} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Workout Title
                </label>
                <input
                  type="text"
                  required
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  className="w-full rounded-xl bg-slate-50 border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:outline-none focus:border-emerald-500"
                  placeholder="Morning Tempo Run"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">
                    Workout Type
                  </label>
                  <select
                    value={workoutType}
                    onChange={(e) => setWorkoutType(e.target.value)}
                    className="w-full rounded-xl bg-slate-50 border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:outline-none focus:border-emerald-500"
                  >
                    <option value="easy">Easy (0.85x)</option>
                    <option value="recovery">Recovery (0.70x)</option>
                    <option value="long">Long Run (1.15x)</option>
                    <option value="tempo">Tempo (1.25x)</option>
                    <option value="interval">Interval (1.35x)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">
                    Shoe Rotation
                  </label>
                  <select
                    value={selectedShoeId}
                    onChange={(e) => setSelectedShoeId(e.target.value)}
                    className="w-full rounded-xl bg-slate-50 border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:outline-none focus:border-emerald-500"
                  >
                    {shoes.map((s) => (
                      <option key={s.shoe_id} value={s.shoe_id}>
                        {s.brand} {s.model}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">
                    Distance (km)
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    min="0.1"
                    required
                    value={distanceKm}
                    onChange={(e) => setDistanceKm(e.target.value)}
                    className="w-full rounded-xl bg-slate-50 border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:outline-none focus:border-emerald-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">
                    Duration (minutes)
                  </label>
                  <input
                    type="number"
                    step="1"
                    min="1"
                    required
                    value={durationMin}
                    onChange={(e) => setDurationMin(e.target.value)}
                    className="w-full rounded-xl bg-slate-50 border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:outline-none focus:border-emerald-500"
                  />
                </div>
              </div>

              <button
                type="submit"
                className="w-full inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-sm py-2.5 shadow-sm transition"
              >
                <Plus className="h-4 w-4 stroke-[2.5]" />
                Log Activity &amp; Trigger Pacing Update
              </button>
            </form>

            {/* Emitted RabbitMQ Event Payload Inspector */}
            {lastEmittedEvent && (
              <div className="rounded-xl bg-slate-50 border border-slate-200 p-3.5 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-emerald-700">
                    RabbitMQ Payload (routing_key: activity.logged)
                  </span>
                  <button
                    type="button"
                    onClick={copyEventJson}
                    className="inline-flex items-center gap-1 text-[11px] text-slate-700 hover:text-slate-900 bg-white border border-slate-200 px-2 py-0.5 rounded"
                  >
                    {copiedPayload ? (
                      <>
                        <ClipboardCheck className="h-3 w-3 text-emerald-600" /> Copied
                      </>
                    ) : (
                      <>
                        <Clipboard className="h-3 w-3" /> Copy JSON
                      </>
                    )}
                  </button>
                </div>
                <pre className="text-[11px] text-slate-800 overflow-x-auto leading-relaxed">
                  {JSON.stringify(lastEmittedEvent, null, 2)}
                </pre>
              </div>
            )}
          </section>

          {/* Right Column: Shoe Wear Indicators & 7-Day Fatigue Ledger */}
          <div className="lg:col-span-7 space-y-6">
            {/* Shoe Rotation Structural Wear Card */}
            <section className="rounded-2xl bg-white border border-slate-200 p-6 shadow-sm space-y-4">
              <div>
                <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                  <Footprints className="h-4 w-4 text-cyan-600" />
                  Multi-Shoe Structural Wear Rotation
                </h3>
                <p className="text-xs text-slate-600 mt-0.5">
                  Async mileage accumulation synced via{' '}
                  <code className="text-cyan-700 font-medium">activity.logged</code>
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5">
                {shoes.map((shoe) => {
                  const pct = Math.min(
                    100,
                    Math.round((shoe.current_mileage_km / shoe.max_lifespan_km) * 100)
                  );
                  const barColor =
                    pct >= 85 ? 'bg-rose-500' : pct >= 65 ? 'bg-amber-500' : 'bg-emerald-500';

                  return (
                    <div
                      key={shoe.shoe_id}
                      className="rounded-xl bg-slate-50 border border-slate-200 p-3.5 space-y-2.5"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <p className="text-xs font-bold text-slate-900">
                            {shoe.brand} {shoe.model}
                          </p>
                          <p className="text-[11px] text-slate-500">{shoe.nickname}</p>
                        </div>
                        <span
                          className={`text-[11px] font-bold px-2 py-0.5 rounded-full ${
                            pct >= 85
                              ? 'bg-rose-100 text-rose-800'
                              : pct >= 65
                              ? 'bg-amber-100 text-amber-800'
                              : 'bg-emerald-100 text-emerald-800'
                          }`}
                        >
                          {pct}%
                        </span>
                      </div>

                      <div className="h-2 w-full rounded-full bg-slate-200 overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-500 ${barColor}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>

                      <div className="flex items-center justify-between text-[11px] text-slate-600">
                        <span>{shoe.current_mileage_km.toFixed(1)} km</span>
                        <span>Max {shoe.max_lifespan_km} km</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>

            {/* Rolling 7-Day Fatigue Activity Ledger */}
            <section className="rounded-2xl bg-white border border-slate-200 p-6 shadow-sm space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                    <Gauge className="h-4 w-4 text-emerald-600" />
                    Rolling 7-Day Fatigue Ledger
                  </h3>
                  <p className="text-xs text-slate-600 mt-0.5">
                    Deduplicated workout entries feeding{' '}
                    <code className="text-slate-800 font-medium">fatigue_activity_ledger</code>
                  </p>
                </div>
                <span className="text-xs text-slate-500">{ledger.length} entries</span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="border-b border-slate-200 text-[11px] uppercase tracking-wider text-slate-500">
                      <th className="py-2.5 pr-3">Workout</th>
                      <th className="py-2.5 px-3">Type</th>
                      <th className="py-2.5 px-3">Dist / Time</th>
                      <th className="py-2.5 px-3">Avg Pace</th>
                      <th className="py-2.5 pl-3 text-right">Load Score</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 text-xs">
                    {ledger.map((item) => (
                      <tr key={item.activity_id} className="hover:bg-slate-50">
                        <td className="py-3 pr-3">
                          <p className="font-semibold text-slate-900">{item.title}</p>
                          <p className="text-[11px] text-slate-500">
                            {new Date(item.activity_date).toLocaleDateString()}
                          </p>
                        </td>
                        <td className="py-3 px-3">
                          <span className="px-2 py-0.5 rounded-md bg-slate-100 border border-slate-200 capitalize text-slate-700">
                            {item.workout_type}
                          </span>
                        </td>
                        <td className="py-3 px-3 text-slate-800">
                          {Number(item.distance_km).toFixed(1)} km •{' '}
                          <span className="text-slate-500">{formatDuration(item.duration_sec)}</span>
                        </td>
                        <td className="py-3 px-3 font-mono text-slate-800">
                          {formatPace(item.avg_pace_sec_per_km)} /km
                        </td>
                        <td className="py-3 pl-3 text-right font-bold text-emerald-700">
                          +{Number(item.training_load_score).toFixed(2)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </div>
        </div>
      </main>
    </div>
  );
}