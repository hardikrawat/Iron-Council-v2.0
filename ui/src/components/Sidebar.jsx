import React, { useState, useEffect, useRef } from 'react';

const AgentMonitor = ({ agent, onOpenGraph }) => {
    const { id, name, stats } = agent;
    const isParanoid = stats.paranoia > 70;

    return (
        <div className={`p-1 bg-white border ${isParanoid ? "border-red-600" : "border-claw-border"} shadow-sharp flex flex-col justify-between h-[65px] group relative`}>
            <div className="font-bold text-[10px] uppercase flex justify-between items-center bg-gray-100 px-1 select-none leading-none pt-1 pb-1">
                <span>/{id}/</span>
                {isParanoid && (
                    <span className="text-red-600 font-mono animate-pulse">!</span>
                )}
            </div>
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
            <button
                onClick={() => onOpenGraph(id)}
                className="absolute bottom-0 right-0 p-0.5 bg-gray-100 border-l border-t border-gray-300 hover:bg-white text-[7px] font-bold text-blue-900 hidden group-hover:block"
            >
                MAP
            </button>
        </div>
    );
};

const WatchdogTerminal = ({ logs = [], statusText, activeAgents = {} }) => {
    const bottomRef = useRef(null);
    const [spinner, setSpinner] = useState(0);
    const frames = ['|', '/', '-', '\\'];

    useEffect(() => {
        const interval = setInterval(() => {
            setSpinner(s => (s + 1) % 4);
        }, 100);
        return () => clearInterval(interval);
    }, []);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [logs]);

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
            <div className="flex-1 overflow-y-auto p-1 scrollbar-hide flex flex-col gap-0.5">
                {(logs || []).length === 0 && <div className="text-gray-400 italic">{">>"} INITIALIZING SYSTEM WATCHER...</div>}

                {/* Show last 50 logs */}
                {(logs || []).slice(-50).map((log, i) => formatLog(log, i))}
                <div ref={bottomRef} />
            </div>

            {/* Footer / Status Line */}
            <div className="bg-white border-t border-gray-300 p-1 text-[8px] text-gray-500 flex justify-between uppercase">
                <span>MEM: 64MB OK</span>
                <span>UPTIME: {Math.floor(performance.now() / 1000)}s</span>
            </div>
        </div>
    );
};

const Sidebar = ({ agents, posts, statusText, activeAgents, systemLogs, onOpenGraph }) => {
    const [spinnerIndex, setSpinnerIndex] = useState(0);
    const diaryRef = useRef(null);
    const spinnerFrames = ['|', '/', '-', '\\'];

    useEffect(() => {
        const spinnerInterval = setInterval(() => {
            setSpinnerIndex(prev => (prev + 1) % 4);
        }, 100);
        return () => clearInterval(spinnerInterval);
    }, []);

    useEffect(() => {
        if (diaryRef.current) {
            diaryRef.current.scrollTop = diaryRef.current.scrollHeight;
        }
    }, [posts]);

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
            backend_terminal_logs: systemLogs
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
            <div className="bg-[#1e293b] text-white p-2 flex justify-between items-center border-b-2 border-black">
                <span className="text-[10px] font-bold tracking-tighter">COUNCIL_MONITOR_v2.0</span>
                <span className="text-[9px] font-mono text-cyan-400">{statusText.includes("READY") ? "CONNECTED" : "ACTIVE"}</span>
            </div>

            {/* 1. AGENT_MONITORS Area */}
            <div className="p-3 border-b border-gray-400 bg-gray-200">
                <div className="text-[10px] font-bold text-gray-700 uppercase tracking-widest mb-2 flex justify-between items-center">
                    <span>// AGENT_MONITORS</span>
                    <button onClick={() => onOpenGraph(null)} className="text-[8px] color-[#af0a0f] hover:underline">FULL_MATRIX</button>
                </div>
                <div className="grid grid-cols-2 gap-2">
                    {agents.map(agent => (
                        <AgentMonitor key={agent.id} agent={agent} onOpenGraph={onOpenGraph} />
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
            <div className="flex-1 p-2 flex flex-col overflow-hidden">
                <div className="text-[10px] font-bold text-gray-600 uppercase tracking-widest mb-2 border-b border-gray-400 pb-0.5">
                    // SUBCONSCIOUS_LOG
                </div>
                <div
                    ref={diaryRef}
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
                <WatchdogTerminal logs={systemLogs} statusText={statusText} activeAgents={activeAgents} />

                <button
                    onClick={handleDownload}
                    className="w-full bg-[#af0a0f] text-white font-bold py-1 px-2 text-[10px] uppercase tracking-widest shadow-sharp hover:bg-red-800 transition-colors border border-black active:shadow-none translate-x-[1px] translate-y-[1px] active:translate-x-[2px] active:translate-y-[2px]"
                >
                    DOWNLOAD_LOG.EXE
                </button>
            </div>
        </div>
    );
};

export default Sidebar;
