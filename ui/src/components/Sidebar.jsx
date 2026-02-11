import React, { useState, useEffect, useRef } from 'react';

const AgentMonitor = ({ agent, status, onOpenGraph }) => {
    const { id, name, stats, goals } = agent;
    const isParanoid = stats.paranoia > 70;
    const [showGoals, setShowGoals] = useState(false);

    // Status Logic
    const currentStatus = status?.status || "IDLE";
    const statusDetails = status?.details || "";
    const phase = status?.phase || ""; // O, O, D, A
    const isActing = ["ACTING", "THINKING"].includes(currentStatus);
    const isWaiting = currentStatus === "WAITING_FOR_LOCK";

    // Determine status color
    let statusColor = "bg-gray-100 text-gray-500";
    if (currentStatus === "THINKING") statusColor = "bg-yellow-100 text-yellow-800 animate-pulse";
    if (currentStatus === "ACTING") statusColor = "bg-red-100 text-red-800 font-bold";
    if (currentStatus === "WAITING_FOR_LOCK") statusColor = "bg-blue-50 text-blue-600";
    if (currentStatus === "OBSERVING") statusColor = "bg-green-50 text-green-700";

    // Get top active goal
    const topGoal = goals?.find(g => g.active && g.progress < 100) || { description: "No active goals", progress: 0 };

    return (
        <div className={`p-1 bg-white border ${isParanoid ? "border-red-600" : "border-claw-border"} shadow-sharp flex flex-col justify-between h-[85px] group relative`}>
            {/* Header */}
            <div className="font-bold text-[10px] uppercase flex justify-between items-center bg-gray-100 px-1 select-none leading-none pt-1 pb-1">
                <span className="flex items-center gap-1">
                    <span className={`w-1 h-1 rounded-full ${isActing ? 'bg-red-600' : 'bg-gray-300'}`}></span>
                    /{id}/
                </span>
                {isParanoid && (
                    <span className="text-red-600 font-mono animate-pulse">!</span>
                )}
            </div>

            {/* OODA Indicators */}
            <div className="flex gap-0.5 px-1 py-0.5 bg-gray-50 border-b border-gray-100">
                {['O', 'O', 'D', 'A'].map((p, i) => {
                    const isActive = phase === p && (
                        (i === 0 && currentStatus === "OBSERVING") ||
                        (i === 1 && currentStatus === "ORIENTING") ||
                        (i === 2 && currentStatus === "DECIDING") ||
                        (i === 3 && (currentStatus === "ACTING" || currentStatus === "THINKING" || currentStatus === "WAITING_FOR_LOCK"))
                    );
                    return (
                        <div key={i} className={`flex-1 h-1 border border-gray-300 transition-colors ${isActive ? 'bg-indigo-600' : 'bg-gray-200'}`}></div>
                    );
                })}
            </div>

            {/* Conditional Display: Goals Overlay OR Stats/Status */}
            {showGoals ? (
                <div className="absolute inset-0 top-[22px] bottom-[18px] bg-white z-10 p-1 text-[8px] leading-tight font-mono overflow-y-auto border-b border-gray-200">
                    <div className="font-bold text-blue-800 mb-0.5">CURRENT OBJECTIVE:</div>
                    <div className="text-gray-800">{topGoal.description}</div>
                    <div className="mt-1 w-full bg-gray-200 h-1">
                        <div className="bg-blue-600 h-1" style={{ width: `${topGoal.progress}%` }}></div>
                    </div>
                </div>
            ) : (
                <>
                    {/* Stats OR Status Message */}
                    {isActing || isWaiting ? (
                        <div className={`flex-1 flex flex-col justify-center items-center text-[9px] font-mono leading-tight px-1 text-center ${statusColor}`}>
                            <span className="font-bold">{currentStatus}</span>
                            <span className="text-[7px] opacity-75 leading-none mt-0.5 truncate w-full">{statusDetails}</span>
                        </div>
                    ) : (
                        <div className="text-[9px] grid grid-cols-3 gap-0.5 px-0.5 font-mono leading-tight flex-1 pt-1">
                            <div className="flex flex-col">
                                <span className="text-gray-400 text-[7px]">LOY</span>
                                <span className={stats.loyalty_to_chairman < 30 ? "text-red-600 font-bold" : ""}>
                                    {stats.loyalty_to_chairman}%
                                </span>
                            </div>
                            <div className="flex flex-col">
                                <span className="text-gray-400 text-[7px]">CNF</span>
                                <span>{stats.confidence}%</span>
                            </div>
                            <div className="flex flex-col">
                                <span className="text-gray-400 text-[7px]">PAR</span>
                                <span className={stats.paranoia > 50 ? "text-red-600 font-bold" : ""}>
                                    {stats.paranoia}%
                                </span>
                            </div>
                        </div>
                    )}
                </>
            )}

            {/* Footer Buttons */}
            <div className="absolute bottom-0 right-0 flex hidden group-hover:flex">
                <button
                    onMouseEnter={() => setShowGoals(true)}
                    onMouseLeave={() => setShowGoals(false)}
                    className="p-0.5 bg-gray-100 border-l border-t border-gray-300 hover:bg-white text-[7px] font-bold text-gray-700 w-6"
                >
                    OBJ
                </button>
                <button
                    onClick={() => onOpenGraph(id)}
                    className="p-0.5 bg-gray-100 border-l border-t border-gray-300 hover:bg-white text-[7px] font-bold text-blue-900 w-6"
                >
                    MAP
                </button>
            </div>
        </div>
    );
};

