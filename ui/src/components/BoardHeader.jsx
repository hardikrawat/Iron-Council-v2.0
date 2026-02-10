import React, { useState } from 'react';

const AgentCard = ({ agent, isFlipped, onFlip, onOpenNetwork }) => {
    const { id, name, stats, relationships } = agent;
    const isParanoid = stats.paranoia > 70;

    // Get top positive and negative relationships
    const rels = Object.entries(relationships || {})
        .sort(([, a], [, b]) => Math.abs(b) - Math.abs(a)) // Sort by magnitude
        .slice(0, 3); // Top 3

    return (
        <div
            className={`flip-card w-full min-w-[140px] h-[72px] cursor-pointer perspective-1000 ${isParanoid ? "shake-hard" : ""}`}
            onClick={() => onFlip(id)}
        >
            <div className={`flip-card-inner relative w-full h-full transition-transform duration-500 transform-style-3d ${isFlipped ? "rotate-y-180" : ""}`}>

                {/* FRONT FACE */}
                <div className={`flip-card-front absolute w-full h-full backface-hidden flex flex-col justify-between bg-white border ${isParanoid ? "border-red-600" : "border-claw-border"} p-1 shadow-sharp`}>
                    <div className="font-bold text-[11px] mb-0.5 uppercase flex justify-between items-center bg-gray-100 px-1 select-none">
                        <span>/{id}/</span>
                        {isParanoid && (
                            <span className="text-red-600 font-mono animate-pulse">!CRITICAL!</span>
                        )}
                    </div>
                    <div className="text-[10px] grid grid-cols-3 gap-1 px-1 font-mono leading-tight">
                        <div className="flex flex-col">
                            <span className="text-gray-500">LOY</span>
                            <span className={stats.loyalty_to_chairman < 30 ? "text-red-600 font-bold" : ""}>
                                {stats.loyalty_to_chairman}%
                            </span>
                        </div>
                        <div className="flex flex-col">
                            <span className="text-gray-500">CNF</span>
                            <span>{stats.confidence}%</span>
                        </div>
                        <div className="flex flex-col">
                            <span className="text-gray-500">PAR</span>
                            <span className={stats.paranoia > 50 ? "text-red-600 font-bold" : ""}>
                                {stats.paranoia}%
                            </span>
                        </div>
                    </div>
                </div>

                {/* BACK FACE - CLEAN STYLE */}
                <div className={`flip-card-back absolute w-full h-full backface-hidden rotate-y-180 bg-gray-50 border border-claw-border p-1 flex flex-col justify-between shadow-sharp text-left`}>
                    <div className="text-[8px] font-bold text-gray-500 uppercase tracking-widest border-b border-gray-200 pb-0.5 mb-0.5 select-none text-center">
                        RELATIONSHIPS
                    </div>
                    <div className="flex-1 flex flex-col justify-center space-y-0.5">
                        {rels.length > 0 ? rels.map(([target, score]) => (
                            <div key={target} className="flex justify-between text-[9px] font-mono leading-none select-none px-1">
                                <span className="text-gray-600 truncate max-w-[80px]">{target.split(' ')[1] || target}</span>
                                <span className={`${score > 0 ? "text-green-600" : "text-red-600"} font-bold`}>{score > 0 ? '+' : ''}{score}</span>
                            </div>
                        )) : <div className="text-[8px] text-gray-400 italic text-center">No Data</div>}
                    </div>

                    <button
                        onClick={(e) => {
                            e.stopPropagation(); // Prevent flip back
                            onOpenNetwork();
                        }}
                        className="w-full text-[9px] bg-white hover:bg-gray-100 text-blue-900 border border-gray-300 uppercase font-bold py-0.5 mt-0.5 transition-colors shadow-sm"
                    >
                        View Graph
                    </button>
                </div>

            </div>
        </div>
    );
};

const BoardHeader = ({ agents, onOpenGraph }) => {
    const [flippedId, setFlippedId] = useState(null);

    return (
        <div className="sticky top-0 z-40 flex flex-wrap gap-2 p-2 bg-claw-bg border-b border-claw-border shadow-md">
            {agents.map((agent) => (
                <div key={agent.id} className="flex-1 min-w-[140px]">
                    <AgentCard
                        agent={agent}
                        isFlipped={flippedId === agent.id}
                        onFlip={(id) => setFlippedId(flippedId === id ? null : id)}
                        onOpenNetwork={() => onOpenGraph(agent.id)}
                    />
                </div>
            ))}
        </div>
    );
};

export default BoardHeader;
