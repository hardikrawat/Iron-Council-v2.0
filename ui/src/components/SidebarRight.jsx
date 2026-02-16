import React, { useState, useEffect, useRef } from 'react';
import LLMUsagePanel from './LLMUsagePanel';
import { formatDreamDiary, downloadTxtFile } from '../utils/exportUtils';

const matrixBlinkStyle = `
@keyframes matrix-blink-pos {
  0%, 100% { border-color: #000; }
  50% { border-color: #22c55e; box-shadow: 0 0 10px #22c55e; }
}

@keyframes matrix-blink-neg {
  0%, 100% { border-color: #000; }
  50% { border-color: #ef4444; box-shadow: 0 0 10px #ef4444; }
}

@keyframes float-up-fade {
  0% { transform: translateY(0); opacity: 1; }
  100% { transform: translateY(-15px); opacity: 0; }
}

.floating-delta {
  position: absolute;
  top: -5px;
  right: -5px;
  font-size: 8px;
  font-weight: bold;
  pointer-events: none;
  animation: float-up-fade 1.5s ease-out forwards;
}

.matrix-blink-positive {
  animation: matrix-blink-pos 1.5s ease-in-out !important;
}

.matrix-blink-negative {
  animation: matrix-blink-neg 1.5s ease-in-out !important;
}
`;

const StratagemPlotter = ({ goalHistory, agents }) => {
    const canvasRef = useRef(null);
    const colors = ['#dc2626', '#2563eb', '#059669', '#7c3aed', '#d97706'];

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const dpr = window.devicePixelRatio || 1;
        const w = canvas.width;
        const h = canvas.height;

        ctx.fillStyle = '#f8fafc';
        ctx.fillRect(0, 0, w, h);

        ctx.strokeStyle = '#cbd5e1';
        ctx.lineWidth = 0.5 * dpr;
        for (let i = 1; i < 10; i++) {
            ctx.beginPath();
            ctx.moveTo(0, (h / 10) * i);
            ctx.lineTo(w, (h / 10) * i);
            ctx.stroke();
            ctx.beginPath();
            ctx.moveTo((w / 10) * i, 0);
            ctx.lineTo((w / 10) * i, h);
            ctx.stroke();
        }

        agents.forEach((agent, i) => {
            const history = goalHistory[agent.name] || [];
            if (history.length < 2) return;

            ctx.strokeStyle = colors[i % colors.length];
            ctx.lineWidth = 2 * dpr;
            ctx.beginPath();

            const xStep = w / 20;
            history.forEach((val, idx) => {
                const x = idx * xStep;
                const y = h - (val / 100) * h;
                if (idx === 0) ctx.moveTo(x, y);
                else ctx.lineTo(x, y);
            });
            ctx.stroke();

            history.forEach((val, idx) => {
                const x = idx * xStep;
                const y = h - (val / 100) * h;
                ctx.fillStyle = colors[i % colors.length];
                ctx.fillRect(x - 1, y - 1, 3, 3);
            });
        });
    }, [goalHistory, agents]);

    return (
        <div className="bg-white border-2 border-claw-border p-1 shadow-sharp overflow-hidden flex-1 h-[90px]">
            <div className="text-[6px] text-gray-500 font-bold mb-1 flex justify-between items-center uppercase h-3">
                <span className="truncate">STRATAGEM_PLOTTER</span>
            </div>
            <canvas ref={canvasRef} width={140} height={70} className="w-full h-[68px]" style={{ imageRendering: 'pixelated' }} />
        </div>
    );
};

const ProtocolLedger = ({ verdicts }) => {
    return (
        <div className="bg-[#fefce8] border-2 border-[#854d0e] p-1 shadow-sharp h-[90px] font-mono text-[6px] relative overflow-hidden flex-1 protocol-ledger">
            <div className="absolute inset-0 opacity-10 pointer-events-none" style={{ backgroundImage: 'radial-gradient(#000 1px, transparent 0)', backgroundSize: '4px 4px' }}></div>
            <div className="text-[7px] font-bold text-[#854d0e] border-b border-[#a16207] mb-0.5 flex justify-between items-center whitespace-nowrap overflow-hidden">
                <span className="truncate">SYSTEM_PROTOCOL_LEDGER</span>
                <span className="animate-pulse">● PRINTING</span>
            </div>
            <div className="flex flex-col gap-0.5 h-[72px] overflow-y-auto no-scrollbar">
                {verdicts.length === 0 && <div className="text-gray-400 italic">No logs.</div>}
                {verdicts.map((v, i) => (
                    <div key={i} className="border-b border-dashed border-gray-200 pb-0.5 last:border-0 leading-tight">
                        <div className="flex justify-between font-bold flex-wrap gap-x-1">
                            <span className="text-black uppercase truncate">{v.agent[0]}: {v.delta > 0 ? '+' : ''}{v.delta}%</span>
                            <span className="text-[#a16207] truncate">{v.goal.slice(0, 10)}...</span>
                        </div>
                        <div className="text-gray-700 italic truncate w-full">"{v.details}"</div>
                    </div>
                ))}
            </div>
        </div>
    );
};

