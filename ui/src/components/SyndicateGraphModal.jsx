import React, { useMemo } from 'react';

const SyndicateGraphModal = ({ isOpen, onClose, agents, focusedAgentId }) => {
    if (!isOpen) return null;

    // Use useMemo to avoid recalculating on every render
    const positions = useMemo(() => {
        const count = agents.length;
        const centerX = 200;
        const centerY = 200;
        const radius = 120; // SVG coordinate system

        return agents.map((agent, i) => {
            const angle = (i / count) * 2 * Math.PI - Math.PI / 2; // Start at top
            return {
                id: agent.id, // e.g. general_ares
                name: agent.name, // e.g. General Ares
                x: centerX + radius * Math.cos(angle),
                y: centerY + radius * Math.sin(angle),
            };
        });
    }, [agents]);

    // Create lines for ALL relationships
    const lines = useMemo(() => {
        const resultLines = [];

        agents.forEach((sourceAgent) => {
            const sourcePos = positions.find(p => p.id === sourceAgent.id);
            if (!sourcePos || !sourceAgent.relationships) return;

            Object.entries(sourceAgent.relationships).forEach(([targetName, rel]) => {
                // Support both RelationshipModel objects and raw int scores
                const score = typeof rel === 'object' ? (rel.trust_score ?? 0) : rel;
                const targetPos = positions.find(p => p.name === targetName);

                if (targetPos && Math.abs(score) > 5) {
                    const isNeutral = Math.abs(score) <= 5;
                    resultLines.push({
                        x1: sourcePos.x,
                        y1: sourcePos.y,
                        x2: targetPos.x,
                        y2: targetPos.y,
                        score: score,
                        isNeutral: isNeutral,
                        sourceId: sourceAgent.id,
                        targetName: targetName,
                        key: `${sourceAgent.id}-${targetName}`
                    });
                }
            });
        });
        return resultLines;
    }, [agents, positions]);

    // Helper to determine if a line or node should be dimmed
    const isDimmed = (type, item) => {
        if (!focusedAgentId) return false; // Show all if no focus
        if (type === 'node') return item.id !== focusedAgentId;
        if (type === 'line') {
            // Check if line connects to focused agent
            // We need to match name too since target is a name string
            const focusedName = agents.find(a => a.id === focusedAgentId)?.name;
            return item.sourceId !== focusedAgentId && item.targetName !== focusedName;
        }
        return false;
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-[2px] animate-fade-in">
            <div className="relative w-full max-w-lg bg-[#f0f0f0] border border-gray-400 p-4 rounded-none shadow-xl">

                {/* Close Button */}
                <button
                    onClick={onClose}
                    className="absolute top-2 right-2 text-red-800 hover:text-red-600 font-bold font-sans text-sm border border-red-300 bg-red-50 px-2"
                >
                    [X]
                </button>

                {/* Header */}
                <div className="text-center mb-4">
                    <h2 className="text-lg font-bold text-[#af0a0f] tracking-tight uppercase font-sans">
                        Syndicate Graph
                    </h2>
                    <div className="text-[10px] text-gray-600 font-sans mt-0.5">
                        {focusedAgentId ? `Network Focus: ${focusedAgentId.toUpperCase()}` : "Trust Network Visualization"}
                    </div>
                    <div className="h-px bg-gray-300 w-full mt-2"></div>
                </div>

                {/* Graph Visualization */}
                <div className="relative aspect-square w-full max-w-[400px] mx-auto bg-white border border-gray-300 shadow-inner">
                    <svg viewBox="0 0 400 400" className="w-full h-full">
                        {/* Background Grid */}
                        <defs>
                            <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
                                <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#e5e7eb" strokeWidth="1" />
                            </pattern>
                        </defs>
                        <rect width="400" height="400" fill="url(#grid)" />

                        {/* Connection Lines */}
                        {lines.map((line) => {
                            const isPositive = line.score > 0;
                            const color = line.isNeutral ? "#9ca3af" : (isPositive ? "#16a34a" : "#dc2626");
                            const dimmed = isDimmed('line', line);
                            const midX = (line.x1 + line.x2) / 2;
                            const midY = (line.y1 + line.y2) / 2;

                            return (
                                <g key={line.key}>
                                    <line
                                        x1={line.x1}
                                        y1={line.y1}
                                        x2={line.x2}
                                        y2={line.y2}
                                        stroke={color}
                                        strokeWidth={Math.max(1, Math.abs(line.score) / 25)}
                                        strokeOpacity={dimmed ? "0.1" : "0.8"}
                                        strokeLinecap="square"
                                        strokeDasharray={line.isNeutral ? "4 3" : "none"}
                                    />
                                    {!dimmed && (
                                        <text
                                            x={midX}
                                            y={midY - 5}
                                            textAnchor="middle"
                                            fill={color}
                                            fontSize="8"
                                            fontFamily="Arial, sans-serif"
                                            opacity="0.7"
                                        >
                                            {line.score > 0 ? `+${line.score}` : line.score}
                                        </text>
                                    )}
                                </g>
                            );
                        })}

                        {/* Nodes (Agents) */}
                        {positions.map((pos) => {
                            const isFocused = focusedAgentId === pos.id;
                            const dimmed = isDimmed('node', pos);

                            return (
                                <g key={pos.id} className={`cursor-pointer transition-opacity ${dimmed ? "opacity-40" : "opacity-100"}`}>

                                    {/* Highlight Ring for Focused Agent */}
                                    {isFocused && (
                                        <circle
                                            cx={pos.x}
                                            cy={pos.y}
                                            r="26"
                                            fill="none"
                                            stroke="#af0a0f"
                                            strokeWidth="2"
                                            strokeDasharray="4 2"
                                            className="animate-spin-slow"
                                        />
                                    )}

                                    {/* Background Circle */}
                                    <circle
                                        cx={pos.x}
                                        cy={pos.y}
                                        r="20"
                                        fill={isFocused ? "#fff1f2" : "#ffffff"}
                                        stroke={isFocused ? "#be123c" : "#374151"}
                                        strokeWidth={isFocused ? "2" : "1.5"}
                                    />

                                    {/* Agent Initials */}
                                    <text
                                        x={pos.x}
                                        y={pos.y}
                                        dy="5"
                                        textAnchor="middle"
                                        fill="#1f2937"
                                        fontSize="12"
                                        fontWeight="bold"
                                        fontFamily="Arial, sans-serif"
                                    >
                                        {pos.name.split(' ').map(n => n[0]).join('')}
                                    </text>

                                    {/* Full Name Label */}
                                    <text
                                        x={pos.x}
                                        y={pos.y + 32}
                                        textAnchor="middle"
                                        fill="#4b5563"
                                        fontSize="10"
                                        fontFamily="Arial, sans-serif"
                                        fontWeight={isFocused ? "bold" : "normal"}
                                    >
                                        {pos.name.split(' ')[1] || pos.name}
                                    </text>
                                </g>
                            );
                        })}
                    </svg>
                </div>

                {/* Legend */}
                <div className="flex justify-center gap-6 mt-4 text-[11px] font-sans text-gray-700">
                    <div className="flex items-center gap-1.5 opacity-80">
                        <div className="w-3 h-3 bg-green-600 border border-green-800"></div>
                        <span>Trust</span>
                    </div>
                    <div className="flex items-center gap-1.5 opacity-80">
                        <div className="w-3 h-3 bg-gray-400 border border-gray-500"></div>
                        <span>Neutral</span>
                    </div>
                    <div className="flex items-center gap-1.5 opacity-80">
                        <div className="w-3 h-3 bg-red-600 border border-red-800"></div>
                        <span>Distrust</span>
                    </div>
                </div>

            </div>
        </div>
    );
};

export default SyndicateGraphModal;
