import React from 'react';

const NeuralTachometer = ({ value = 0 }) => {
    // Scale 0-100 Synaptic Flux (mF)
    const clampedValue = Math.min(100, Math.max(0, value));
    const rotation = (clampedValue / 100) * 180 - 90; // -90 to 90 degrees
    const isRedZone = clampedValue >= 75;

    return (
        <div className="relative w-full h-24 flex flex-col items-center justify-end mb-1">
            <div className="relative pt-2">
                {/* SVG Gauge */}
                <svg viewBox="0 0 100 55" className="w-28 h-14">
                    {/* Background Track */}
                    <path
                        d="M 10 50 A 40 40 0 0 1 90 50"
                        fill="none"
                        stroke="#d1d5db"
                        strokeWidth="10"
                        strokeLinecap="round"
                    />
                    {/* Red Zone Marker */}
                    <path
                        d="M 70 20 A 40 40 0 0 1 90 50"
                        fill="none"
                        stroke="#ef4444"
                        strokeWidth="10"
                        strokeLinecap="round"
                        className="opacity-30"
                    />
                    {/* Active Progress */}
                    <path
                        d="M 10 50 A 40 40 0 0 1 90 50"
                        fill="none"
                        stroke={isRedZone ? '#ef4444' : '#2563eb'}
                        strokeWidth="10"
                        strokeLinecap="round"
                        strokeDasharray="125.6"
                        strokeDashoffset={125.6 - (clampedValue / 100) * 125.6}
                        className="transition-all duration-500 ease-out"
                        style={{ filter: isRedZone ? 'drop-shadow(0 0 3px rgba(239, 68, 68, 0.5))' : 'none' }}
                    />

                    {/* Tick Marks (0, 25, 50, 75, 100) */}
                    {[0, 25, 50, 75, 100].map((tick) => {
                        const angle = (tick / 100) * 180 - 180;
                        const rad = (angle * Math.PI) / 180;
                        const x1 = 50 + 32 * Math.cos(rad);
                        const y1 = 50 + 32 * Math.sin(rad);
                        const x2 = 50 + 38 * Math.cos(rad);
                        const y2 = 50 + 38 * Math.sin(rad);
                        return (
                            <line
                                key={tick}
                                x1={x1} y1={y1} x2={x2} y2={y2}
                                stroke="white"
                                strokeWidth="1"
                                className="opacity-50"
                            />
                        );
                    })}
                </svg>

                {/* Needle */}
                <div
                    className="absolute bottom-0 left-1/2 -ml-[1px] w-[2px] h-12 bg-black origin-bottom transition-transform duration-500 ease-out"
                    style={{
                        transform: `rotate(${rotation}deg)`,
                        boxShadow: '0 0 2px rgba(0,0,0,0.5)',
                        filter: isRedZone ? 'drop-shadow(0 0 1px red)' : 'none'
                    }}
                >
                    <div className="absolute -top-1 -left-1 w-2.5 h-2.5 bg-red-600 rounded-full border border-black shadow-sharp"></div>
                </div>
            </div>
        </div>
    );
};

