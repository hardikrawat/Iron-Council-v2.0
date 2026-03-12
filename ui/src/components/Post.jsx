
import React, { useState } from 'react';
import Typewriter from './Typewriter';

const TRIPCODES = {
    "General Ares": "!WARGOD",
    "Diplomat Dove": "!PEACEMKR",
    "Banker Midas": "!GOLDSTD",
    "Analyst Logic": "!LOGICGATE",
    "Chairman": "!OMNIADMIN"
};

const IDENTICONS = {
    "General Ares": "⚔️",
    "Diplomat Dove": "🕊️",
    "Banker Midas": "💰",
    "Analyst Logic": "📐",
    "Chairman": "👁️"
};

// Fallback for visual assets if pure text
const AGENT_COLORS = {
    "General Ares": "bg-red-100",
    "Diplomat Dove": "bg-blue-100",
    "Banker Midas": "bg-yellow-100",
    "Analyst Logic": "bg-gray-100",
    "Chairman": "bg-purple-100"
};

const Post = ({ post }) => {
    // post: { type, content, data: { name, public_text, hidden_text, id } }

    const isAgent = post.type === 'agent_post';
    const name = isAgent ? post.data.name : "Chairman";
    const tripcode = TRIPCODES[name] || "!!ANON";
    const publicText = isAgent ? post.data.public_text : post.content;
    const hiddenText = isAgent ? post.data.hidden_text : null;

    // Integrity mechanic: Visual diff
    // Fix: Show hidden text if it exists, regardless of similarity, to ensure visibility
    const hasHiddenLayer = isAgent && hiddenText && hiddenText.trim().length > 0;

    // Visual Assets: Simple Color Block Identicon
    const identiconChar = name[0];
    const colorClass = AGENT_COLORS[name] || "bg-white";

    const timestamp = post.timestamp ? new Date(post.timestamp).toLocaleTimeString() : new Date().toLocaleTimeString();

    return (
        <div className="flex gap-2 mb-3 group">
            {/* Side Arrows / Container */}
            <div className="w-6 shrink-0 flex flex-col items-center pt-1">
                <div className={`w-6 h-6 ${colorClass} border border-black flex items-center justify-center font-bold text-xs shadow-[1px_1px_0px_#000]`}>
                    {IDENTICONS[name] || identiconChar}
                </div>
            </div>

            <div className="flex-1 bg-[#EEF2FF] border border-black p-2 shadow-[2px_2px_0px_#000] relative">
                {/* Header */}
                <div className="text-[11px] border-b border-gray-400 pb-1 mb-1 font-bold text-[#117743] leading-none">
                    <span className="text-[#0f0c5d]">{name}</span>
                    <span className="text-[#117743] font-normal ml-2">{tripcode}</span>
                    <span className="text-gray-500 font-normal ml-2 text-[10px]">{timestamp}</span>
                </div>

                {/* Content */}
                <div className="font-sans text-[13px] leading-snug whitespace-pre-wrap text-black">
                    <div className="mb-1">
                        <Typewriter text={publicText} isStreaming={post.isStreaming} />
                    </div>

                    {hasHiddenLayer && (
                        <div className="mt-2 border-t border-gray-300 pt-1">
                            <div className="group/spoiler relative cursor-help select-none">
                                {/* The Thought Stream: Indigo theme for 'Neural' activity */}
                                <div className="bg-[#1e1b4b] text-[#a5b4fc] group-hover/spoiler:text-white transition-colors duration-300 ease-in p-2 font-mono text-xs border-l-2 border-indigo-500">
                                    <span className="opacity-50 select-none mr-2">{'>'}</span>
                                    <Typewriter text={hiddenText} isStreaming={post.isStreaming} speed={20} />
                                </div>
                                <div className="absolute top-0 right-0 text-[9px] text-indigo-400 opacity-70 pointer-events-none group-hover/spoiler:opacity-0 pr-1 pt-1">
                                    [THOUGHT STREAM]
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default Post;
