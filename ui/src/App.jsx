
import React, { useState, useEffect, useRef } from 'react';
import SidebarLeft from './components/SidebarLeft';
import SidebarRight from './components/SidebarRight';
import Post from './components/Post';
import SyndicateGraphModal from './components/SyndicateGraphModal';

function App() {
    const [agents, setAgents] = useState([]);
    const [posts, setPosts] = useState([]);
    const [connected, setConnected] = useState(false);
    const [input, setInput] = useState("");
    const wsRef = useRef(null);
    const bottomRef = useRef(null);
    // FIX: Ref to access current agents inside WebSocket closure
    const agentsRef = useRef([]);
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
    const [drainStatus, setDrainStatus] = useState(null); // { buffered: [], total: 4, phase: 'DRAINING'|'CLEAR' }
    const [verdicts, setVerdicts] = useState([]); // Array of { agent, goal, delta, details, timestamp }
    const [goalHistory, setGoalHistory] = useState({}); // { AgentName: [progress_values] }

    // FIX: Keep agentsRef in sync so WebSocket handler sees current agents
    useEffect(() => { agentsRef.current = agents; }, [agents]);

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
                } else if (msg.type === 'initial_sync') {
                    // Populate agents and their current statuses
                    const { agents: syncAgents, heartbeat: syncHeartbeat } = msg.data;
                    setAgents(syncAgents);
                    if (syncHeartbeat) setHeartbeatStats(syncHeartbeat);

                    // Populate the status map
                    const statusMap = {};
                    syncAgents.forEach(a => {
                        statusMap[a.id] = {
                            status: a.status,
                            phase: a.phase,
                            details: a.details
                        };
                    });
                    setAgentStatuses(statusMap);
                } else if (msg.type === 'heartbeat_pulse') {
                    setHeartbeatStats(msg.stats);
                    // Sync CORE LED with actual backend pulse
                    setActivity(prev => ({ ...prev, heart: Date.now() }));
                } else if (msg.type === 'relationship_update') {
                    // Update relationships specifically 
                    setAgents(prev => prev.map(a => a.id === msg.agent_id ? { ...a, relationships: msg.relationships } : a));
                } else if (msg.type === 'agent_status_update') {
                    // Handle Narrative Verdicts specifically for the Ledger/Plotter
                    if (msg.data.status === 'NARRATIVE_VERDICT') {
                        const { agent, goal, delta, details, goals, stats } = msg.data;
                        const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

                        setVerdicts(prev => [{ agent, goal, delta, details, timestamp }, ...prev].slice(0, 10));

                        // Update Goal History for Plotter
                        // FIX: Use agentsRef.current instead of stale `agents` closure
                        setGoalHistory(prev => {
                            const newHistory = { ...prev };
                            const currentAgents = agentsRef.current;
                            currentAgents.forEach(a => {
                                const prog = (a.id === agent)
                                    ? (goals.find(g => g.active)?.progress || 0)
                                    : (a.goals?.find(g => g.active)?.progress || 0);

                                if (!newHistory[a.name]) newHistory[a.name] = [];
                                newHistory[a.name] = [...newHistory[a.name], prog].slice(-20);
                            });
                            return newHistory;
                        });

                        // Also update agents list so bars move
                        setAgents(prev => prev.map(a => a.id === agent ? {
                            ...a,
                            stats: stats,
                            goals: goals
                        } : a));
                    }

                    setAgentStatuses(prev => {
                        const prevStatus = prev[msg.data.agent] || {};
                        return {
                            ...prev,
                            [msg.data.agent]: {
                                status: msg.data.status,
                                details: msg.data.details,
                                // FIX: Preserve previous phase if new update doesn't provide one
                                // This prevents relationship updates from clobbering the OODA overlay
                                phase: msg.data.phase || prevStatus.phase,
                                updatedAt: Date.now()
                            }
                        };
                    });
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
                            next.llm_agent = data?.agent;
                            // Capture performance metrics
                            // Capture performance metrics
                            if (data?.tps !== undefined) next.llm_activity_base = data.tps;
                            if (data?.model !== undefined) next.llm_model = data.model;
                            if (data?.signal !== undefined) next.llm_signal = data.signal;
                            if (data?.synaptic_load !== undefined) next.llm_load = data.synaptic_load;
                            if (data?.total_requests !== undefined) next.llm_requests = data.total_requests;
                            if (data?.active_requests !== undefined) next.llm_active_requests = data.active_requests;
                            if (data?.pending_requests !== undefined) next.llm_pending_requests = data.pending_requests;
                            if (data?.queue_latency !== undefined) next.llm_queue_latency = data.queue_latency;
                            if (data?.total_input_tokens !== undefined) next.llm_input_tokens = data.total_input_tokens;
                            if (data?.total_output_tokens !== undefined) next.llm_output_tokens = data.total_output_tokens;

                            // Concurrent Pressure Flux Model (mF)
                            // 1. Static Pressure: Each active or pending link adds 15 mF of base intensity
                            // 2. Dynamic Flow: Each TPS adds 5 mF of flux
                            const totalLinks = (next.llm_active_requests || 0) + (next.llm_pending_requests || 0);
                            const pressureFlux = totalLinks * 15;
                            const flowFlux = (next.llm_activity_base || 0) * 5;

                            next.llm_activity = Math.min(100, Math.round((pressureFlux + flowFlux) * 10) / 10);

                            // Auto-decay base activity if link is severed
                            if (totalLinks === 0) {
                                next.llm_activity = 0;
                                next.llm_activity_base = 0;
                            }
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
                        // FIX: Use findLastIndex to ensure we update the MOST RECENT stream for this agent
                        const lastIdx = newPosts.findLastIndex(p => p.streamId === streamKey);
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
                        // FIX: Use findLastIndex to ensure we target the MOST RECENT stream
                        const lastIdx = newPosts.findLastIndex(p => p.streamId === streamKey);
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
                                // FIX BUG-07: Preserve _id, type, streamId from original post
                                newPosts[lastIdx] = {
                                    ...originalPost,
                                    isStreaming: false,
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
                    if (msg.content.includes("SESSION ENDED") || msg.content.includes("SESSION ENDING")) {
                        document.body.classList.add('dream-mode');
                        setIsDreaming(true);
                    } else if (msg.content.includes("DREAM PHASE COMPLETE")) {
                        document.body.classList.remove('dream-mode');
                        setIsDreaming(false);
                        setDrainStatus(null);
                    }
                    setPosts(prev => [...prev, { _id: nextPostId(), type: 'system', content: msg.content }]);
                } else if (msg.type === 'dream') {
                    setPosts(prev => [...prev, { _id: nextPostId(), type: 'dream', data: msg.data }]);
                    // Auto-wakeup: Remove dream mode after 8 seconds (legacy fallback)
                    setTimeout(() => {
                        document.body.classList.remove('dream-mode');
                        setIsDreaming(false);
                    }, 8000);
                } else if (msg.type === 'drain_status') {
                    setDrainStatus(msg);
                } else if (msg.type === 'dream_session_marker') {
                    setPosts(prev => [...prev, {
                        _id: nextPostId(),
                        type: 'dream_session_marker',
                        timestamp: msg.timestamp,
                        sessionId: msg.session_id
                    }]);
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
        <div className="flex h-screen bg-claw-bg font-sans text-sm selection:bg-red-900 selection:text-white relative overflow-hidden">
            {/* CRT & Vignette Overlays */}
            <div className="crt-overlay pointer-events-none z-[100]"></div>
            <div className="mic-vignette pointer-events-none z-[100]"></div>

            {/* Left Sidebar: Operational */}
            <SidebarLeft
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

            {/* Main Content Area: Centered Chat */}
            <div className="flex-1 flex flex-col h-screen relative z-10 overflow-hidden bg-white/50 backdrop-blur-sm shadow-inner">

                {/*Header */}
                <div className="bg-white/80 border-b border-gray-200 z-20 p-4 pb-2 backdrop-blur-md">
                    <div className="max-w-3xl mx-auto">
                        <div className="text-xl font-bold text-[#af0a0f] text-center tracking-tight border-b-2 border-[#af0a0f] pb-2">
                            IRON_COUNCIL // COMMAND_INTERFACE
                        </div>
                    </div>
                </div>

                {/* Posts Area */}
                <div className="flex-1 overflow-y-auto p-4 scrollbar-hide">
                    <div className="max-w-3xl mx-auto space-y-6 post-container">
                        {posts.map((post) => (
                            // Only show user and agent posts in the main chat
                            (post.type === 'user' || post.type === 'agent_post' || post.type === 'system') &&
                            <Post key={post._id} post={post} />
                        ))}

                        {/* Dream Mode Indicator in Main Chat */}
                        {isDreaming && (
                            <div className="p-4 bg-amber-50 border-2 border-amber-700 text-center shadow-sharp my-4 dream-banner">
                                {drainStatus && drainStatus.phase === 'DRAINING' ? (
                                    <>
                                        <div className="text-amber-900 font-bold text-sm tracking-widest uppercase mb-2 font-mono">
                                            ⚙ FLUSHING PIPELINE
                                        </div>
                                        <div className="flex gap-0.5 max-w-xs mx-auto mb-2">
                                            {Array.from({ length: drainStatus.total }).map((_, i) => (
                                                <div key={i} className={`flex-1 h-2 border border-amber-700 transition-all duration-500 ${i < (drainStatus.total - drainStatus.buffered.length)
                                                    ? 'bg-amber-600'
                                                    : 'bg-amber-100 animate-pulse'
                                                    }`} />
                                            ))}
                                        </div>
                                        <div className="text-amber-800 text-[10px] font-mono">
                                            {drainStatus.buffered.length} AGENT{drainStatus.buffered.length !== 1 ? 'S' : ''} BUFFERED: {drainStatus.buffered.join(', ')}
                                        </div>
                                    </>
                                ) : (
                                    <>
                                        <div className="text-amber-900 font-bold text-lg tracking-widest uppercase mb-1 font-mono">
                                            ⚠ SYSTEM DREAMING ⚠
                                        </div>
                                        <div className="text-amber-800 text-xs font-mono">
                                            The council is reflecting via the Neural Link (Subconscious Log).
                                            <br />
                                            <span className="font-bold underline">CHECK THE SIDEBAR</span> for subjective memory formation.
                                        </div>
                                    </>
                                )}
                            </div>
                        )}
                        <div ref={bottomRef} />
                    </div>
                </div>

                {/* Input Area */}
                <div className="p-4 bg-white/80 backdrop-blur-md border-t border-gray-200 z-20">
                    <form onSubmit={handleSubmit} className="max-w-3xl mx-auto flex gap-2">
                        <input
                            type="text"
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            placeholder="COMMUNICATE PROTOCOL..."
                            className="flex-1 bg-gray-50 border-2 border-claw-border p-2 font-mono text-sm focus:outline-none focus:ring-1 focus:ring-[#af0a0f] shadow-inner"
                        />
                        <button
                            type="submit"
                            className="bg-[#af0a0f] text-white px-6 py-2 font-bold uppercase tracking-widest shadow-sharp hover:bg-red-800 active:shadow-none transition-all"
                        >
                            SEND
                        </button>
                    </form>
                </div>
            </div>

            {/* Right Sidebar: Intelligence */}
            <SidebarRight
                agents={agents}
                posts={posts}
                heartbeatStats={heartbeatStats}
                activity={activity}
                verdicts={verdicts}
                goalHistory={goalHistory}
                statusText={statusText}
            />

            {/* Modals */}
            <SyndicateGraphModal
                isOpen={showGraphModal}
                onClose={() => setShowGraphModal(false)}
                agents={agents}
                focusedAgentId={selectedAgentId}
            />
        </div>
    );
};

export default App;
