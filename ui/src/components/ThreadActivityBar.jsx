import React, { useState, useEffect, useRef } from 'react';

const ThreadActivityBar = ({ statusText, activeAgents }) => {
    const [spinnerIndex, setSpinnerIndex] = useState(0);

    // ASCII Spinner
    const spinnerFrames = ['|', '/', '-', '\\'];

    useEffect(() => {
        const spinnerInterval = setInterval(() => {
            setSpinnerIndex(prev => (prev + 1) % 4);
        }, 100);
        return () => clearInterval(spinnerInterval);
    }, []);

    // Render logic
    const hasActivity = Object.keys(activeAgents || {}).length > 0;
    const isIdle = !hasActivity && (statusText && statusText.includes("READY"));

    return (
        <div className="w-full bg-[#F3F4F6] border-t border-[#ccc] text-[#666] font-mono text-[11px] px-2 py-1 flex items-center h-[24px] overflow-hidden whitespace-nowrap select-none">
            {isIdle ? (
                <span>{statusText}</span>
            ) : (
                <div className="flex gap-4">
                    {/* Show System/Physics first if active */}
                    {activeAgents['PHYSICS_ENGINE'] && (
                        <span className="text-blue-600">
                            {spinnerFrames[spinnerIndex]} [PHYSICS]: {activeAgents['PHYSICS_ENGINE']}
                        </span>
                    )}

                    {/* Show Agents */}
                    {Object.entries(activeAgents || {}).map(([agent, action]) => {
                        if (agent === 'PHYSICS_ENGINE') return null;
                        // Truncate action text if too long
                        const displayAction = action.length > 30 ? action.substring(0, 30) + "..." : action;
                        return (
                            <span key={agent} className="flex gap-1 items-center">
                                <span className="font-bold">{spinnerFrames[spinnerIndex]} [{agent}]:</span>
                                <span>{displayAction}</span>
                            </span>
                        );
                    })}

                    {!hasActivity && statusText && <span>{statusText}</span>}
                </div>
            )}
        </div>
    );
};


export default ThreadActivityBar;
