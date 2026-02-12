
import React, { useState, useEffect, useRef } from 'react';
import Sidebar from './components/Sidebar';
import Post from './components/Post';
import SyndicateGraphModal from './components/SyndicateGraphModal';

function App() {
    const [agents, setAgents] = useState([]);
    const [posts, setPosts] = useState([]);
    const [connected, setConnected] = useState(false);
    const [input, setInput] = useState("");
    const wsRef = useRef(null);
    const bottomRef = useRef(null);
    // FIX AUDIT-4.2: Counter-based unique post IDs for stable React keys
    const postIdCounter = useRef(0);
    const nextPostId = () => `post-${++postIdCounter.current}`;
    const [statusText, setStatusText] = useState("System: READY // Waiting for command...");
    const [activeAgents, setActiveAgents] = useState({});
    const [showGraphModal, setShowGraphModal] = useState(false);
    const [selectedAgentId, setSelectedAgentId] = useState(null);
    const [systemLogs, setSystemLogs] = useState([]);
    const [heartbeatStats, setHeartbeatStats] = useState({ uptime: 0, mem: "64.0MB", status: "READY" });
    const [agentStatuses, setAgentStatuses] = useState({});
    const [systemState, setSystemState] = useState({ tension: 0, conch: null });
    const [activity, setActivity] = useState({ disk: 0, llm: 0, net: 0, ego: 0, phys: 0 });
    const [isDreaming, setIsDreaming] = useState(false);

    useEffect(() => {
        // FIX CRIT-04: WebSocket with automatic reconnection + exponential backoff
        let ws;
        let retryDelay = 1000;
        let isMounted = true;

        const connect = () => {
            if (!isMounted) return;
            ws = new WebSocket("ws://localhost:8000/ws/council");
            wsRef.current = ws;

            ws.onopen = () => {
                console.log("Connected to Council");
                setConnected(true);
                retryDelay = 1000; // Reset backoff on successful connection
            };

            ws.onmessage = (event) => {
                const msg = JSON.parse(event.data);

                // Pulse NET activity on every message
                setActivity(prev => ({ ...prev, net: Date.now() }));

                if (msg.type === 'init') {
                    setAgents(msg.data);
                } else if (msg.type === 'heartbeat_pulse') {
                    setHeartbeatStats(msg.stats);
                    // Sync CORE LED with actual backend pulse
                    setActivity(prev => ({ ...prev, heart: Date.now() }));
                } else if (msg.type === 'relationship_update') {
                    // Update relationships specifically 
                    setAgents(prev => prev.map(a => a.id === msg.agent_id ? { ...a, relationships: msg.relationships } : a));
                } else if (msg.type === 'agent_status_update') {
                    setAgentStatuses(prev => ({
                        ...prev,
                        [msg.data.agent]: {
                            status: msg.data.status,
                            details: msg.data.details,
                            phase: msg.data.phase,  // FIX 6.1: Preserve phase for OODA indicators
                            updatedAt: Date.now()
                        }
                    }));
                } else if (msg.type === 'system_state_update') {
                    // { time, tension, conch: { owner, expires_in } }
                    setSystemState(prev => ({
                        ...prev,
                        tension: msg.data.tension,
                        conch: msg.data.conch
                    }));
                } else if (msg.type === 'stat_update') {
                    setAgents(prev => prev.map(a => a.id === msg.agent_id ? {
                        ...a,
                        stats: msg.stats,
                        goals: msg.goals // Update goals as well
                    } : a));
                } else if (msg.type === 'activity_event') {
                    const { event, data } = msg;
                    // FIX AUDIT-4.3: Unique time for singleton blinks
                    const uniqueTime = Date.now() + (Math.random() * 0.1);
                    const status = data?.status; // START or END

                    setActivity(prev => {
                        const next = { ...prev };

                        // Mapping helper for busy states
                        const updateBusy = (key) => {
                            const countKey = `${key}_count`;
                            const currentCount = next[countKey] || 0;
                            if (status === 'START') {
                                next[countKey] = currentCount + 1;
                                next[`${key}_busy`] = true;
                                next[key] = uniqueTime; // Also trigger a blink
                            } else if (status === 'END') {
                                const nextCount = Math.max(0, currentCount - 1);
                                next[countKey] = nextCount;
                                next[`${key}_busy`] = nextCount > 0;
                            } else {
                                // Fallback for legacy events without START/END
                                next[key] = uniqueTime;
                            }
                        };

                        if (event === 'MEMORY_ACCESS' || event === 'STATE_SAVE' || event === 'DISK') {
                            next.disk = uniqueTime;
                            next.disk_agent = data?.agent;
                            next.disk_save = (data?.op === 'SAVE' || event === 'STATE_SAVE');
                        }
                        if (event === 'LLM_ACTIVITY' || event === 'LLM') {
                            updateBusy('llm');
                            next.llm_step = data?.step;
                        }
                        if (event === 'EGO_CHECK' || event === 'EGO') {
                            updateBusy('ego');
                            next.ego_agent = data?.agent;
                        }
                        if (event === 'PHYSICS_SYNC' || event === 'PHYS') {
                            updateBusy('phys');
                            next.phys_type = data?.type;
                        }

                        return next;
                    });
                } else if (msg.type === 'system_log') {
                    const content = msg.content;
                    setSystemLogs(prev => [...prev.slice(-1499), content]);
                    const match = content.match(/\[(.*?)\] \[(.*?)\] > (.*)/);
                    if (match) {
                        const module = match[2];
                        const message = match[3];

                        if (module === 'SIMULATION') {
                            if (message.includes("Processing turn") || message.includes("Entering dream phase")) {
                                setStatusText(message.toUpperCase());
                                setActiveAgents({});
                            } else if (message.includes("Turn complete") || message.includes("Session finalized")) {
                                setStatusText("System: READY // Waiting for command...");
                                setActiveAgents({});
                            }
                        } else {
                            // All other modules (Agents, Physics, System components)
                            setActiveAgents(prev => ({
                                ...prev,
                                [module]: message
                            }));
                        }
                    }

                } else if (msg.type === 'history') {

                    // Load historical posts
                    const history = msg.data.map(item => {
                        // Normalize history items to match post structure
                        if (item.type === 'user') return { _id: nextPostId(), type: 'user', content: item.content, timestamp: item.timestamp };
                        if (item.type === 'agent_post') return { _id: nextPostId(), type: 'agent_post', data: item.data, timestamp: item.timestamp };
                        return { _id: nextPostId(), ...item };
                    });
                    setPosts(history);
                } else if (msg.type === 'user_post') {
                    setPosts(prev => [...prev, { _id: nextPostId(), type: 'user', content: msg.content, timestamp: msg.timestamp || new Date().toISOString() }]);
                } else if (msg.type === 'agent_post') {
                    // Legacy / fallback if non-streaming
                    const agentData = msg.data;
                    // Use backend timestamp if available, else fallback
                    const ts = agentData.timestamp || new Date().toISOString();
                    setPosts(prev => [...prev, { _id: nextPostId(), type: 'agent_post', data: agentData, timestamp: ts }]);
                    setAgents(prev => prev.map(a => a.id === agentData.id ? {
                        ...a,
                        stats: agentData.stats,
                        relationships: agentData.relationships,
                        goals: agentData.goals || a.goals // Update goals if present
                    } : a));

                } else if (msg.type === 'stream_start') {
                    // FIX MAJ-06: Use msg.agent (server sends 'agent' field) instead of msg.id (undefined)
                    const streamKey = msg.agent || msg.id || msg.name;
                    if (msg.is_dream) {
                        // Initialize a dream placeholder
                        setPosts(prev => [...prev, {
                            _id: nextPostId(),
                            type: 'dream_stream',
                            isStreaming: true,
                            streamId: streamKey,
                            agentName: msg.name,
                            content: ""
                        }]);
                    } else {
                        // Initialize a new agent placeholder post
                        setPosts(prev => [...prev, {
                            _id: nextPostId(),
                            type: 'agent_post',
                            isStreaming: true,
                            streamId: streamKey,
                            timestamp: new Date().toISOString(),
                            data: {
                                id: msg.agent_id,
                                name: msg.name,
                                public_text: "",
                                stats: msg.stats,
                                hidden_text: ""
                            }
                        }]);
                    }


                } else if (msg.type === 'stream_chunk') {
                    // FIX MAJ-06: Use msg.agent instead of msg.id
                    const streamKey = msg.agent || msg.id;
                    // Find the streaming post and append text
                    setPosts(prev => {
                        const newPosts = [...prev];
                        const lastIdx = newPosts.findIndex(p => p.streamId === streamKey);
                        if (lastIdx !== -1) {
                            const updatedPost = { ...newPosts[lastIdx] };
                            if (updatedPost.type === 'dream_stream') {
                                updatedPost.content = (updatedPost.content || "") + msg.content;
                            } else {
                                updatedPost.data = {
                                    ...updatedPost.data,
                                    public_text: updatedPost.data.public_text + msg.content
                                };
                            }
                            newPosts[lastIdx] = updatedPost;
                        }
                        return newPosts;
                    });

                } else if (msg.type === 'stream_end') {
                    // FIX MAJ-06: Use msg.agent instead of msg.id
                    const streamKey = msg.agent || msg.id;
                    // Finalize the post with the full authoritative data
                    setPosts(prev => {
                        const newPosts = [...prev];
                        const lastIdx = newPosts.findIndex(p => p.streamId === streamKey);
                        if (lastIdx !== -1) {
                            const originalPost = newPosts[lastIdx];
                            if (originalPost.type === 'dream_stream') {
                                // Convert to a finalized dream post or keep as is but marked not streaming
                                newPosts[lastIdx] = {
                                    ...originalPost,
                                    isStreaming: false,
                                    content: msg.full_data.entry // Authoritative full text
                                };
                            } else {
                                newPosts[lastIdx] = {
                                    data: msg.full_data,
                                    timestamp: originalPost.timestamp || new Date().toISOString()
                                };
                                // Update stats and relationships globally when stream finishes
                                setAgents(prev => prev.map(a => a.id === msg.full_data.id ? {
                                    ...a,
                                    stats: msg.full_data.stats,
                                    relationships: msg.full_data.relationships,
                                    goals: msg.full_data.goals || a.goals // Update goals on stream end too
                                } : a));
                            }
                        }
                        return newPosts;
                    });


                } else if (msg.type === 'system') {
                    if (msg.content === "SESSION ENDED. DREAMING...") {
                        document.body.classList.add('dream-mode');
                        setIsDreaming(true);
                    } else if (msg.content.includes("DREAM PHASE COMPLETE")) {
                        document.body.classList.remove('dream-mode');
                        setIsDreaming(false);
                    }
                    setPosts(prev => [...prev, { _id: nextPostId(), type: 'system', content: msg.content }]);
                } else if (msg.type === 'dream') {
                    setPosts(prev => [...prev, { _id: nextPostId(), type: 'dream', data: msg.data }]);
                    // Auto-wakeup: Remove dream mode after 8 seconds (legacy fallback)
                    setTimeout(() => {
                        document.body.classList.remove('dream-mode');
                        setIsDreaming(false);
                    }, 8000);
                }
            };

            // FIX CRIT-04: Reconnect with exponential backoff on close
            ws.onclose = () => {
                setConnected(false);
                if (isMounted) {
                    console.log(`WebSocket closed. Reconnecting in ${retryDelay / 1000}s...`);
                    setTimeout(connect, retryDelay);
                    retryDelay = Math.min(retryDelay * 2, 30000); // Cap at 30s
                }
            };

            ws.onerror = (err) => {
                console.error("WebSocket error:", err);
                ws.close(); // Trigger onclose → reconnect
            };
        };

        connect();

        return () => {
            isMounted = false;
            ws?.close();
        };
    }, []);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [posts]);

    const handleSubmit = (e) => {
        e.preventDefault();
        if (!input.trim() || !wsRef.current) return;

        setActivity(prev => ({ ...prev, net: Date.now() }));
        wsRef.current.send(JSON.stringify({ type: 'chat', content: input }));
        setInput("");
    };

    const handleOpenGraph = (id) => {
        setSelectedAgentId(id);
        setShowGraphModal(true);
    };

    return (
        <div className="flex min-h-screen bg-claw-bg font-sans text-sm selection:bg-red-900 selection:text-white relative overflow-hidden">
            {/* CRT & Vignette Overlays */}
            <div className="crt-overlay"></div>
            <div className="mic-vignette"></div>

            {/* NEW: Left Sidebar */}
            <Sidebar
                agents={agents}
                posts={posts}
                statusText={statusText}
                activeAgents={activeAgents}
                systemLogs={systemLogs}
                heartbeatStats={heartbeatStats}
                agentStatuses={agentStatuses}
                systemState={systemState}
                activity={activity}
                onOpenGraph={handleOpenGraph}
            />

            {/* Modals */}
            <SyndicateGraphModal
                isOpen={showGraphModal}
                onClose={() => setShowGraphModal(false)}
                agents={agents}
                focusedAgentId={selectedAgentId}
            />

            {/* Main Content Area */}
            <div className="flex-1 flex flex-col h-screen relative">

                {/*Header */}
                <div className="bg-claw-bg z-20 p-4 pb-0">
                    <div className="max-w-3xl mx-auto">
                        <div className="text-xl font-bold text-[#af0a0f] text-center tracking-tight border-b-2 border-[#af0a0f] pb-2">
                            /ic/ - Iron Council Simulation <span className="text-xs font-normal text-gray-500">[Thread #849102]</span>
                        </div>
                    </div>
                </div>

                {/* Scrollable Thread View */}
                <div className="flex-1 overflow-y-auto p-4 pt-0 pb-32 scrollbar-hide">
                    <div className="max-w-3xl mx-auto">
                        {/* Posts Container */}
                        <div className="space-y-4 post-container pt-6">
                            {posts.map((post, idx) => {
                                // Skip dream posts in the main chat as they are now in the sidebar
                                if (post.type === 'dream' || post.type === 'dream_stream') return null;
                                return <Post key={post._id || idx} post={post} />;
                            })}

                            {/* Dream Mode Indicator in Main Chat */}
                            {isDreaming && (
                                <div className="p-4 bg-indigo-900 border-2 border-indigo-500 text-center animate-pulse shadow-sharp my-4">
                                    <div className="text-white font-bold text-lg tracking-widest uppercase mb-1">
                                        ⚠️ SYSTEM DREAMING ⚠️
                                    </div>
                                    <div className="text-indigo-200 text-xs font-mono">
                                        The council is reflecting via the Neural Link (Subconscious Log).
                                        <br />
                                        <span className="font-bold underline">CHECK THE SIDEBAR</span> for subjective memory formation.
                                    </div>
                                </div>
                            )}

                            <div ref={bottomRef} />
                        </div>
                    </div>
                </div>

                {/* Fixed Input Bar at Bottom */}
                <div className="absolute bottom-0 left-0 w-full bg-[#d6daf0] border-t-2 border-claw-border p-3 shadow-2xl z-40">
                    <div className="max-w-3xl mx-auto flex gap-3">
                        <div className="text-[11px] self-center hidden sm:flex items-center gap-1 font-bold text-[#af0a0f] uppercase tracking-widest whitespace-nowrap">
                            <span className="w-2 h-2 bg-red-600 rounded-full animate-pulse"></span>
                            CHAIRMAN
                        </div>
                        <form onSubmit={handleSubmit} className="flex-1 flex gap-2">
                            <input
                                type="text"
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                className="flex-1 border-2 border-claw-border p-2 text-[14px] focus:ring-2 focus:ring-red-500 outline-none shadow-sharp font-mono bg-white rounded-none"
                                placeholder={connected ? ">> BROADCAST TO THE COUNCIL_" : "ESTABLISHING UPLINK..."}
                                disabled={!connected}
                            />
                            <button
                                type="submit"
                                disabled={!connected}
                                className="px-6 py-2 bg-[#af0a0f] text-white border-2 border-black font-bold hover:bg-red-800 disabled:opacity-50 text-[11px] uppercase tracking-wider shadow-sharp active:shadow-none translate-y-[-2px] active:translate-y-[0px] transition-all"
                            >
                                Post
                            </button>
                        </form>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default App;