const MissionStatus = ({ heartbeatStats, systemState }) => {
    // Format Uptime
    const uptime = heartbeatStats?.uptime || 0;
    const hours = Math.floor(uptime / 3600).toString().padStart(2, '0');
    const minutes = Math.floor((uptime % 3600) / 60).toString().padStart(2, '0');
    const seconds = (uptime % 60).toString().padStart(2, '0');

    // Tension Bar
    const tension = systemState?.tension || 0;
    const [isPaused, setIsPaused] = useState(false);

    // Toggle Function
    const toggleSystem = async () => {
        try {
            const newState = !isPaused; // If paused (true), we want to active (true/start). Wait, logic inverse?
            // API: active=true means START. active=false means STOP.
            // visual isPaused=true means STOPPED.
            // So if paused, we want to START (active=true).
            const activeParam = isPaused;

            await fetch(`http://localhost:8000/admin/toggle_heartbeat?active=${activeParam}`, { method: 'POST' });
            setIsPaused(!isPaused);
        } catch (e) {
            console.error("Failed to toggle system:", e);
        }
    };



    // Conch Info
    const conchOwner = systemState?.conch?.owner;
    const conchExpires = systemState?.conch?.expires_in;

    return (
        <div className="p-2 bg-gray-200 border-b border-gray-400 font-mono text-[9px]">
            <div className="grid grid-cols-2 gap-2 mb-2">
                <div className="bg-white border-2 border-claw-border p-1 shadow-inner relative overflow-hidden">
                    <div className="text-[7px] text-gray-400 uppercase mb-1">MISSION_CLOCK</div>
                    <div className="text-lg font-bold text-gray-800 leading-none font-mono">
                        {hours}:{minutes}<span className="animate-pulse">:{seconds}</span>
                    </div>
                    <div className="absolute top-0 right-0 w-8 h-8 opacity-5 border-l border-b border-black transform rotate-45 translate-x-4 -translate-y-4"></div>
                </div>
                <div className="bg-white border-2 border-claw-border p-1 shadow-inner overflow-hidden">
                    <div className="text-[7px] text-gray-400 uppercase flex justify-between">
                        <span>ENTROPY</span>
                        <span>{tension}%</span>
                    </div>
                    {/* Retro "Dial" Meter */}
                    <div className="w-full bg-gray-100 h-3 mt-1 border border-gray-400 relative">
                        <div className="absolute inset-0 flex">
                            {[...Array(10)].map((_, i) => (
                                <div key={i} className="flex-1 border-r border-gray-300 opacity-30"></div>
                            ))}
                        </div>
                        <div
                            className={`h-full transition-all duration-300 ${tension > 70 ? 'bg-red-600 shadow-[0_0_5px_rgba(220,38,38,0.5)]' : 'bg-green-600 shadow-[0_0_5px_rgba(22,163,74,0.5)]'}`}
                            style={{ width: `${tension}%` }}
                        ></div>
                        <div className="absolute top-0 left-[70%] w-px h-full bg-red-400 z-10 opacity-50"></div>
                    </div>
                </div>
            </div>

            {conchOwner ? (
                <div className="bg-red-50 border-2 border-red-500 p-1 text-center animate-pulse shadow-sharp cursor-pointer hover:bg-red-100" onClick={toggleSystem}>
                    <span className="font-bold text-red-800 text-[8px]">⚠ CHANNEL LOCKED: {conchOwner}</span>
                    <span className="block text-[7px] text-red-600 mt-0.5">CLICK TO FORCE HALT</span>
                </div>
            ) : (
                <div
                    onClick={toggleSystem}
                    className={`border-2 p-1 text-center shadow-sharp cursor-pointer transition-all ${isPaused ? 'bg-red-900 border-red-600' : 'bg-green-50 border-green-500 hover:bg-green-100'}`}
                >
                    {isPaused ? (
                        <div className="flex flex-col items-center">
                            <span className="text-[9px] font-bold text-red-100 animate-pulse">⚠ SYSTEM HALTED ⚠</span>
                            <span className="text-[7px] text-red-300">CLICK TO RESUME</span>
                        </div>
                    ) : (
                        <span className="text-[8px] font-bold text-green-800 opacity-75">SYSTEM NOMINAL // CHANNEL OPEN</span>
                    )}
                </div>
            )}
        </div>
    );
};

