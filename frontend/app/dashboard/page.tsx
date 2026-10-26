'use client';
import { useRef, useEffect, useState, type MouseEvent, type PointerEvent, type ReactNode } from 'react';
import Link from 'next/link';
import {
  BACKEND_URL_KEY,
  loadCachedContacts,
  mixedContentProblem,
  normalizeBackendUrl,
  saveCachedContacts,
  syncContactsToPi,
} from '@/lib/sliplert';

const DEFAULT_BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || '';

type Delivery = {
  name: string;
  to: string;
  status: 'sending' | 'sent' | 'failed';
  method?: string;
  error?: string | null;
};

type FallRecord = {
  timestamp: string;
  fall_type: string;
  body_angle: number;
  confidence: number;
  called_contacts?: string[];
  called_phones?: string[];
  delivery?: Delivery[];
};

type RobotStatus = {
  autonomous: boolean;
  gpio_available: boolean;
  motor_error?: string | null;
  motor_action?: string;
  follow_state?: string;
  camera_running: boolean;
  camera_error?: string | null;
  person_detected: boolean;
  fps: number;
  body_angle?: number;
  posture_score?: number;
  smtp_configured?: boolean;
  contacts_count?: number;
  last_fall?: FallRecord | null;
};

type OutboxEntry = {
  id: string; // fall timestamp from the Pi
  subject: string;
  time: string;
  body: string;
  delivery: Delivery[];
};

type DriveAction = 'forward' | 'backward' | 'left' | 'right' | 'stop';

const FOLLOW_LABELS: Record<string, string> = {
  approaching: 'FOLLOWING',
  turning: 'TURNING TO PERSON',
  arrived: 'NEXT TO PERSON',
  backing_up: 'BACKING UP',
  waiting: 'PERSON LOST',
  searching: 'SEARCHING',
  idle: 'WAITING FOR PERSON',
  paused: 'PAUSED',
};

const EMAIL_SUBJECT = 'URGENT: SlipLert Fall Detected';

// Press-and-hold motor button: drives while held, stops on release (mouse or touch)
function DriveButton({ onStart, onEnd, disabled, children }: {
  onStart: () => void;
  onEnd: () => void;
  disabled: boolean;
  children: ReactNode;
}) {
  return (
    <button
      disabled={disabled}
      onPointerDown={(e: PointerEvent<HTMLButtonElement>) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        onStart();
      }}
      onPointerUp={onEnd}
      onPointerCancel={onEnd}
      onLostPointerCapture={onEnd}
      onContextMenu={(e: MouseEvent) => e.preventDefault()}
      className="py-2 bg-slate-950 hover:bg-indigo-600 active:bg-indigo-500 border border-slate-800 rounded-lg font-semibold transition disabled:opacity-40"
    >
      {children}
    </button>
  );
}

