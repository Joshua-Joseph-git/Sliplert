'use client';
import { useRef, useEffect, useState } from 'react';
import Link from 'next/link';

const DEFAULT_BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || '';

type RobotStatus = {
  autonomous: boolean;
  gpio_available: boolean;
  camera_running: boolean;
  person_detected: boolean;
  fps: number;
  body_angle?: number;
  posture_score?: number;
  last_fall?: {
    timestamp: string;
    fall_type: string;
    body_angle: number;
    confidence: number;
    called_contacts?: string[];
    called_phones?: string[];
  } | null;
};

export default function CameraDashboard() {
  const lastRobotFallRef = useRef<string | null>(null);
  const alertTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const backendUrlRef = useRef(DEFAULT_BACKEND_URL);
  const [status, setStatus] = useState('ONLINE');
  const [alertMessage, setAlertMessage] = useState('FALL PATTERN CONFIRMED BY MEDIAPIPE');
  const [alertPhones, setAlertPhones] = useState<string[]>([]);
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
    setSystemLog(prev => [`[${time}] ${message}`, ...prev.slice(0, 4)]);
  };

  const triggerFallSequence = (
    fallType: string,
    bodyAngle: number,
    calledContacts?: string[],
    calledPhones?: string[]
  ) => {
    setStatus('ALERT_TRIGGERED');
    setStats(prev => ({
      ...prev,
      postureScore: Math.max(0, Math.floor(100 - (bodyAngle || 80))),
    }));
    const who = calledContacts && calledContacts.length > 0
      ? calledContacts.join(', ')
      : 'saved emergency contacts';
    const phones = calledPhones || [];
    setAlertPhones(phones);
    setAlertMessage(`FALL DETECTED (${fallType.toUpperCase()}) — CALLING ${who.toUpperCase()}`);
    addLog(`CRITICAL: Fall detected (${fallType})! Stopping robot & alerting ${who}...`);

    if (phones.length > 0 && typeof window !== 'undefined') {
      const msg = encodeURIComponent('SlipLert Emergency Alert: A fall was just detected. Please check on your loved one immediately.');
      window.open(`sms:${phones[0]}?body=${msg}`, '_self');
    }

    if (alertTimerRef.current) clearTimeout(alertTimerRef.current);
    setTimeout(() => {
      addLog(`Emergency call & SMS dispatched to ${who}.`);
    }, 2000);

    alertTimerRef.current = setTimeout(() => {
      setStatus('ONLINE');
      setStats(prev => ({ ...prev, postureScore: 98 }));
      addLog('Call completed — resumed autonomous robot monitoring.');
    }, 6500);
  };

  useEffect(() => {
    backendUrlRef.current = backendUrl;
  }, [backendUrl]);

  useEffect(() => {
    const saved = window.localStorage.getItem('sliplert_backend_url');
    if (saved && !saved.includes('localhost')) {
      setBackendUrl(saved);
      setUrlInput(saved);
      setConnected(true);
    } else if (DEFAULT_BACKEND_URL) {
      setBackendUrl(DEFAULT_BACKEND_URL);
      setUrlInput(DEFAULT_BACKEND_URL);
      setConnected(true);
    }
    return () => {
      if (alertTimerRef.current) clearTimeout(alertTimerRef.current);
    };
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
        if (data.last_fall && data.last_fall.timestamp !== lastRobotFallRef.current) {
          lastRobotFallRef.current = data.last_fall.timestamp;
          triggerFallSequence(
            data.last_fall.fall_type || 'horizontal',
            data.last_fall.body_angle || 80,
            data.last_fall.called_contacts,
            data.last_fall.called_phones
          );
        }
      } catch {
        setRobot(null);
      }
    };
    checkRobot();
    const poll = setInterval(checkRobot, 1000);
    return () => clearInterval(poll);
  }, [backendUrl, connected]);

  const toggleConnection = async () => {
    if (connected) {
      try {
        await fetch(`${backendUrl}/robot/camera`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled: false }),
        });
      } catch {}
      setConnected(false);
      setRobot(null);
      setStats(prev => ({ ...prev, fps: 0 }));
      addLog('Disconnected from Raspberry Pi robot car.');
      return;
    }
    const clean = urlInput.trim().replace(/\/+$/, '');
    if (!clean) {
      addLog('Please enter your Raspberry Pi IP address first.');
      return;
    }
    const finalUrl = clean.startsWith('http') ? clean : `http://${clean}${clean.includes(':') ? '' : ':8000'}`;
    setBackendUrl(finalUrl);
    setUrlInput(finalUrl);
    window.localStorage.setItem('sliplert_backend_url', finalUrl);
    setConnected(true);
    setStreamKey(prev => prev + 1);
    try {
      await fetch(`${finalUrl}/robot/camera`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: true }),
      });
      await fetch(`${finalUrl}/robot/autonomous`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: true }),
      });
      const res = await fetch(`${finalUrl}/robot/status`, { signal: AbortSignal.timeout(3000) });
      if (res.ok) {
        const data = await res.json();
        setRobot(data);
        addLog(`Connected to robot car at ${finalUrl} — autonomous mode active.`);
      } else {
        addLog(`Could not reach ${finalUrl}.`);
      }
    } catch {
      addLog(`Could not reach ${finalUrl} — check that python main.py is running on the Pi.`);
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

  const sendRobotCommand = async (action: 'forward' | 'backward' | 'left' | 'right' | 'stop') => {
    if (!robot) return;
    try {
      const response = await fetch(`${backendUrl}/robot/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, speed: 55 }),
      });
      const data = await response.json();
      addLog(`Motor test: ${action.toUpperCase()} (${data.status || 'sent'}).`);
    } catch {
      addLog(`Failed to send ${action} command to robot.`);
    }
  };

  const simulateSensorSignal = async () => {
    setStatus('EVALUATING');
    addLog('Anomalous horizontal shift detected. Querying MediaPipe AI...');
    
    try {
      const response = await fetch('/api/verify-fall', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          simulate: true,
          backendUrl: backendUrlRef.current || 'http://localhost:8000',
          coordinates: { head: { x: 120, y: 480 }, feet: { x: 500, y: 490 } }
        }),
      });
      const data = await response.json();
      
      if (data.confirmedFall) {
        triggerFallSequence(
          data.fallType || 'simulated_fall',
          data.bodyAngle || 82,
          data.calledContacts,
          data.calledPhones
        );
      } else {
        setStatus('SAFE');
        addLog('False alarm. MediaPipe verified orientation as upright.');
        setTimeout(() => setStatus('ONLINE'), 3000);
      }
    } catch {
      setStatus('ONLINE');
      addLog('Network Error: Failed to reach AI endpoint.');
    }
  };

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
              <img
                key={streamKey}
                src={`${backendUrl}/video_feed?t=${streamKey}`}
                alt="Robot car camera perspective"
                className="w-full h-full object-cover"
              />
            ) : (
              <div className="absolute inset-0 bg-slate-900 flex flex-col items-center justify-center p-6 text-center">
                <div className="text-slate-300 text-sm font-semibold mb-2">
                  {connected && robot ? 'Robot Connected — Waiting for Pi Camera Stream' : 'Robot Car Camera Feed Offline'}
                </div>
                <div className="text-slate-500 text-xs max-w-md">
                  {connected && robot
                    ? 'Make sure the Pi ribbon camera is seated firmly and python main.py is running on the Raspberry Pi.'
                    : 'Enter your Raspberry Pi IP address (e.g. 192.168.1.XX:8000) in Robot Control on the right and click Connect.'}
                </div>
              </div>
            )}
            
            <div className="absolute top-4 left-4 bg-slate-950/80 backdrop-blur text-xs px-2.5 py-1 rounded text-indigo-400 font-mono tracking-widest border border-slate-800">
              REC // ROBOT_CAR_POV_FEED
            </div>
            
            {status === 'ALERT_TRIGGERED' && (
              <div className="absolute inset-0 bg-red-600/20 border-4 border-red-500 animate-pulse flex items-center justify-center">
                <div className="bg-slate-950/95 text-red-400 font-bold px-6 py-4 rounded-lg border border-red-500/50 text-center tracking-widest text-sm space-y-2">
                  <div>{alertMessage}</div>
                  {alertPhones.length > 0 && (
                    <div className="flex gap-2 justify-center pt-1">
                      <a
                        href={`tel:${alertPhones[0]}`}
                        className="px-3 py-1.5 bg-red-600 hover:bg-red-500 text-white rounded text-xs font-semibold uppercase"
                      >
                        Call {alertPhones[0]}
                      </a>
                      <a
                        href={`sms:${alertPhones[0]}?body=${encodeURIComponent('SlipLert Emergency Alert: A fall was detected! Please check on your loved one immediately.')}`}
                        className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded text-xs font-semibold uppercase"
                      >
                        Text {alertPhones[0]}
                      </a>
                    </div>
                  )}
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
                  {robot?.autonomous ? (robot?.person_detected ? 'FOLLOWING' : 'SEARCHING') : 'PAUSED'}
                </div>
              </div>
            </div>

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
                <span className="uppercase tracking-wider">Motor Drive Test</span>
                <span className={robot?.gpio_available ? 'text-emerald-400' : 'text-amber-400'}>
                  {robot?.gpio_available ? 'GPIO Motors Ready' : 'Not Connected to Pi'}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-1.5 text-xs">
                <div />
                <button
                  onClick={() => sendRobotCommand('forward')}
                  disabled={!robot}
                  className="py-2 bg-slate-950 hover:bg-indigo-600 border border-slate-800 rounded-lg font-semibold transition disabled:opacity-40"
                >
                  ▲ Fwd
                </button>
                <div />
                <button
                  onClick={() => sendRobotCommand('left')}
                  disabled={!robot}
                  className="py-2 bg-slate-950 hover:bg-indigo-600 border border-slate-800 rounded-lg font-semibold transition disabled:opacity-40"
                >
                  ◀ Left
                </button>
                <button
                  onClick={() => sendRobotCommand('stop')}
                  disabled={!robot}
                  className="py-2 bg-red-600/20 hover:bg-red-600 text-red-400 hover:text-white border border-red-500/30 rounded-lg font-semibold transition disabled:opacity-40"
                >
                  ■ Stop
                </button>
                <button
                  onClick={() => sendRobotCommand('right')}
                  disabled={!robot}
                  className="py-2 bg-slate-950 hover:bg-indigo-600 border border-slate-800 rounded-lg font-semibold transition disabled:opacity-40"
                >
                  Right ▶
                </button>
                <div />
                <button
                  onClick={() => sendRobotCommand('backward')}
                  disabled={!robot}
                  className="py-2 bg-slate-950 hover:bg-indigo-600 border border-slate-800 rounded-lg font-semibold transition disabled:opacity-40"
                >
                  ▼ Back
                </button>
                <div />
              </div>
            </div>
          </div>

          <div className="bg-slate-900 border border-slate-800 p-6 rounded-xl shadow-xl flex flex-col justify-between">
            <div>
              <h2 className="text-lg font-bold text-slate-200 mb-1">Safety Routine Controller</h2>
              <p className="text-xs text-slate-400 mb-6">Manually test the neural net evaluation sequence and emergency webhook relays.</p>
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
                <div key={index} className={`truncate ${index === 0 ? 'text-indigo-400 font-medium' : 'text-slate-500'}`}>
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