const HardwareMonitor = ({ activity = {} }) => {
    const [ledStatus, setLedStatus] = useState({ disk: false, llm: false, net: false, ego: false, phys: false, heart: false });

    // HEART Pulse
    useEffect(() => {
        const interval = setInterval(() => {
            setLedStatus(prev => ({ ...prev, heart: true }));
            setTimeout(() => setLedStatus(prev => ({ ...prev, heart: false })), 150);
        }, 2000);
        return () => clearInterval(interval);
    }, []);

    useEffect(() => {
        if (activity.disk) {
            setLedStatus(prev => ({ ...prev, disk: true }));
            const t = setTimeout(() => setLedStatus(prev => ({ ...prev, disk: false })), 100);
            return () => clearTimeout(t);
        }
    }, [activity.disk]);

    useEffect(() => {
        if (activity.llm) {
            setLedStatus(prev => ({ ...prev, llm: true }));
            const t = setTimeout(() => setLedStatus(prev => ({ ...prev, llm: false })), 150);
            return () => clearTimeout(t);
        }
    }, [activity.llm]);

    useEffect(() => {
        if (activity.net) {
            setLedStatus(prev => ({ ...prev, net: true }));
            const t = setTimeout(() => setLedStatus(prev => ({ ...prev, net: false })), 100);
            // Don't log every net pulse to BIOS, too noisy
            return () => clearTimeout(t);
        }
    }, [activity.net]);

    useEffect(() => {
        if (activity.ego) {
            setLedStatus(prev => ({ ...prev, ego: true }));
            const t = setTimeout(() => setLedStatus(prev => ({ ...prev, ego: false })), 200);
            return () => clearTimeout(t);
        }
    }, [activity.ego]);

    useEffect(() => {
        if (activity.phys) {
            setLedStatus(prev => ({ ...prev, phys: true }));
            const t = setTimeout(() => setLedStatus(prev => ({ ...prev, phys: false })), 100);
            return () => clearTimeout(t);
        }
    }, [activity.phys]);

    return (
        <div className="p-2 bg-gray-300 border-b border-gray-400 grid grid-cols-3 gap-y-2 gap-x-1 font-mono text-[8px]">
            {/* ROW 1 */}
            <div className="flex flex-col items-center gap-1">
                <div className={`w-3 h-1.5 border border-black transition-colors ${ledStatus.disk ? 'bg-amber-400 shadow-[0_0_5px_rgba(251,191,36,0.8)]' : 'bg-amber-950'}`}></div>
                <span className="text-gray-600">DISK</span>
            </div>
            <div className="flex flex-col items-center gap-1">
                <div className={`w-3 h-1.5 border border-black transition-colors ${ledStatus.llm ? 'bg-cyan-400 shadow-[0_0_5px_rgba(34,211,238,0.8)]' : 'bg-cyan-950'}`}></div>
                <span className="text-gray-600">NEURAL</span>
            </div>
            <div className="flex flex-col items-center gap-1">
                <div className={`w-3 h-1.5 border border-black transition-colors ${ledStatus.ego ? 'bg-fuchsia-500 shadow-[0_0_5px_rgba(217,70,239,0.8)]' : 'bg-fuchsia-950'}`}></div>
                <span className="text-gray-600">EGO</span>
            </div>

            {/* ROW 2 */}
            <div className="flex flex-col items-center gap-1">
                <div className={`w-3 h-1.5 border border-black transition-colors ${ledStatus.phys ? 'bg-blue-400 shadow-[0_0_5px_rgba(96,165,250,0.8)]' : 'bg-blue-950'}`}></div>
                <span className="text-gray-600">PHYS</span>
            </div>
            <div className="flex flex-col items-center gap-1">
                <div className={`w-3 h-1.5 border border-black transition-colors ${ledStatus.net ? 'bg-green-400 shadow-[0_0_5px_rgba(74,222,128,0.8)]' : 'bg-green-950'}`}></div>
                <span className="text-gray-600">UPLINK</span>
            </div>
            <div className="flex flex-col items-center gap-1">
                <div className={`w-3 h-1.5 border border-black transition-colors ${ledStatus.heart ? 'bg-red-600 shadow-[0_0_5px_rgba(220,38,38,0.8)]' : 'bg-red-950'}`}></div>
                <span className="text-gray-600">CORE</span>
            </div>
        </div>
    );
};