export default function CameraDashboard() {
  const lastRobotFallRef = useRef<string | null>(null);
  const alertTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const driveTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const backendUrlRef = useRef(DEFAULT_BACKEND_URL);
  const outboxIdsRef = useRef<Set<string>>(new Set());
  const deliveryLogRef = useRef<Record<string, string>>({});
  const [status, setStatus] = useState('ONLINE');
  const [alertMessage, setAlertMessage] = useState('FALL PATTERN CONFIRMED BY POSE AI');
  const [alertId, setAlertId] = useState<string | null>(null);
  const [outbox, setOutbox] = useState<OutboxEntry[]>([]);
  const [robot, setRobot] = useState<RobotStatus | null>(null);
  const [robotBusy, setRobotBusy] = useState(false);
  const [backendUrl, setBackendUrl] = useState(DEFAULT_BACKEND_URL);
  const [urlInput, setUrlInput] = useState(DEFAULT_BACKEND_URL);
  const [connected, setConnected] = useState(false);
  const [streamKey, setStreamKey] = useState(0);
  const [systemLog, setSystemLog] = useState<string[]>([
    'System initialized.',
    'Enter Raspberry Pi IP in Robot Control and click Connect.',
    'Ready for autonomous robot monitoring.'
  ]);

  const [stats, setStats] = useState({ fps: 0, latency: 12, postureScore: 98 });

  const addLog = (message: string) => {
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    setSystemLog(prev => [`[${time}] ${message}`, ...prev.slice(0, 7)]);
  };

  // Called once per fall (keyed by the Pi's timestamp) — later polls only update delivery status
  const triggerFallSequence = (fall: FallRecord) => {
    const fallType = fall.fall_type || 'horizontal';
    const bodyAngle = fall.body_angle || 80;
    setStatus('ALERT_TRIGGERED');
    setAlertId(fall.timestamp);
    setStats(prev => ({
      ...prev,
      postureScore: Math.max(0, Math.floor(100 - bodyAngle)),
    }));
    const contactsList = fall.called_contacts || [];
    const who = contactsList.length > 0 ? contactsList.join(', ') : 'NO EMERGENCY CONTACTS SAVED';
    setAlertMessage(`FALL DETECTED (${fallType.toUpperCase()}) — ALERTING ${who.toUpperCase()}`);
    addLog(contactsList.length > 0
      ? `CRITICAL: Fall detected (${fallType})! Robot stopped, alerting ${who}...`
      : `CRITICAL: Fall detected (${fallType}) but no emergency contacts are saved — add one in Settings!`);

    const nowStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const bodyText = `Your loved one has fallen — please check on them immediately. (${fallType}, angle ${Math.round(bodyAngle)} deg at ${nowStr}) The robot car has stopped safely next to them.`;
    outboxIdsRef.current.add(fall.timestamp);
    setOutbox(prev => [
      { id: fall.timestamp, subject: EMAIL_SUBJECT, time: nowStr, body: bodyText, delivery: fall.delivery || [] },
      ...prev.filter(e => e.id !== fall.timestamp).slice(0, 3),
    ]);

    if (alertTimerRef.current) clearTimeout(alertTimerRef.current);
    alertTimerRef.current = setTimeout(() => {
      setStatus('ONLINE');
      setStats(prev => ({ ...prev, postureScore: 98 }));
      addLog('Resumed autonomous robot monitoring.');
    }, 6500);
  };

  // Pi reports each email/SMS as sending -> sent/failed; mirror that in the outbox
  const updateDelivery = (fall: FallRecord) => {
    if (!outboxIdsRef.current.has(fall.timestamp)) return; // an old fall from before this page was opened
    const delivery = fall.delivery || [];
    for (const d of delivery) {
      const key = `${fall.timestamp}|${d.to}`;
      if (d.status !== 'sending' && deliveryLogRef.current[key] !== d.status) {
        deliveryLogRef.current[key] = d.status;
        addLog(d.status === 'sent'
          ? `Alert delivered to ${d.name} <${d.to}> via ${d.method}.`
          : `ALERT FAILED for ${d.name} <${d.to}>: ${d.error || 'unknown error'}`);
      }
    }
    setOutbox(prev => prev.map(e => (e.id === fall.timestamp ? { ...e, delivery } : e)));
  };

  const syncContacts = async (url: string) => {
    try {
      const onPi = await syncContactsToPi(url);
      if (onPi) {
        saveCachedContacts(onPi);
        if (onPi.length === 0) addLog('No emergency contacts on the robot yet — add one in Settings.');
      }
    } catch {}
  };

  useEffect(() => {
    backendUrlRef.current = backendUrl;
  }, [backendUrl]);

  useEffect(() => {
    const saved = window.localStorage.getItem(BACKEND_URL_KEY);
    if (saved && !saved.includes('localhost')) {
      setBackendUrl(saved);
      setUrlInput(saved);
      setConnected(true);
      syncContacts(saved);
      const problem = mixedContentProblem(saved);
      if (problem) addLog(problem);
    }
    return () => {
      if (alertTimerRef.current) clearTimeout(alertTimerRef.current);
      if (driveTimerRef.current) clearInterval(driveTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!connected || !backendUrl) {
      setRobot(null);
      return;
    }
    const checkRobot = async () => {
      const t0 = performance.now();
      try {
        const response = await fetch(`${backendUrl}/robot/status`, { signal: AbortSignal.timeout(2500) });
        if (!response.ok) {
          setRobot(null);
          return;
        }
        const elapsed = Math.max(1, Math.round(performance.now() - t0));
        const data: RobotStatus = await response.json();
        setRobot(data);
        setStats(prev => ({
          fps: data.camera_running ? data.fps : 0,
          latency: elapsed,
          postureScore: typeof data.posture_score === 'number' ? data.posture_score : prev.postureScore,
        }));
        if (data.last_fall) {
          if (lastRobotFallRef.current === null) {
            // First poll after (re)loading the page: don't replay an old fall as a new emergency
            lastRobotFallRef.current = data.last_fall.timestamp;
          } else if (data.last_fall.timestamp !== lastRobotFallRef.current) {
            lastRobotFallRef.current = data.last_fall.timestamp;
            triggerFallSequence(data.last_fall);
          }
          updateDelivery(data.last_fall);
        } else if (lastRobotFallRef.current === null) {
          lastRobotFallRef.current = '';
        }
      } catch {
        setRobot(null);
      }
    };
    checkRobot();
    const poll = setInterval(checkRobot, 1000);
    return () => clearInterval(poll);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [backendUrl, connected]);

  const toggleConnection = async () => {
    if (connected) {
      if (backendUrl) {
        try {
          await fetch(`${backendUrl}/robot/camera`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: false }),
          });
        } catch {}
      }
      setConnected(false);
      setRobot(null);
      setStats(prev => ({ ...prev, fps: 0 }));
      addLog('Disconnected from Raspberry Pi robot car.');
      return;
    }
    const finalUrl = normalizeBackendUrl(urlInput);
    if (!finalUrl) {
      addLog('Please enter your Raspberry Pi IP address first.');
      return;
    }
    const problem = mixedContentProblem(finalUrl);
    if (problem) addLog(problem);
    setBackendUrl(finalUrl);
    setUrlInput(finalUrl);
    window.localStorage.setItem(BACKEND_URL_KEY, finalUrl);
    lastRobotFallRef.current = null;
    setConnected(true);
    setStreamKey(prev => prev + 1);
    try {
      await syncContacts(finalUrl);
      await fetch(`${finalUrl}/robot/camera`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: true, autonomous: true }),
        signal: AbortSignal.timeout(5000),
      });
      const res = await fetch(`${finalUrl}/robot/status`, { signal: AbortSignal.timeout(3000) });
      if (res.ok) {
        const data: RobotStatus = await res.json();
        setRobot(data);
        addLog(`Connected to robot car at ${finalUrl} — it will drive toward the person once the camera sees them.`);
        if (!data.gpio_available) addLog(`Motors are OFF: ${data.motor_error || 'GPIO not initialized'}`);
      } else {
        addLog(`Could not reach ${finalUrl}.`);
      }
    } catch {
      addLog(`Could not reach ${finalUrl} — check that python main.py is running on the Pi and both are on the same Wi-Fi.`);
    }
  };

  const toggleFollowing = async () => {
    if (!robot) return;
    setRobotBusy(true);
    const enable = !robot.autonomous;
    try {
      const response = await fetch(`${backendUrl}/robot/autonomous`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: enable }),
      });
      const data = await response.json();
      setRobot({ ...robot, autonomous: data.status });
      addLog(enable ? 'Autonomous following engaged.' : 'Autonomous following paused.');
    } catch {
      addLog('Could not reach the robot.');
    }
    setRobotBusy(false);
  };

  // Each command auto-stops on the Pi after 0.5s, so we re-send it while the button is held.
  // If Wi-Fi drops or the button is released, the car stops by itself.
  const sendRobotCommand = async (action: DriveAction, log: boolean) => {
    try {
      const response = await fetch(`${backendUrlRef.current}/robot/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, duration: 0.5 }),
        signal: AbortSignal.timeout(1500),
      });
      const data = await response.json();
      if (log) {
        setRobot(prev => (prev ? { ...prev, autonomous: false } : prev));
        addLog(data.status === 'simulation'
          ? `Motor ${action.toUpperCase()} ignored — ${data.message}`
          : `Motor drive: ${action.toUpperCase()}.`);
      }
    } catch {
      if (log) addLog(`Failed to send ${action} command to robot.`);
    }
  };

  const startDrive = (action: DriveAction) => {
    if (!robot) return;
    if (driveTimerRef.current) clearInterval(driveTimerRef.current);
    sendRobotCommand(action, true);
    driveTimerRef.current = setInterval(() => sendRobotCommand(action, false), 250);
  };

  const endDrive = () => {
    if (!driveTimerRef.current) return;
    clearInterval(driveTimerRef.current);
    driveTimerRef.current = null;
    sendRobotCommand('stop', false);
  };

  const simulateSensorSignal = async () => {
    if (!connected || !backendUrlRef.current) {
      addLog('Connect to the robot first — the Pi is what sends the emergency email.');
      return;
    }
    setStatus('EVALUATING');
    addLog('Sending a test fall to the robot...');
    try {
      // Talk to the Pi straight from the browser: a deployed Next.js server can't reach a home-network Pi
      const response = await fetch(`${backendUrlRef.current}/detect-fall-base64`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ simulate: true, contacts: loadCachedContacts() }),
        signal: AbortSignal.timeout(8000),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (data.fall_detected) {
        const fall: FallRecord = {
          timestamp: data.timestamp,
          fall_type: data.fall_type || 'simulated_fall',
          body_angle: data.body_angle || 82,
          confidence: data.confidence,
          called_contacts: data.called_contacts,
          called_phones: data.called_phones,
          delivery: data.delivery,
        };
        lastRobotFallRef.current = fall.timestamp; // the status poll will see this same fall; don't double-count it
        triggerFallSequence(fall);
      } else {
        setStatus('SAFE');
        addLog('False alarm. Pose AI verified orientation as upright.');
        setTimeout(() => setStatus('ONLINE'), 3000);
      }
    } catch {
      setStatus('ONLINE');
      addLog('Could not reach the robot to run the test.');
    }
  };

  const activeAlert = outbox.find(e => e.id === alertId);
  const deliverySummary = (d: Delivery[]) => {
    if (d.length === 0) return { text: 'NO CONTACTS SAVED', cls: 'text-amber-400' };
    if (d.some(x => x.status === 'sending')) return { text: 'SENDING…', cls: 'text-amber-400' };
    if (d.every(x => x.status === 'sent')) return { text: 'ALERT DELIVERED & ROBOT STOPPED', cls: 'text-emerald-400' };
    if (d.some(x => x.status === 'sent')) return { text: 'PARTLY DELIVERED — SEE OUTBOX', cls: 'text-amber-400' };
    return { text: 'DELIVERY FAILED — SEE OUTBOX', cls: 'text-red-400' };
  };
  const followLabel = robot?.autonomous
    ? FOLLOW_LABELS[robot.follow_state || ''] || (robot.person_detected ? 'FOLLOWING' : 'SEARCHING')
    : 'PAUSED';
  const robotProblems = robot
    ? [
        !robot.gpio_available ? `Motors off: ${robot.motor_error || 'GPIO not initialized'}` : null,
        robot.camera_error ? `Camera: ${robot.camera_error}` : null,
        robot.contacts_count === 0 ? 'No emergency contacts on the robot — add one in Settings.' : null,
        robot.smtp_configured === false
          ? 'Email is using direct delivery (often blocked or sent to spam). For reliable alerts set SMTP_EMAIL and SMTP_PASSWORD in Backend/.env.'
          : null,
      ].filter((p): p is string => Boolean(p))
    : [];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-mono selection:bg-indigo-500 selection:text-white">

      <header className="border-b border-slate-800 bg-slate-900/50 backdrop-blur px-6 py-4 flex items-center sticky top-0 z-50">
        <div className="flex items-center space-x-3">
          <div className="h-3 w-3 rounded-full bg-indigo-500 animate-pulse" />
          <h1 className="text-xl font-bold tracking-wider text-slate-200">
            Slip<span className="text-indigo-500">Lert</span> OS
          </h1>
        </div>

        <div className="flex items-center space-x-6 ml-auto">
          <Link href="/" className="text-slate-400 hover:text-white transition text-sm">Home</Link>
          <Link href="/dashboard" className="text-slate-400 hover:text-white transition text-sm">Dashboard</Link>
          <Link href="/settings" className="text-slate-400 hover:text-white transition text-sm">Settings</Link>
        </div>
        <div className="flex items-center space-x-4 ml-6">
          <div className="text-xs bg-slate-800 border border-slate-700 px-3 py-1.5 rounded-md font-mono text-slate-400">
            LOC: ROBOT_UNIT_1
          </div>
          {status === 'ONLINE' && <span className="px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">SYSTEM LIVE</span>}
          {status === 'EVALUATING' && <span className="px-3 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20 animate-pulse">ANALYZING FRAME</span>}
          {status === 'ALERT_TRIGGERED' && <span className="px-3 py-1 rounded-full text-xs font-semibold bg-red-500/10 text-red-400 border border-red-500/20 animate-bounce">EMERGENCY ACTIVE</span>}
          {status === 'SAFE' && <span className="px-3 py-1 rounded-full text-xs font-semibold bg-blue-500/10 text-blue-400 border border-blue-500/20">POSTURE VERIFIED</span>}
        </div>
      </header>

      <main className="flex-1 grid grid-cols-1 lg:grid-cols-3 gap-6 p-6 max-w-7xl mx-auto w-full">

        <div className="lg:col-span-2 flex flex-col space-y-4">
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-2xl relative group aspect-video flex items-center justify-center">
            {connected && robot?.camera_running ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                key={`${backendUrl}-${streamKey}`}
                src={`${backendUrl}/video_feed?t=${streamKey}`}
                alt="Robot car camera perspective"
                className="w-full h-full object-cover"
              />
            ) : (
              <div className="absolute inset-0 bg-slate-900 flex flex-col items-center justify-center p-6 text-center">
                <div className="text-slate-300 text-sm font-semibold mb-2">
                  {connected && robot ? 'Camera Starting…' : 'Camera Feed Disconnected'}
                </div>
                <div className="text-slate-500 text-xs max-w-md">
                  {connected && robot?.camera_error
                    ? robot.camera_error
                    : 'Click Connect in Robot Car Control on the right to start live fall detection.'}
                </div>
              </div>
            )}

            <div className="absolute top-4 left-4 bg-slate-950/80 backdrop-blur text-xs px-2.5 py-1 rounded text-indigo-400 font-mono tracking-widest border border-slate-800">
              REC // ROBOT_CAR_POV_FEED
            </div>

            {status === 'ALERT_TRIGGERED' && (
              <div className="absolute inset-0 bg-red-600/20 border-4 border-red-500 animate-pulse flex items-center justify-center pointer-events-none p-4">
                <div className="bg-slate-950/95 text-red-400 font-bold px-6 py-4 rounded-lg border border-red-500/50 text-center tracking-wider text-sm space-y-2 max-w-lg w-full">
                  <div>{alertMessage}</div>
                  <div className="bg-slate-900 border border-slate-800 rounded p-3 text-left text-xs font-mono text-slate-300 space-y-1">
                    <div><span className="text-slate-500">TO:</span> {activeAlert && activeAlert.delivery.length > 0 ? activeAlert.delivery.map(d => d.to).join(', ') : 'No emergency contacts saved'}</div>
                    <div><span className="text-slate-500">SUBJECT:</span> {EMAIL_SUBJECT}</div>
                    <div>
                      <span className="text-slate-500">STATUS:</span>{' '}
                      <span className={deliverySummary(activeAlert?.delivery || []).cls}>{deliverySummary(activeAlert?.delivery || []).text}</span>
                    </div>
                  </div>
                  <div className="text-xs text-slate-300 font-normal">Auto-resuming autonomous monitoring in 6s...</div>
                </div>
              </div>
            )}
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl font-mono">
              <div className="text-xs text-slate-500 uppercase tracking-wider">Robot Camera FPS</div>
              <div className="text-lg font-bold text-slate-200 mt-1">{stats.fps} FPS</div>
            </div>
            <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl font-mono">
              <div className="text-xs text-slate-500 uppercase tracking-wider">Pi Link Latency</div>
              <div className="text-lg font-bold text-slate-200 mt-1">{stats.latency} ms</div>
            </div>
            <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl font-mono">
              <div className="text-xs text-slate-500 uppercase tracking-wider">Stability Rating</div>
              <div className="text-lg font-bold text-indigo-400 mt-1">{stats.postureScore}%</div>
            </div>
          </div>

          <div className="bg-slate-900 border border-slate-800 p-5 rounded-xl font-mono">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-bold text-slate-300 uppercase tracking-widest">Emergency Email Outbox</h2>
              <span className="text-xs text-emerald-400">
                {outbox.reduce((n, e) => n + e.delivery.filter(d => d.status === 'sent').length, 0)} Delivered
              </span>
            </div>
            {outbox.length === 0 ? (
              <div className="text-xs text-slate-500 py-2">
                No emergency alerts yet. When the robot detects a fall, each email and whether it was delivered appears here.
              </div>
            ) : (
              <div className="space-y-2.5">
                {outbox.map(em => (
                  <div key={em.id} className="bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs space-y-1">
                    <div className="flex justify-between items-center">
                      <span className="text-slate-200 font-medium">{em.subject}</span>
                      <span className="text-slate-500">{em.time}</span>
                    </div>
                    <div className="text-slate-400">{em.body}</div>
                    {em.delivery.length === 0 && (
                      <div className="text-amber-400">Nobody was alerted — no emergency contacts are saved on the robot.</div>
                    )}
                    {em.delivery.map(d => (
                      <div key={d.to} className="flex flex-wrap items-center gap-x-2 pt-1">
                        <span className="text-indigo-400 font-semibold">TO: {d.name} &lt;{d.to}&gt;</span>
                        {d.status === 'sent' && <span className="text-emerald-400 font-semibold">DELIVERED{d.method ? ` · ${d.method}` : ''}</span>}
                        {d.status === 'sending' && <span className="text-amber-400 font-semibold animate-pulse">SENDING…</span>}
                        {d.status === 'failed' && <span className="text-red-400 font-semibold">FAILED</span>}
                        {d.status === 'failed' && d.error && <span className="text-slate-500 w-full">{d.error}</span>}
                        {d.status === 'failed' && d.to.includes('@') && (
                          <a
                            href={`https://mail.google.com/mail/?view=cm&fs=1&to=${encodeURIComponent(d.to)}&su=${encodeURIComponent(em.subject)}&body=${encodeURIComponent(em.body)}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-block mt-1 px-2.5 py-1 bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-300 border border-indigo-500/30 rounded text-[11px] uppercase tracking-wider"
                          >
                            Send it yourself in Gmail
                          </a>
                        )}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="flex flex-col space-y-6">

          <div className="bg-slate-900 border border-slate-800 p-6 rounded-xl shadow-xl">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-bold text-slate-200">Robot Car Control</h2>
              {connected && robot ? (
                <span className="px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">ROBOT ONLINE</span>
              ) : (
                <span className="px-3 py-1 rounded-full text-xs font-semibold bg-slate-800 text-slate-500 border border-slate-700">ROBOT OFFLINE</span>
              )}
            </div>

            <div className="flex gap-2 mb-3">
              <input
                type="text"
                value={urlInput}
                onChange={(e) => setUrlInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !connected) toggleConnection(); }}
                placeholder="Raspberry Pi IP (e.g. 192.168.1.XX:8000)"
                className="flex-1 bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 font-mono"
              />
              <button
                onClick={toggleConnection}
                className={`px-3 py-2 rounded-lg text-xs font-semibold uppercase tracking-wider transition ${
                  connected
                    ? 'bg-red-600/20 hover:bg-red-600/30 text-red-400 border border-red-500/30'
                    : 'bg-emerald-600 hover:bg-emerald-500 text-white'
                }`}
              >
                {connected ? 'Disconnect' : 'Connect'}
              </button>
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs mb-4">
              <div className="bg-slate-950 border border-slate-800 rounded-lg p-2.5">
                <div className="text-slate-500 uppercase tracking-wider">Robot Camera</div>
                <div className={`font-bold mt-0.5 ${robot?.camera_running ? 'text-emerald-400' : 'text-slate-500'}`}>
                  {robot?.camera_running ? `ON · ${robot.fps} FPS` : 'OFF'}
                </div>
              </div>
              <div className="bg-slate-950 border border-slate-800 rounded-lg p-2.5">
                <div className="text-slate-500 uppercase tracking-wider">Autonomous</div>
                <div className={`font-bold mt-0.5 ${robot?.autonomous ? 'text-indigo-400' : 'text-slate-500'}`}>
                  {followLabel}
                </div>
              </div>
            </div>

            {robotProblems.length > 0 && (
              <div className="bg-amber-500/5 border border-amber-500/30 rounded-lg p-2.5 mb-4 text-[11px] text-amber-300 space-y-1">
                {robotProblems.map(p => <div key={p}>⚠ {p}</div>)}
              </div>
            )}

            <button
              onClick={toggleFollowing}
              disabled={!robot || robotBusy}
              className={`w-full py-3 font-semibold rounded-lg transition transform active:scale-[0.99] disabled:opacity-40 disabled:pointer-events-none text-sm tracking-wider uppercase mb-3 ${
                robot?.autonomous
                  ? 'bg-red-600/90 hover:bg-red-500 text-white'
                  : 'bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 shadow-lg shadow-indigo-500/10'
              }`}
            >
              {robot?.autonomous ? 'Pause Autonomous Following' : 'Start Autonomous Following'}
            </button>

            <div className="border-t border-slate-800 pt-3">
              <div className="flex items-center justify-between text-xs text-slate-400 mb-2">
                <span className="uppercase tracking-wider">Hold to Drive</span>
                <span className={robot?.gpio_available ? 'text-emerald-400' : 'text-amber-400'}>
                  {!robot ? 'Not Connected to Pi' : robot.gpio_available ? `Motors Ready · ${(robot.motor_action || 'stop').toUpperCase()}` : 'Motors Not Initialized'}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-1.5 text-xs select-none touch-none">
                <div />
                <DriveButton onStart={() => startDrive('forward')} onEnd={endDrive} disabled={!robot}>
                  ▲ Forward
                </DriveButton>
                <div />
                <DriveButton onStart={() => startDrive('left')} onEnd={endDrive} disabled={!robot}>
                  ◀ Left
                </DriveButton>
                <button
                  onClick={() => { endDrive(); sendRobotCommand('stop', true); }}
                  disabled={!robot}
                  className="py-2 bg-red-600/20 hover:bg-red-600 text-red-400 hover:text-white border border-red-500/30 rounded-lg font-semibold transition disabled:opacity-40"
                >
                  ■ Stop
                </button>
                <DriveButton onStart={() => startDrive('right')} onEnd={endDrive} disabled={!robot}>
                  Right ▶
                </DriveButton>
                <div />
                <DriveButton onStart={() => startDrive('backward')} onEnd={endDrive} disabled={!robot}>
                  ▼ Backward
                </DriveButton>
                <div />
              </div>
            </div>
          </div>

          <div className="bg-slate-900 border border-slate-800 p-6 rounded-xl shadow-xl flex flex-col justify-between">
            <div>
              <h2 className="text-lg font-bold text-slate-200 mb-1">Safety Routine Controller</h2>
              <p className="text-xs text-slate-400 mb-6">Send a test fall through the robot to check that your emergency contacts really get the email.</p>
            </div>
            <button
              onClick={simulateSensorSignal}
              disabled={status === 'EVALUATING'}
              className="w-full py-3.5 bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 font-semibold rounded-lg shadow-lg shadow-indigo-500/10 transition transform active:scale-[0.99] disabled:opacity-50 disabled:pointer-events-none text-sm tracking-wider uppercase"
            >
              {status === 'EVALUATING' ? 'Consulting Core AI...' : 'Simulate Fall Trajectory'}
            </button>
            {status === 'ALERT_TRIGGERED' && (
              <button
                onClick={() => {
                  setStatus('ONLINE');
                  setStats(prev => ({ ...prev, postureScore: 98 }));
                  addLog('Emergency alert cleared by operator.');
                }}
                className="w-full mt-2 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold rounded-lg transition text-xs tracking-wider uppercase"
              >
                Reset Emergency Alert
              </button>
            )}
          </div>

          <div className="bg-slate-900 border border-slate-800 p-6 rounded-xl shadow-xl flex-1 flex flex-col">
            <h2 className="text-sm font-bold text-slate-400 uppercase tracking-widest mb-3 font-mono">System Live Logs</h2>
            <div className="flex-1 bg-slate-950 border border-slate-850 p-4 rounded-lg font-mono text-xs text-slate-300 space-y-2.5 overflow-y-auto max-h-[220px] lg:max-h-none">
              {systemLog.map((log, index) => (
                <div key={index} className={`break-words ${index === 0 ? 'text-indigo-400 font-medium' : 'text-slate-500'}`}>
                  {log}
                </div>
              ))}
            </div>
          </div>

        </div>
      </main>
    </div>
  );
}