const SidebarRight = ({ agents, posts, heartbeatStats, activity, verdicts, goalHistory, statusText }) => {
    const [spinnerIndex, setSpinnerIndex] = useState(0);
    const [isPulsing, setIsPulsing] = useState(false);
    const diaryRef = useRef(null);
    const diaryIsAtBottomRef = useRef(true);
    const [matrixBlink, setMatrixBlink] = useState('none');
    const [activeDeltas, setActiveDeltas] = useState({});
    const prevTrustsRef = useRef({});
    const spinnerFrames = ['|', '/', '-', '\\'];

    const handleDiaryScroll = () => {
        if (diaryRef.current) {
            const { scrollTop, scrollHeight, clientHeight } = diaryRef.current;
            diaryIsAtBottomRef.current = scrollHeight - (scrollTop + clientHeight) < 50;
        }
    };

    useEffect(() => {
        const spinnerInterval = setInterval(() => setSpinnerIndex(prev => (prev + 1) % 4), 100);
        return () => clearInterval(spinnerInterval);
    }, []);

    useEffect(() => {
        if (diaryRef.current && diaryIsAtBottomRef.current) {
            diaryRef.current.scrollTop = diaryRef.current.scrollHeight;
        }
    }, [posts]);

    useEffect(() => {
        setIsPulsing(true);
        const timer = setTimeout(() => setIsPulsing(false), 800);
        return () => clearTimeout(timer);
    }, [heartbeatStats?.uptime]);

    useEffect(() => {
        let blink = 'none';
        const currentTrusts = {};
        let hasChange = false;
        const newDeltas = { ...activeDeltas };

        agents.forEach(agent => {
            currentTrusts[agent.id] = {};
            const prevAgentTrusts = prevTrustsRef.current[agent.id] || {};
            Object.entries(agent.relationships || {}).forEach(([target, rel]) => {
                const score = rel.trust_score ?? 0;
                currentTrusts[agent.id][target] = score;
                if (prevAgentTrusts.hasOwnProperty(target)) {
                    const prevScore = prevAgentTrusts[target];
                    if (score !== prevScore) {
                        const delta = score - prevScore;
                        const key = `${agent.id}-${target}`;
                        newDeltas[key] = {
                            val: delta > 0 ? `+${delta}` : delta,
                            color: delta > 0 ? 'text-green-600' : 'text-red-600',
                            ts: Date.now()
                        };
                        if (delta > 0) blink = 'positive';
                        else if (blink !== 'positive') blink = 'negative';
                        hasChange = true;
                    }
                }
            });
        });

        if (hasChange) {
            setMatrixBlink(blink);
            setActiveDeltas(newDeltas);
            const timer = setTimeout(() => setMatrixBlink('none'), 1500);
            prevTrustsRef.current = currentTrusts;
            return () => clearTimeout(timer);
        }
        prevTrustsRef.current = currentTrusts;

        const cleanup = setInterval(() => {
            const now = Date.now();
            setActiveDeltas(prev => {
                const next = { ...prev };
                let deltaCleaned = false;
                Object.entries(next).forEach(([k, v]) => {
                    if (now - v.ts > 2000) {
                        delete next[k];
                        deltaCleaned = true;
                    }
                });
                return deltaCleaned ? next : prev;
            });
        }, 5000);
        return () => clearInterval(cleanup);
    }, [agents]);

    const handleExportDiary = () => {
        const content = formatDreamDiary(posts);
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        downloadTxtFile(content, `iron_council_diary_${timestamp}.txt`);
    };

    const dreamPosts = posts.filter(p => p.type === 'dream' || p.type === 'dream_stream' || p.type === 'dream_session_marker');

    return (
        <div className="w-80 h-screen flex flex-col bg-[#d1d5db] border-l-2 border-claw-border shadow-2xl z-50 overflow-hidden relative">
            <div className="bg-[#1e293b] text-white p-2 flex justify-between items-center border-b-2 border-black flex-none">
                <span className="text-[10px] font-bold tracking-tighter">INTELLIGENCE_MONITOR_v2.0</span>
                <div className="flex items-center gap-1.5">
                    <div className={`w-1.5 h-1.5 rounded-full ${isPulsing ? 'bg-indigo-400 shadow-[0_0_5px_rgba(129,140,248,0.8)]' : 'bg-indigo-900'} transition-all duration-300`}></div>
                    <span className="text-[9px] font-mono text-indigo-400">SESSION_SYNC</span>
                </div>
            </div>

            <div className="flex-1 overflow-y-auto scrollbar-hide flex flex-col">
                <LLMUsagePanel activity={activity} />

                <div className="px-3 py-1 bg-gray-200 flex gap-2">
                    <StratagemPlotter goalHistory={goalHistory} agents={agents} />
                    <ProtocolLedger verdicts={verdicts} />
                </div>

                <div className="p-3 border-b border-gray-400 bg-gray-200 flex-none">
                    <div className="text-[10px] font-bold text-gray-700 uppercase tracking-widest mb-2">
                        <span>// SOCIAL_MATRIX</span>
                    </div>
                    <div className={`bg-white border-2 border-claw-border p-1 shadow-sharp ${matrixBlink === 'positive' ? 'matrix-blink-positive' : matrixBlink === 'negative' ? 'matrix-blink-negative' : ''}`}>
                        <style>{matrixBlinkStyle}</style>
                        <table className="w-full text-[9px] font-mono">
                            <thead>
                                <tr className="border-b-2 border-black">
                                    <th className="text-left py-1 px-1">ID</th>
                                    {agents.map(a => <th key={a.id} className="text-center bg-gray-50">{a.id.split('_')[1]?.[0] || a.id[0]}</th>)}
                                </tr>
                            </thead>
                            <tbody>
                                {agents.map(a => (
                                    <tr key={a.id} className="border-b border-gray-200 last:border-0 hover:bg-blue-50">
                                        <td className="font-bold text-gray-600 p-1">{a.id.split('_')[1] || a.id}</td>
                                        {agents.map(b => {
                                            if (a.id === b.id) return <td key={b.id} className="text-center text-gray-300 bg-gray-50">-</td>;
                                            const score = a.relationships?.[b.name]?.trust_score ?? 0;
                                            return (
                                                <td key={b.id} className={`text-center font-bold relative ${score > 0 ? 'text-green-600' : score < 0 ? 'text-red-700' : 'text-gray-400'}`}>
                                                    {score > 0 ? '+' : ''}{score}
                                                    {activeDeltas[`${a.id}-${b.name}`] && (
                                                        <span key={activeDeltas[`${a.id}-${b.name}`].ts} className={`floating-delta ${activeDeltas[`${a.id}-${b.name}`].color}`}>
                                                            {activeDeltas[`${a.id}-${b.name}`].val}
                                                        </span>
                                                    )}
                                                </td>
                                            );
                                        })}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>

                <div className="p-2 flex flex-col flex-none h-64">
                    <div className="text-[10px] font-bold text-gray-600 uppercase tracking-widest mb-2 border-b border-gray-400 pb-0.5 flex justify-between items-center">
                        <span>// SUBCONSCIOUS_LOG</span>
                        <button
                            onClick={handleExportDiary}
                            className="text-[8px] text-[#af0a0f] hover:underline hover:cursor-pointer font-mono"
                        >
                            EXPORT_TXT
                        </button>
                    </div>
                    <div ref={diaryRef} onScroll={handleDiaryScroll} className="flex-1 bg-white border border-claw-border p-2 shadow-sharp overflow-y-auto font-serif text-xs leading-tight diary-scroll">
                        {dreamPosts.length === 0 && <div className="text-gray-400 italic text-[10px]">Ready for neural capture...</div>}
                        {dreamPosts.map((post, idx) => {
                            if (post.type === 'dream_session_marker') {
                                return (
                                    <div key={idx} className="my-4 border-y-2 border-indigo-200 py-1 bg-indigo-50/30 text-center">
                                        <div className="text-[9px] font-bold text-indigo-700 uppercase tracking-tighter">
                                            --- NEURAL LINK SESSION: {new Date(post.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} ---
                                        </div>
                                    </div>
                                );
                            }
                            if (post.type === 'dream') {
                                const entries = Array.isArray(post.data) ? post.data : [post.data];
                                return entries.map((entry, i) => (
                                    <div key={`${idx}-${i}`} className="mb-3 border-b border-gray-100 pb-1 last:border-0 last:pb-0">
                                        <div className="font-mono text-[9px] font-bold text-indigo-900 uppercase mb-0.5">{entry.agent_name}</div>
                                        <div className="italic text-gray-800 leading-relaxed border-l-2 border-indigo-50 pl-2">"{entry.entry}"</div>
                                    </div>
                                ));
                            }
                            return (
                                <div key={idx} className="mb-3 border-b border-gray-100 pb-1 last:border-0 last:pb-0">
                                    <div className="font-mono text-[9px] font-bold text-indigo-900 uppercase flex justify-between items-center mb-0.5">
                                        <span>{post.agentName || post.data?.name || "Unknown"}</span>
                                        {post.isStreaming && <span className="text-[8px] animate-pulse">RECEIVING... {spinnerFrames[spinnerIndex]}</span>}
                                    </div>
                                    <div className="italic text-gray-800 leading-relaxed border-l-2 border-indigo-50 pl-2">{post.content}</div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default SidebarRight;