const WatchdogTerminal = ({ logs = [], statusText, activeAgents = {}, heartbeatStats }) => {
    const bottomRef = useRef(null);
    const containerRef = useRef(null);
    const isAtBottomRef = useRef(true); // Default to true (auto-scroll enabled)

    // Check scroll position on user interaction
    const handleScroll = () => {
        if (containerRef.current) {
            const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
            // Tolerance of 50px to be more forgiving
            const atBottom = scrollHeight - (scrollTop + clientHeight) < 50;
            isAtBottomRef.current = atBottom;
        }
    };

    const [spinner, setSpinner] = useState(0);
    const frames = ['|', '/', '-', '\\'];

    useEffect(() => {
        const interval = setInterval(() => {
            setSpinner(s => (s + 1) % 4);
        }, 100);
        return () => clearInterval(interval);
    }, []);

    useEffect(() => {
        // Use scrollTop instead of scrollIntoView to prevent parent container scrolling
        if (isAtBottomRef.current && containerRef.current) {
            containerRef.current.scrollTop = containerRef.current.scrollHeight;
        }
    }, [logs, activeAgents, heartbeatStats]); // Trigger on any content change

    // Format logs for display
    // We'll just take the raw log string and try to parse the module if possible for coloring
    const formatLog = (log, idx) => {
        if (!log || typeof log !== 'string') return null;
        // Regex to extract parts: [TIMESTAMP] [MODULE] > MESSAGE
        const match = log.match(/\[(.*?)\] \[(.*?)\] > (.*)/);
        if (match) {
            const [_, timestamp, module, message] = match;
            let moduleColor = "text-black";
            if (module === "SYSTEM") moduleColor = "text-red-700 font-bold";
            if (module === "SIMULATION") moduleColor = "text-blue-800 font-bold";
            if (module === "BIOS") moduleColor = "text-indigo-600 font-mono italic";
            if (module.includes("AGENT")) moduleColor = "text-green-700 font-bold";

            return (
                <div key={idx} className="whitespace-nowrap hover:bg-gray-100">
                    <span className="text-gray-500 mr-1">[{timestamp.split('T')[1]?.split('.')[0] || "00:00:00"}]</span>
                    <span className={`${moduleColor} mr-1`}>[{module}]</span>
                    <span className="text-black">{message}</span>
                </div>
            );
        }
        return <div key={idx} className="whitespace-nowrap hover:bg-gray-100">{log}</div>;
    };

    return (
        <div className="flex flex-col h-48 bg-white border-2 border-claw-border shadow-sharp font-mono text-[9px] mb-2 select-none">
            {/* Header */}
            <div className="bg-gray-200 border-b-2 border-claw-border p-1 flex justify-between items-center text-[10px] font-bold text-gray-700 uppercase tracking-wider">
                <span>[ TERMINAL_WATCHDOG ]</span>
                <span>{frames[spinner]} {Object.keys(activeAgents || {}).length > 0 ? "BUSY" : "IDLE"}</span>
            </div>

            {/* Log Area */}
            <div
                ref={containerRef}
                onScroll={handleScroll}
                className="flex-1 overflow-y-auto p-1 scrollbar-hide flex flex-col gap-0.5"
            >
                {(logs || []).length === 0 && <div className="text-gray-400 italic">{">>"} INITIALIZING SYSTEM WATCHER...</div>}

                {/* Show last 50 logs */}
                {(logs || []).slice(-50).map((log, i) => formatLog(log, i))}
                <div ref={bottomRef} />
            </div>

            {/* Footer / Status Line */}
            <div className="bg-white border-t border-gray-300 p-1 text-[8px] text-gray-500 flex justify-between uppercase">
                <span>MEM: {heartbeatStats?.mem || "64MB"} OK</span>
                <span>UPTIME: {heartbeatStats?.uptime || 0}S</span>
            </div>
        </div>
    );
};

