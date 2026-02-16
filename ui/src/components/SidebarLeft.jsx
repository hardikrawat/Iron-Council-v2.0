import React, { useState, useEffect, useRef } from 'react';
import { formatChatHistory, downloadTxtFile } from '../utils/exportUtils';

const AgentMonitor = ({ agent, status, onOpenGraph, activity = {} }) => {
    const { id, name, stats, goals } = agent;
    const isParanoid = stats.paranoia > 70;
    const [showGoals, setShowGoals] = useState(false);

    const currentStatus = status?.status || "IDLE";
    const statusDetails = status?.details || "";
    const phase = status?.phase || "";
    const isActing = ["ACTING", "THINKING", "OBSERVING", "ORIENTING", "DECIDING", "FEELING", "RECHARGING", "RECALLING", "DREAMING"].includes(currentStatus) || (phase && phase !== "");
    const isWaiting = currentStatus === "WAITING_FOR_LOCK";

    const isLlmAgent = activity.llm_busy && activity.llm_agent === id;
    const llmStep = isLlmAgent ? activity.llm_step : null;

    let statusColor = "bg-gray-100 text-gray-500";
    if (currentStatus === "THINKING") statusColor = "bg-yellow-100 text-yellow-800 animate-pulse";
    if (currentStatus === "ACTING") statusColor = "bg-red-100 text-red-800 font-bold";
    if (currentStatus === "WAITING_FOR_LOCK") statusColor = "bg-blue-50 text-blue-600";
    if (currentStatus === "OBSERVING") statusColor = "bg-green-50 text-green-700";
    if (currentStatus === "ORIENTING") statusColor = "bg-gray-100 text-gray-600";
    if (currentStatus === "DECIDING") statusColor = "bg-gray-100 text-gray-600";
    if (currentStatus === "RECALLING") statusColor = "bg-purple-50 text-purple-700 animate-pulse";
    if (currentStatus === "FEELING") statusColor = "bg-pink-50 text-pink-700 animate-pulse";
    if (currentStatus === "RECHARGING") statusColor = "bg-amber-50 text-amber-700";
    if (currentStatus === "DREAMING") statusColor = "bg-indigo-100 text-indigo-800 animate-pulse";

    if (currentStatus === "RELATIONSHIP_UPDATE" || currentStatus === "STAT_UPDATE") statusColor = "bg-blue-50 text-blue-700 border-blue-200 border animate-pulse";
    if (currentStatus === "NARRATIVE_VERDICT") statusColor = "bg-amber-50 text-[#854d0e] border-[#854d0e] border";

    const topGoal = goals?.find(g => g.active && g.progress < 100) || { description: "No active goals", progress: 0 };

    return (
        <div className={`p-1 bg-white border ${isParanoid ? "border-red-600" : "border-claw-border"} shadow-sharp flex flex-col justify-between h-[85px] group relative`}>
            <div className="font-bold text-[10px] uppercase flex justify-between items-center bg-gray-100 px-1 select-none leading-none pt-1 pb-1">
                <span className="flex items-center gap-1">
                    <span className={`w-1 h-1 rounded-full ${isActing ? 'bg-red-600' : 'bg-gray-300'}`}></span>
                    /{id}/
                </span>
                {isParanoid && (
                    <span className="text-red-600 font-mono animate-pulse">!</span>
                )}
            </div>

            {(() => {
                const PIPELINE = [
                    { label: 'OBS', statuses: ['OBSERVING', 'FEELING'] },
                    { label: 'ORI', statuses: ['ORIENTING', 'RECHARGING'] },
                    { label: 'DEC', statuses: ['DECIDING'] },
                    { label: 'RCL', statuses: ['RECALLING'] },
                    { label: 'GEN', statuses: ['THINKING', 'WAITING_FOR_LOCK'] },
                    { label: 'OUT', statuses: ['ACTING'] },
                ];
                const activeIdx = currentStatus === 'IDLE' ? -1 :
                    PIPELINE.findIndex(s => s.statuses.includes(currentStatus));
                return (
                    <div className="px-1 py-0.5 bg-gray-50 border-b border-gray-100">
                        <div className="flex gap-px">
                            {PIPELINE.map((stage, i) => {
                                const isFilled = activeIdx >= 0 && i <= activeIdx;
                                const isCurrent = i === activeIdx;
                                return (
                                    <div key={i} className="flex-1 flex flex-col items-center">
                                        <div className={`w-full h-1 border transition-all duration-300 ${isFilled
                                            ? `bg-amber-600 border-amber-700 ${isCurrent ? 'animate-pulse' : ''}`
                                            : 'bg-gray-200 border-gray-300'
                                            }`} />
                                        <span className={`text-[5px] font-mono leading-none mt-px select-none ${isFilled ? 'text-amber-800 font-bold' : 'text-gray-400'
                                            }`}>{stage.label}</span>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                );
            })()}

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
                    {isActing || isWaiting ? (
                        <div className={`flex-1 flex flex-col justify-center items-center text-[9px] font-mono leading-tight px-1 text-center ${statusColor}`}>
                            <span className="font-bold flex items-center gap-1">
                                {llmStep && <span className="text-[7px] bg-red-600 text-white px-0.5 rounded-sm animate-pulse">{llmStep}</span>}
                                {currentStatus}
                            </span>
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
    const uptime = heartbeatStats?.uptime || 0;
    const hours = Math.floor(uptime / 3600).toString().padStart(2, '0');
    const minutes = Math.floor((uptime % 3600) / 60).toString().padStart(2, '0');
    const seconds = (uptime % 60).toString().padStart(2, '0');

    const tension = systemState?.tension || 0;
    const isPaused = heartbeatStats?.running === false;

    const toggleSystem = async () => {
        try {
            const activeParam = isPaused;
            await fetch(`http://localhost:8000/admin/toggle_heartbeat?active=${activeParam}`, { method: 'POST' });
        } catch (e) {
            console.error("Failed to toggle system:", e);
        }
    };

    const releaseConch = async () => {
        try {
            await fetch(`http://localhost:8000/admin/force_release_conch`, { method: 'POST' });
        } catch (e) {
            console.error("Failed to release conch:", e);
        }
    };

    const conchOwner = systemState?.conch?.owner;

    return (
        <div className="p-2 bg-gray-200 border-b border-gray-400 font-mono text-[9px]">
            <div className="grid grid-cols-2 gap-2 mb-2">
                <div className="bg-white border-2 border-claw-border p-1 shadow-inner relative overflow-hidden">
                    <div className="text-[7px] text-gray-400 uppercase mb-1">MISSION_CLOCK</div>
                    <div className="text-lg font-bold text-gray-800 leading-none font-mono">
                        {hours}:{minutes}<span className="animate-pulse">:{seconds}</span>
                    </div>
                </div>
                <div className="bg-white border-2 border-claw-border p-1 shadow-inner overflow-hidden">
                    <div className="text-[7px] text-gray-400 uppercase flex justify-between">
                        <span>ENTROPY</span>
                        <span>{tension}%</span>
                    </div>
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
                    </div>
                </div>
            </div>

            {conchOwner ? (
                <div className="bg-red-50 border-2 border-red-500 p-1 text-center animate-pulse shadow-sharp cursor-pointer hover:bg-red-100" onClick={releaseConch}>
                    <span className="font-bold text-red-800 text-[8px]">⚠ CHANNEL LOCKED: {conchOwner}</span>
                    <span className="block text-[7px] text-red-600 mt-0.5">CLICK TO FORCE RELEASE</span>
                </div>
            ) : (
                <div onClick={toggleSystem} className={`border-2 p-1 text-center shadow-sharp cursor-pointer transition-all ${isPaused ? 'bg-red-900 border-red-600' : 'bg-green-50 border-green-500 hover:bg-green-100'}`}>
                    {isPaused ? (
                        <div className="flex flex-col items-center">
                            <span className="text-[9px] font-bold text-red-100 animate-pulse">⚠ SYSTEM HALTED ⚠</span>
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

    useEffect(() => {
        if (activity.disk) {
            setLedStatus(prev => ({ ...prev, disk: true }));
            const duration = activity.disk_save ? 400 : 100;
            const t = setTimeout(() => setLedStatus(prev => ({ ...prev, disk: false })), duration);
            return () => clearTimeout(t);
        }
    }, [activity.disk]);

    useEffect(() => {
        if (!activity.heart) return;
        setLedStatus(prev => ({ ...prev, heart: true }));
        const tension = activity.tension || 0;
        const duration = Math.max(50, 200 - (tension * 1.5));
        const timeout = setTimeout(() => setLedStatus(prev => ({ ...prev, heart: false })), duration);
        return () => clearTimeout(timeout);
    }, [activity.heart, activity.tension]);

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
            <div className="flex flex-col items-center gap-1">
                <div className={`w-4 h-2 border border-black transition-colors ${ledStatus.disk ? 'bg-red-500 shadow-[0_0_5px_rgba(239,68,68,0.8)]' : 'bg-red-950'}`}></div>
                <span className="text-gray-600">DISK</span>
            </div>
            <div className="flex flex-col items-center gap-1">
                <div className={`w-4 h-2 border border-black ${ledStatus.llm || activity.llm_busy ? 'bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.8)]' : 'bg-red-950'} ${activity.llm_busy ? 'animate-pulse' : ''}`}></div>
                <span className="text-red-900">NEURAL</span>
            </div>
            <div className="flex flex-col items-center gap-1">
                <div className={`w-4 h-2 border border-black ${ledStatus.ego || activity.ego_busy ? 'bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.8)]' : 'bg-red-950'} ${activity.ego_busy ? 'animate-pulse' : ''}`}></div>
                <span className="text-red-900">EGO</span>
            </div>
            <div className="flex flex-col items-center gap-1">
                <div className={`w-4 h-2 border border-black ${ledStatus.phys || activity.phys_busy ? 'bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.8)]' : 'bg-red-950'} ${activity.phys_busy ? 'animate-pulse' : ''}`}></div>
                <span className="text-red-900">PHYS</span>
            </div>
            <div className="flex flex-col items-center gap-1">
                <div className={`w-4 h-2 border border-black transition-colors ${ledStatus.net ? 'bg-red-500 shadow-[0_0_5px_rgba(239,68,68,0.8)]' : 'bg-red-950'}`}></div>
                <span className="text-gray-600">NET</span>
            </div>
            <div className="flex flex-col items-center gap-1">
                <div className={`w-4 h-2 border border-black transition-colors ${ledStatus.heart ? 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.9)]' : 'bg-red-950'}`}></div>
                <span className="text-gray-600">HEART</span>
            </div>
        </div>
    );
};

const WatchdogTerminal = ({ logs = [], activeAgents = {}, heartbeatStats }) => {
    const containerRef = useRef(null);
    const isAtBottomRef = useRef(true);

    const handleScroll = () => {
        if (containerRef.current) {
            const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
            isAtBottomRef.current = scrollHeight - (scrollTop + clientHeight) < 50;
        }
    };

    const [spinner, setSpinner] = useState(0);
    const frames = ['|', '/', '-', '\\'];

    useEffect(() => {
        const interval = setInterval(() => setSpinner(s => (s + 1) % 4), 100);
        return () => clearInterval(interval);
    }, []);

    useEffect(() => {
        if (isAtBottomRef.current && containerRef.current) {
            containerRef.current.scrollTop = containerRef.current.scrollHeight;
        }
    }, [logs]);

    const formatLog = (log, idx) => {
        if (!log || typeof log !== 'string') return null;
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
            <div className="bg-gray-200 border-b-2 border-claw-border p-1 flex justify-between items-center text-[10px] font-bold text-gray-700 uppercase tracking-wider">
                <span>[ TERMINAL_WATCHDOG ]</span>
                <span>{frames[spinner]} {Object.keys(activeAgents || {}).length > 0 ? "BUSY" : "IDLE"}</span>
            </div>
            <div ref={containerRef} onScroll={handleScroll} className="flex-1 overflow-y-auto p-1 scrollbar-hide flex flex-col gap-0.5">
                {(logs || []).slice(-50).map((log, i) => formatLog(log, i))}
            </div>
            <div className="bg-white border-t border-gray-300 p-1 text-[8px] text-gray-500 flex justify-between uppercase">
                <span>MEM: {heartbeatStats?.mem || "64MB"} OK</span>
                <span>UPTIME: {heartbeatStats?.uptime || 0}S</span>
            </div>
        </div>
    );
};

const SidebarLeft = ({ agents, posts, statusText, activeAgents, systemLogs, heartbeatStats, agentStatuses, systemState, activity, onOpenGraph }) => {
    const [isPulsing, setIsPulsing] = useState(false);
    useEffect(() => {
        setIsPulsing(true);
        const timer = setTimeout(() => setIsPulsing(false), 800);
        return () => clearTimeout(timer);
    }, [heartbeatStats?.uptime]);

    const [logSize, setLogSize] = useState("0 B");
    useEffect(() => {
        const fetchSize = async () => {
            try {
                const res = await fetch("http://localhost:8000/logs/size");
                if (res.ok) {
                    const data = await res.json();
                    setLogSize(data.size_formatted);
                }
            } catch (e) { }
        };
        fetchSize();
        const interval = setInterval(fetchSize, 5000);
        return () => clearInterval(interval);
    }, []);

    const handleDownload = () => {
        window.location.href = "http://localhost:8000/logs/download";
    };

    const handleExportChat = () => {
        const content = formatChatHistory(posts);
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        downloadTxtFile(content, `iron_council_chat_${timestamp}.txt`);
    };

    return (
        <div className="w-80 h-screen flex flex-col bg-[#d1d5db] border-r-2 border-claw-border shadow-2xl z-50 overflow-hidden relative">
            <div className="bg-[#1e293b] text-white p-2 flex justify-between items-center border-b-2 border-black flex-none">
                <span className="text-[10px] font-bold tracking-tighter">OPERATIONAL_MONITOR_v2.0</span>
                <div className="flex items-center gap-1.5">
                    <div className={`w-1.5 h-1.5 rounded-full ${isPulsing ? 'bg-cyan-400 shadow-[0_0_5px_rgba(34,211,238,0.8)]' : 'bg-cyan-900'} transition-all duration-300`}></div>
                    <span className="text-[9px] font-mono text-cyan-400">{statusText.includes("READY") ? "CONNECTED" : "ACTIVE"}</span>
                </div>
            </div>

            <div className="flex-1 overflow-y-auto scrollbar-hide flex flex-col">
                <HardwareMonitor activity={activity} />
                <MissionStatus heartbeatStats={heartbeatStats} systemState={systemState} />

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
                                activity={activity}
                            />
                        ))}
                    </div>
                </div>

                <div className="p-2 border-t border-claw-border bg-gray-100 mt-auto flex flex-col gap-2 flex-none">
                    <WatchdogTerminal
                        logs={systemLogs.filter(log => {
                            const blacklist = ["System nominal.", "Integrity check passed.", "Watching...", "Ping.", "Cycle complete."];
                            return !blacklist.some(b => log.includes(b));
                        })}
                        activeAgents={activeAgents}
                        heartbeatStats={heartbeatStats}
                    />
                    <div className="flex justify-between items-end mb-1 px-1 font-mono">
                        <span className="text-[7px] text-gray-500">BUFFER_SIZE:</span>
                        <span className="text-[9px] font-bold text-gray-700">{logSize}</span>
                    </div>
                    <div className="flex gap-2">
                        <button
                            onClick={handleDownload}
                            className="flex-1 bg-[#af0a0f] text-white font-bold py-1 px-2 text-[10px] uppercase tracking-widest shadow-sharp hover:bg-red-800 transition-colors border border-black active:shadow-none translate-x-[1px] translate-y-[1px]"
                        >
                            DOWNLOAD_LOG.EXE
                        </button>
                        <button
                            onClick={handleExportChat}
                            title="EXPORT CHAT TO .TXT"
                            className="bg-gray-300 text-black font-bold py-1 px-2 text-[10px] uppercase tracking-widest shadow-sharp hover:bg-white transition-colors border border-black active:shadow-none translate-x-[1px] translate-y-[1px]"
                        >
                            EXPORT CHAT TO .TXT
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default SidebarLeft;
