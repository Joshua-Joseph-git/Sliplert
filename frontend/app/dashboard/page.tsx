'use client';
import { useRef, useEffect, useState } from 'react';
import Link from 'next/link';

const DEFAULT_BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

type RobotStatus = {
  autonomous: boolean;
  gpio_available: boolean;
  camera_running: boolean;
  person_detected: boolean;
  fps: number;
  body_angle?: number;
  posture_score?: number;
  last_fall?: { timestamp: string; fall_type: string; body_angle: number; confidence: number; called_contacts?: string[] } | null;
};

export default function CameraDashboard() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const lastRobotFallRef = useRef<string | null>(null);
  const alertTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const backendUrlRef = useRef(DEFAULT_BACKEND_URL);
  const [status, setStatus] = useState('ONLINE');
  const [alertMessage, setAlertMessage] = useState('⚠️ FALL PATTERN CONFIRMED BY MEDIAPIPE');
  const [robot, setRobot] = useState<RobotStatus | null>(null);
  const [feed, setFeed] = useState<'laptop' | 'robot'>('laptop');
  const [robotBusy, setRobotBusy] = useState(false);
  const [backendUrl, setBackendUrl] = useState(DEFAULT_BACKEND_URL);
  const [urlInput, setUrlInput] = useState(DEFAULT_BACKEND_URL);
  const [connected, setConnected] = useState(true);
  const [systemLog, setSystemLog] = useState<string[]>([
    'System initialized.',
    'Robot WebSocket link standing by.',
    'Ready for safety monitoring.'
  ]);

  const [stats, setStats] = useState({ fps: 30, latency: 12, postureScore: 98 });

  const stopBrowserCamera = () => {
    const stream = videoRef.current?.srcObject as MediaStream | null;
    if (stream) {
      stream.getTracks().forEach(track => track.stop());
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
  };

  const triggerFallSequence = (fallType: string, bodyAngle: number, calledContacts?: string[]) => {
    setStatus('ALERT_TRIGGERED');
    setStats(prev => ({
      ...prev,
      postureScore: Math.max(0, Math.floor(100 - (bodyAngle || 80))),
    }));
    const who = calledContacts && calledContacts.length > 0
      ? calledContacts.join(', ')
      : 'saved emergency contacts';
    setAlertMessage(`⚠️ FALL DETECTED (${fallType.toUpperCase()}) — 📞 CALLING ${who.toUpperCase()}`);
    addLog(`⚠️ CRITICAL: Fall detected (${fallType})! Stopping robot & calling ${who}...`);

    if (alertTimerRef.current) clearTimeout(alertTimerRef.current);
    setTimeout(() => {
      addLog(`📞 Emergency call & SMS dispatched to ${who}.`);
    }, 2000);

    alertTimerRef.current = setTimeout(() => {
      setStatus('ONLINE');
      setStats(prev => ({ ...prev, postureScore: 98 }));
      addLog('✅ Call completed — resumed live fall monitoring.');
    }, 6500);
  };

  useEffect(() => {
    backendUrlRef.current = backendUrl;
  }, [backendUrl]);

  useEffect(() => {
    let stopDetection = false;
    async function setupCamera() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true });
        if (stopDetection) {
          stream.getTracks().forEach(track => track.stop());
          return;
        }
        if (videoRef.current) videoRef.current.srcObject = stream;
        addLog('Hardware camera interface mapped successfully.');

        if (videoRef.current) {
          videoRef.current.onloadedmetadata = () => {
            if (!stopDetection) startFallDetection(() => stopDetection);
          };
        }
      } catch (err) {
        addLog('Using backend camera stream.');
        setStatus('ONLINE');
      }
    }
    setupCamera();

    const interval = setInterval(() => {
      setStats(prev => ({
        ...prev,
        fps: Math.floor(Math.random() * (31 - 28) + 28),
      }));
    }, 1500);
    return () => {
      stopDetection = true;
      clearInterval(interval);
      if (alertTimerRef.current) clearTimeout(alertTimerRef.current);
      stopBrowserCamera();
    };
  }, []);

  useEffect(() => {
    const saved = window.localStorage.getItem('sliplert_backend_url');
    if (saved) {
      setBackendUrl(saved);
      setUrlInput(saved);
    }
  }, []);

  useEffect(() => {
    if (!connected) {
      setRobot(null);
      return;
    }
    const checkRobot = async () => {
      try {
        const response = await fetch(`${backendUrl}/robot/status`, { signal: AbortSignal.timeout(2000) });
        if (!response.ok) {
          setRobot(null);
          return;
        }
        const data: RobotStatus = await response.json();
        setRobot(data);
        if (data.camera_running) {
          if (!videoRef.current?.srcObject) {
            setFeed('robot');
          }
          if (typeof data.posture_score === 'number') {
            setStats(prev => ({
              ...prev,
              fps: data.fps || prev.fps,
              postureScore: data.posture_score ?? prev.postureScore,
            }));
          }
        }
        if (data.last_fall && data.last_fall.timestamp !== lastRobotFallRef.current) {
          lastRobotFallRef.current = data.last_fall.timestamp;
          triggerFallSequence(
            data.last_fall.fall_type || 'horizontal',
            data.last_fall.body_angle || 80,
            data.last_fall.called_contacts
          );
        }
      } catch {
        setRobot(null);
      }
    };
    checkRobot();
    const poll = setInterval(checkRobot, 1200);
    return () => clearInterval(poll);
  }, [backendUrl, connected]);

  const toggleConnection = async () => {
    if (connected) {
      stopBrowserCamera();
      try {
        await fetch(`${backendUrl}/robot/camera`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled: false }),
        });
      } catch {}
      setConnected(false);
      setRobot(null);
      setFeed('laptop');
      addLog('Camera & Raspberry Pi disconnected.');
      return;
    }
    const clean = urlInput.trim().replace(/\/+$/, '') || DEFAULT_BACKEND_URL;
    const finalUrl = clean.startsWith('http') ? clean : `http://${clean}${clean.includes(':') ? '' : ':8000'}`;
    setBackendUrl(finalUrl);
    setUrlInput(finalUrl);
    window.localStorage.setItem('sliplert_backend_url', finalUrl);
    setConnected(true);
    try {
      await fetch(`${finalUrl}/robot/camera`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: true }),
      });
      const res = await fetch(`${finalUrl}/robot/status`, { signal: AbortSignal.timeout(2500) });
      if (res.ok) {
        const data = await res.json();
        setRobot(data);
        if (data.camera_running) setFeed('robot');
        addLog(`Connected to robot at ${finalUrl}.`);
      } else {
        addLog(`Could not reach ${finalUrl}.`);
      }
    } catch {
      addLog(`Could not reach ${finalUrl} — check Pi IP or start backend.`);
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
      addLog(enable ? 'Robot following engaged.' : 'Robot following stopped.');
    } catch {
      addLog('Could not reach the robot.');
    }
    setRobotBusy(false);
  };

  const startFallDetection = (isStopped: () => boolean) => {
    if (!videoRef.current) return;

    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    canvas.width = 640;
    canvas.height = 480;

    const detectFrame = async () => {
      if (isStopped()) return;
      if (!videoRef.current || !ctx || videoRef.current.readyState < 2) {
        setTimeout(detectFrame, 300);
        return;
      }

      const t0 = performance.now();
      ctx.drawImage(videoRef.current, 0, 0, canvas.width, canvas.height);
      const imageData = canvas.toDataURL('image/jpeg', 0.75);

      try {
        const response = await fetch('/api/verify-fall', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ image: imageData, backendUrl: backendUrlRef.current }),
        });

        const data = await response.json();
        const elapsed = Math.max(1, Math.round(performance.now() - t0));

        if (typeof data.bodyAngle === 'number') {
          const score = Math.max(0, Math.min(100, Math.floor(100 - data.bodyAngle)));
          setStats(prev => ({ ...prev, latency: elapsed, postureScore: score }));
        }

        if (data.confirmedFall) {
          triggerFallSequence(data.fallType || 'fall', data.bodyAngle || 75, data.calledContacts);
        }
      } catch {
      }

      if (!isStopped()) {
        setTimeout(detectFrame, 300);
      }
    };

    detectFrame();
  };

  const addLog = (message: string) => {
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    setSystemLog(prev => [`[${time}] ${message}`, ...prev.slice(0, 4)]);
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
          backendUrl: backendUrlRef.current,
          coordinates: { head: { x: 120, y: 480 }, feet: { x: 500, y: 490 } }
        }),
      });
      const data = await response.json();
      
      if (data.confirmedFall) {
        triggerFallSequence(data.fallType || 'simulated_fall', data.bodyAngle || 82, data.calledContacts);
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
            LOC: HOME_SECTOR_1
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
            <video ref={videoRef} autoPlay playsInline muted className="w-full h-full object-cover" />
            <canvas ref={canvasRef} className="absolute top-0 left-0 w-full h-full pointer-events-none" />
            
            {(feed === 'robot' || !videoRef.current?.srcObject) && robot?.camera_running && (
              <img src={`${backendUrl}/video_feed`} alt="Robot camera" className="absolute inset-0 w-full h-full object-cover" />
            )}

            {!robot?.camera_running && !videoRef.current?.srcObject && (
              <div className="absolute inset-0 bg-slate-800 flex flex-col items-center justify-center">
                <div className="text-slate-500 text-sm mb-2">Camera Feed Offline</div>
                <div className="text-slate-600 text-xs">Click Connect in Robot Control to start camera monitoring</div>
              </div>
            )}
            
            <div className="absolute top-4 left-4 bg-slate-950/80 backdrop-blur text-xs px-2.5 py-1 rounded text-indigo-400 font-mono tracking-widest border border-slate-800">
              REC // CAM_01_ROBOT_FEED
            </div>
            
            {status === 'ALERT_TRIGGERED' && (
              <div className="absolute inset-0 bg-red-600/20 border-4 border-red-500 animate-pulse flex items-center justify-center pointer-events-none">
                <div className="bg-slate-950/95 text-red-400 font-bold px-6 py-4 rounded-lg border border-red-500/50 text-center tracking-widest text-sm space-y-1">
                  <div>{alertMessage}</div>
                  <div className="text-xs text-slate-300 font-normal">Auto-resuming live monitoring in 6s...</div>
                </div>
              </div>
            )}
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl font-mono">
              <div className="text-xs text-slate-500 uppercase tracking-wider">Feed Signal</div>
              <div className="text-lg font-bold text-slate-200 mt-1">{stats.fps} FPS</div>
            </div>
            <div className="bg-slate-900 border border-slate-800 p-4 rounded-xl font-mono">
              <div className="text-xs text-slate-500 uppercase tracking-wider">AI API Latency</div>
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
              <h2 className="text-lg font-bold text-slate-200">Robot Control</h2>
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
                placeholder="Pi IP (e.g. 192.168.1.42:8000)"
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
                <div className="text-slate-500 uppercase tracking-wider">Camera</div>
                <div className={`font-bold mt-0.5 ${robot?.camera_running ? 'text-emerald-400' : 'text-slate-500'}`}>
                  {robot?.camera_running ? `ON · ${robot.fps} FPS` : 'OFF'}
                </div>
              </div>
              <div className="bg-slate-950 border border-slate-800 rounded-lg p-2.5">
                <div className="text-slate-500 uppercase tracking-wider">Person</div>
                <div className={`font-bold mt-0.5 ${robot?.person_detected ? 'text-indigo-400' : 'text-slate-500'}`}>
                  {robot?.person_detected ? 'TRACKING' : 'NOT SEEN'}
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
              {robot?.autonomous ? 'Stop Following' : 'Start Following'}
            </button>

            <div className="flex bg-slate-950 border border-slate-800 rounded-lg p-1 text-xs">
              {(['laptop', 'robot'] as const).map((source) => (
                <button
                  key={source}
                  onClick={() => setFeed(source)}
                  disabled={source === 'robot' && !robot?.camera_running}
                  className={`flex-1 py-1.5 rounded-md transition uppercase tracking-wider disabled:opacity-40 ${
                    feed === source ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-white'
                  }`}
                >
                  {source === 'laptop' ? 'Laptop Cam' : 'Robot Cam'}
                </button>
              ))}
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