const Sidebar = ({ agents, posts, statusText, activeAgents, systemLogs, heartbeatStats, agentStatuses, systemState, activity, onOpenGraph }) => {
    const [spinnerIndex, setSpinnerIndex] = useState(0);
    const [isPulsing, setIsPulsing] = useState(false);
    const diaryRef = useRef(null);
    const diaryIsAtBottomRef = useRef(true);
    const spinnerFrames = ['|', '/', '-', '\\'];

    const handleDiaryScroll = () => {
        if (diaryRef.current) {
            const { scrollTop, scrollHeight, clientHeight } = diaryRef.current;
            const atBottom = scrollHeight - (scrollTop + clientHeight) < 50;
            diaryIsAtBottomRef.current = atBottom;
        }
    };

    useEffect(() => {
        const spinnerInterval = setInterval(() => {
            setSpinnerIndex(prev => (prev + 1) % 4);
        }, 100);
        return () => clearInterval(spinnerInterval);
    }, []);

    useEffect(() => {
        if (diaryRef.current && diaryIsAtBottomRef.current) {
            diaryRef.current.scrollTop = diaryRef.current.scrollHeight;
        }
    }, [posts]);

    // Handle pulse animation on heartbeat
    useEffect(() => {
        setIsPulsing(true);
        const timer = setTimeout(() => setIsPulsing(false), 800);
        return () => clearTimeout(timer);
    }, [heartbeatStats?.uptime]);

    const handleDownload = () => {
        const logData = {
            session_manifest: {
                generator: "IRON_COUNCIL_V2.0_RESEARCH_CORE",
                timestamp: new Date().toISOString(),
                session_id: Math.floor(Math.random() * 1000000)
            },
            agent_data: agents.map(a => ({
                identity: { name: a.name, id: a.id },
                soul_state: a.full_soul || a, // Use full extraction if available, else fallback
                final_trust_scores: a.relationships
            })),
            council_thread: posts.map(p => {
                if (p.type === 'user') return { role: "CHAIRMAN", content: p.content };
                if (p.type === 'agent_post') return {
                    role: p.data.name,
                    content: p.data.public_text,
                    hidden_thought: p.data.hidden_text,
                    stats_at_time: p.data.stats
                };
                return null;
            }).filter(Boolean),
            subconscious_repository: posts.filter(p => p.type === 'dream' || p.type === 'dream_stream').map(p => {
                if (p.type === 'dream') return p.data;
                return { agent: p.agentName, content: p.content };
            }),
            backend_terminal_logs: systemLogs.filter(log => {
                const blacklist = ["System nominal.", "Integrity check passed.", "Watching...", "Ping.", "Cycle complete."];
                return !blacklist.some(b => log.includes(b));
            })
        };

        const blob = new Blob([JSON.stringify(logData, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `IC_RESEARCH_LOG_${Date.now()}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };

    const dreamPosts = posts.filter(p => p.type === 'dream' || p.type === 'dream_stream');

    return (
        <div className="w-80 h-screen flex flex-col bg-[#d1d5db] border-r-2 border-claw-border shadow-2xl z-50 overflow-hidden relative">
            {/* Header / Brand */}
            <div className="bg-[#1e293b] text-white p-2 flex justify-between items-center border-b-2 border-black flex-none">
                <span className="text-[10px] font-bold tracking-tighter">COUNCIL_MONITOR_v2.0</span>
                <div className="flex items-center gap-1.5">
                    <div className={`w-1.5 h-1.5 rounded-full ${isPulsing ? 'bg-cyan-400 shadow-[0_0_5px_rgba(34,211,238,0.8)]' : 'bg-cyan-900'} transition-all duration-300`}></div>
                    <span className="text-[9px] font-mono text-cyan-400">{statusText.includes("READY") ? "CONNECTED" : "ACTIVE"}</span>
                </div>
            </div>

            {/* Scrollable Container */}
            <div className="flex-1 overflow-y-auto scrollbar-hide flex flex-col">

                {/* 0. HARDWARE STATUS */}
                <HardwareMonitor activity={activity} />

                {/* 0. MISSION STATUS */}
                <MissionStatus heartbeatStats={heartbeatStats} systemState={systemState} />

                {/* 1. AGENT_MONITORS Area */}
                <div className="p-3 border-b border-gray-400 bg-gray-200">
                    <div className="text-[10px] font-bold text-gray-700 uppercase tracking-widest mb-2 flex justify-between items-center">
                        <span>// AGENT_MONITORS</span>
                        <button onClick={() => onOpenGraph(null)} className="text-[8px] color-[#af0a0f] hover:underline">FULL_MATRIX</button>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                        {agents.map(agent => (
                            <AgentMonitor
                                key={agent.id}
                                agent={agent}
                                status={agentStatuses?.[agent.id]}
                                onOpenGraph={onOpenGraph}
                            />
                        ))}
                    </div>
                </div>

                {/* 2. SOCIAL_MATRIX Area */}
                <div className="p-3 border-b border-gray-400 bg-gray-200 flex-none">
                    <div className="text-[10px] font-bold text-gray-700 uppercase tracking-widest mb-2">
                        <span>// SOCIAL_MATRIX</span>
                    </div>
                    <div className="bg-white border-2 border-claw-border p-1 shadow-sharp">
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
                                                <td key={b.id} className={`text-center font-bold ${score > 0 ? 'text-green-600' : score < 0 ? 'text-red-700' : 'text-gray-400'}`}>
                                                    {score > 0 ? '+' : ''}{score}
                                                </td>
                                            );
                                        })}
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>

                {/* 3. SUBCONSCIOUS_LOG Area */}
                <div className="p-2 flex flex-col flex-none h-64">
                    <div className="text-[10px] font-bold text-gray-600 uppercase tracking-widest mb-2 border-b border-gray-400 pb-0.5">
                        // SUBCONSCIOUS_LOG
                    </div>
                    <div
                        ref={diaryRef}
                        onScroll={handleDiaryScroll}
                        className="flex-1 bg-white border border-claw-border p-2 shadow-sharp overflow-y-auto font-serif text-xs leading-tight diary-scroll"
                    >
                        {dreamPosts.length === 0 && (
                            <div className="text-gray-400 italic text-[10px]">Ready for neural capture...</div>
                        )}
                        {dreamPosts.map((post, idx) => {
                            if (post.type === 'dream') {
                                return post.data.map((entry, i) => (
                                    <div key={`${idx}-${i}`} className="mb-3 border-b border-gray-100 pb-1 last:border-0 last:pb-0">
                                        <div className="font-mono text-[9px] font-bold text-indigo-900 uppercase mb-0.5">{entry.agent_name}</div>
                                        <div className="italic text-gray-800 leading-relaxed border-l-2 border-indigo-50 pl-2">
                                            "{entry.entry}"
                                        </div>
                                    </div>
                                ));
                            }
                            return (
                                <div key={idx} className="mb-3 border-b border-gray-100 pb-1 last:border-0 last:pb-0">
                                    <div className="font-mono text-[9px] font-bold text-indigo-900 uppercase flex justify-between items-center mb-0.5">
                                        <span>{post.agentName}</span>
                                        {post.isStreaming && <span className="text-[8px] animate-pulse">RECEIVING... {spinnerFrames[spinnerIndex]}</span>}
                                    </div>
                                    <div className="italic text-gray-800 leading-relaxed border-l-2 border-indigo-50 pl-2">
                                        {post.content}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>

                {/* 4. SYSTEM_STATUS & DOWNLOAD Area */}
                <div className="p-2 border-t border-claw-border bg-gray-100 mt-auto flex flex-col gap-2 flex-none">
                    {/* REPLACED: Watchdog Terminal */}
                    <WatchdogTerminal
                        logs={systemLogs.filter(log => {
                            const blacklist = ["System nominal.", "Integrity check passed.", "Watching...", "Ping.", "Cycle complete."];
                            return !blacklist.some(b => log.includes(b));
                        })}
                        statusText={statusText}
                        activeAgents={activeAgents}
                        heartbeatStats={heartbeatStats}
                    />

                    <button
                        onClick={handleDownload}
                        className="w-full bg-[#af0a0f] text-white font-bold py-1 px-2 text-[10px] uppercase tracking-widest shadow-sharp hover:bg-red-800 transition-colors border border-black active:shadow-none translate-x-[1px] translate-y-[1px] active:translate-x-[2px] active:translate-y-[2px]"
                    >
                        DOWNLOAD_LOG.EXE
                    </button>
                </div>

            </div>
        </div>
    );
};

export default Sidebar;
