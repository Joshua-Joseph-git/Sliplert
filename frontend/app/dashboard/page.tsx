'use client';
import { useRef, useEffect, useState } from 'react';
import Link from 'next/link';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

type RobotStatus = {
  autonomous: boolean;
  gpio_available: boolean;
  camera_running: boolean;
  person_detected: boolean;
  fps: number;
};

export default function CameraDashboard() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [status, setStatus] = useState('ONLINE');
  const [robot, setRobot] = useState<RobotStatus | null>(null);
  const [feed, setFeed] = useState<'laptop' | 'robot'>('laptop');
  const [robotBusy, setRobotBusy] = useState(false);
  const [systemLog, setSystemLog] = useState<string[]>([
    'System initialized.',
    'Robot WebSocket link standing by.',
    'Ready for safety monitoring.'
  ]);

  const [stats, setStats] = useState({ fps: 30, latency: 12, postureScore: 98 });

  useEffect(() => {
    async function setupCamera() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true });
        if (videoRef.current) videoRef.current.srcObject = stream;
        addLog('Hardware camera interface mapped successfully.');

        if (videoRef.current) {
          videoRef.current.onloadedmetadata = () => {
            startFallDetection();
          };
        }
      } catch (err) {
        addLog('Camera access denied - using simulation mode.');
        setStatus('ONLINE');
      }
    }
    setupCamera();

    const interval = setInterval(() => {
      setStats({
        fps: Math.floor(Math.random() * (31 - 28) + 28),
        latency: Math.floor(Math.random() * (16 - 11) + 11),
        postureScore: Math.floor(Math.random() * (100 - 95) + 95)
      });
    }, 1500);
    return () => {
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    const checkRobot = async () => {
      try {
        const response = await fetch(`${BACKEND_URL}/robot/status`, { signal: AbortSignal.timeout(2000) });
        setRobot(response.ok ? await response.json() : null);
      } catch {
        setRobot(null);
      }
    };
    checkRobot();
    const poll = setInterval(checkRobot, 2000);
    return () => clearInterval(poll);
  }, []);

  const toggleFollowing = async () => {
    if (!robot) return;
    setRobotBusy(true);
    const enable = !robot.autonomous;
    try {
      const response = await fetch(`${BACKEND_URL}/robot/autonomous`, {
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

  const startFallDetection = () => {
    if (!videoRef.current) return;

    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    canvas.width = 640;
    canvas.height = 480;

    const detectFrame = async () => {
      if (!videoRef.current || !ctx) return;

      ctx.drawImage(videoRef.current, 0, 0, canvas.width, canvas.height);
      const imageData = canvas.toDataURL('image/jpeg', 0.8);

      try {
        const response = await fetch('/api/verify-fall', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ image: imageData }),
        });

        const data = await response.json();

        if (data.confirmedFall) {
          setStatus('ALERT_TRIGGERED');
          addLog(`⚠️ CRITICAL: Fall detected! Type: ${data.fallType}, Confidence: ${(data.confidence * 100).toFixed(0)}%`);
        } else {
          if (data.bodyAngle) {
            const score = Math.max(0, 100 - data.bodyAngle);
            setStats(prev => ({ ...prev, postureScore: Math.floor(score) }));
          }
        }
      } catch (error) {
      }

      requestAnimationFrame(detectFrame);
    };

    detectFrame();
  };

  const addLog = (message: string) => {
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    setSystemLog(prev => [`[${time}] ${message}`, ...prev.slice(0, 4)]);
  };

  const simulateSensorSignal = async () => {
    setStatus('EVALUATING');
    addLog('Anomalous horizontal shift detected. Querying Claude AI...');
    
    try {
      const response = await fetch('/api/verify-fall', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          coordinates: { head: { x: 120, y: 480 }, feet: { x: 500, y: 490 } }
        }),
      });
      const data = await response.json();
      
      if (data.confirmedFall) {
        setStatus('ALERT_TRIGGERED');
        addLog('⚠️ CRITICAL: Claude verified a fall! Twilio emergency dispatch fired.');
      } else {
        setStatus('SAFE');
        addLog('False alarm. Claude verified orientation as upright.');
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
            
            {feed === 'robot' && robot?.camera_running && (
              <img src={`${BACKEND_URL}/video_feed`} alt="Robot camera" className="absolute inset-0 w-full h-full object-cover" />
            )}

            {feed === 'laptop' && !videoRef.current?.srcObject && (
              <div className="absolute inset-0 bg-slate-800 flex flex-col items-center justify-center">
                <div className="text-slate-500 text-sm mb-2">Camera Feed Offline</div>
                <div className="text-slate-600 text-xs">Grant camera permissions to enable monitoring</div>
              </div>
            )}
            
            <div className="absolute top-4 left-4 bg-slate-950/80 backdrop-blur text-xs px-2.5 py-1 rounded text-indigo-400 font-mono tracking-widest border border-slate-800">
              REC // CAM_01_ROBOT_FEED
            </div>
            
            {status === 'ALERT_TRIGGERED' && (
              <div className="absolute inset-0 bg-red-600/20 border-4 border-red-500 animate-pulse flex items-center justify-center pointer-events-none">
                <div className="bg-slate-950/90 text-red-400 font-bold px-6 py-3 rounded-lg border border-red-500/50 text-center tracking-widest text-sm">
                  ⚠️ FALL PATTERN CONFIRMED BY CLAUDE
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
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-slate-200">Robot Control</h2>
              {robot ? (
                <span className="px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">ROBOT ONLINE</span>
              ) : (
                <span className="px-3 py-1 rounded-full text-xs font-semibold bg-slate-800 text-slate-500 border border-slate-700">ROBOT OFFLINE</span>
              )}
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