const LLMUsagePanel = ({ activity = {} }) => {
    // Neural metrics from activity
    const activityMetric = activity.llm_activity || 0;
    const signal = activity.llm_signal || "HIGH";
    const load = activity.llm_load || 0;
    const model = activity.llm_model || "UNKNOWN";
    const requests = activity.llm_requests || 0;
    const activeRequests = activity.llm_active_requests || 0;
    const inTokens = activity.llm_input_tokens || 0;
    const outTokens = activity.llm_output_tokens || 0;
    const isBusy = activity.llm_busy;
    const activeAgent = activity.llm_agent;
    const currentStep = activity.llm_step;

    // Helper to format values with placeholders when busy
    const formatMetric = (val, formatFn, placeholder = "CALCULATING...") => {
        if (isBusy && (val === 0 || val === "0.0")) return <span className="text-[6px] animate-pulse italic">{placeholder}</span>;
        return formatFn(val);
    };

    return (
        <div className="p-3 border-b border-gray-400 bg-gray-200">
            <div className="text-[10px] font-bold text-gray-700 uppercase tracking-widest mb-2 flex justify-between items-center">
                <span>// NEURAL_LINK_MONITOR</span>
                <span className={`text-[8px] ${isBusy ? 'text-red-600 animate-pulse' : 'text-gray-400'}`}>
                    {isBusy ? '● PROCESSING' : '○ STANDBY'}
                </span>
            </div>

            <div className="bg-white border-2 border-claw-border shadow-sharp p-1 space-y-2">
                {/* Link Status & Agent */}
                <div className="flex flex-col gap-1">
                    <div className="flex items-center gap-2">
                        <div className="flex-1 bg-gray-50 border border-gray-200 p-1 h-6 flex items-center overflow-hidden">
                            <span className="text-[8px] text-blue-900 font-bold mr-1 shrink-0">LINK:</span>
                            <div className="whitespace-nowrap truncate text-black font-mono text-[9px]">
                                {isBusy ? (
                                    <span className="animate-pulse">[{activeAgent}] ACCESSING {currentStep}...</span>
                                ) : (
                                    <span className="text-gray-400 italic">STANDBY - NEURAL_LINK_OPEN</span>
                                )}
                            </div>
                        </div>
                        <div className="w-10 flex flex-col items-center gap-0.5 shrink-0">
                            <div className={`w-4 h-2 border border-black transition-colors ${isBusy ? 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.8)]' : 'bg-red-950'}`}></div>
                            <span className="text-[7px] text-gray-600 font-mono">PROC</span>
                        </div>
                    </div>
                </div>

                {/* Centerpiece: Neural Tachometer */}
                <div className="bg-gray-50 border border-gray-200 py-2">
                    <NeuralTachometer value={activityMetric} />
                    {/* Readout with placeholder */}
                    <div className="text-center">
                        <div className={`text-[11px] font-black font-mono leading-none ${activityMetric >= 75 ? 'text-red-600 animate-pulse' : 'text-blue-900'}`}>
                            {isBusy && activityMetric <= 15 ? (
                                <span className="text-[8px] animate-pulse">IGNITING_FLUX...</span>
                            ) : (
                                <>{activityMetric.toFixed(1)} <span className="text-[7px]">mF</span></>
                            )}
                        </div>
                        <div className="text-[6px] font-bold text-gray-400 uppercase tracking-tighter">SYNAPTIC_FLUX // INTENSITY</div>
                    </div>
                </div>

                {/* Grid for other metrics */}
                <div className="grid grid-cols-2 gap-2">
                    {/* Left: Synaptic Load */}
                    <div className="space-y-1.5 px-0.5 pt-1">
                        <div className="flex flex-col">
                            <div className="flex justify-between items-center text-[7px] font-bold text-gray-400 mb-0.5 uppercase tracking-tighter">
                                <span>Synaptic_Load</span>
                                <span className="text-red-700 font-black">
                                    {isBusy && load === 0 ? "ESTIMATING..." : `${load}%`}
                                </span>
                            </div>
                            <div className="w-full bg-gray-100 h-3 border border-black relative overflow-hidden">
                                <div
                                    className="h-full bg-red-600 transition-all duration-300 shadow-[0_0_5px_rgba(220,38,38,0.3)]"
                                    style={{ width: `${load}%` }}
                                />
                                <div className="absolute inset-0 flex">
                                    {[...Array(10)].map((_, i) => (
                                        <div key={i} className="flex-1 border-r border-black/10"></div>
                                    ))}
                                </div>
                            </div>
                        </div>
                        {/* Model indicator moved here */}
                        <div className="bg-gray-100 text-[#af0a0f] px-1 py-0.5 border border-gray-200 flex flex-col text-[7px] font-mono overflow-hidden uppercase">
                            <span className="text-gray-500 font-bold">MODEL_ID:</span>
                            <span className="truncate font-black">{model}</span>
                        </div>
                    </div>

                    {/* Right: Static Counters */}
                    <div className="bg-white border border-gray-200 p-1 flex flex-col justify-between font-mono text-[7px] leading-tight">
                        <div className="flex justify-between border-b border-gray-100 pb-0.5">
                            <span className="text-gray-400">SYNAPSES</span>
                            <span className="text-black font-bold">{requests}</span>
                        </div>
                        <div className="flex justify-between border-b border-gray-100 pb-0.5 pt-0.5">
                            <span className="text-gray-400">ACTIVE_LINKS</span>
                            <span className={`${activeRequests > 0 ? 'text-red-600 animate-pulse' : 'text-gray-500'} font-bold`}>{activeRequests}</span>
                        </div>
                        <div className="flex justify-between border-b border-gray-100 pb-0.5 pt-0.5">
                            <span className="text-gray-400">PENDING_LINKS</span>
                            <span className={`${activity.llm_pending_requests > 0 ? 'text-amber-600 animate-pulse' : 'text-gray-500'} font-bold`}>{activity.llm_pending_requests || 0}</span>
                        </div>
                        <div className="flex justify-between border-b border-gray-100 pb-0.5 pt-0.5">
                            <span className="text-gray-400">QUEUE_LAG</span>
                            <span className={`${activity.llm_queue_latency > 1000 ? 'text-red-600 font-black' : 'text-gray-500'} font-bold`}>
                                {isBusy && !activity.llm_queue_latency ?
                                    <span className="text-[6px] animate-pulse">CALCULATING...</span> :
                                    `${((activity.llm_queue_latency || 0) / 1000).toFixed(1)}s`
                                }
                            </span>
                        </div>
                        <div className="flex flex-col gap-0.5 pt-0.5">
                            <div className="flex justify-between">
                                <span className="text-gray-400">IN_TOK</span>
                                <span className="text-blue-900">{formatMetric(inTokens, (v) => `${(v / 1000).toFixed(1)}k`)}</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-gray-400">OUT_TOK</span>
                                <span className="text-green-700">{formatMetric(outTokens, (v) => `${(v / 1000).toFixed(1)}k`)}</span>
                            </div>
                            <div className="flex justify-between mt-0.5 border-t border-gray-100 pt-0.5">
                                <span className="text-black font-bold">TOTAL</span>
                                <span className="text-black font-bold">{formatMetric(inTokens + outTokens, (v) => `${(v / 1000).toFixed(1)}k`)}</span>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Footer Info */}
                <div className="flex justify-between items-center text-[7px] bg-gray-50 py-0.5 px-1 border border-gray-100 font-mono">
                    <div className="flex items-center gap-1">
                        <span className="text-gray-400">SIGNAL:</span>
                        <span className={`font-bold ${signal === 'HIGH' ? 'text-green-600' :
                            signal === 'MED' ? 'text-amber-600' : 'text-red-600'
                            }`}>
                            {signal}
                        </span>
                    </div>
                    <div className="text-gray-400">NEURAL_PROTO_LNK v2.1</div>
                </div>
            </div>
        </div>
    );
};

export default LLMUsagePanel;
