
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
    const [statusText, setStatusText] = useState("System: READY // Waiting for command...");
    const [activeAgents, setActiveAgents] = useState({});
    const [showGraphModal, setShowGraphModal] = useState(false);
    const [selectedAgentId, setSelectedAgentId] = useState(null);
    const [systemLogs, setSystemLogs] = useState([]);
    const [heartbeatStats, setHeartbeatStats] = useState({ uptime: 0, mem: "64.0MB", status: "READY" });

    useEffect(() => {
        // Connect to WebSocket
        const ws = new WebSocket("ws://localhost:8000/ws/council");
        wsRef.current = ws;

        ws.onopen = () => {
            console.log("Connected to Council");
            setConnected(true);
        };

        ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            if (msg.type === 'init') {
                setAgents(msg.data);
            } else if (msg.type === 'heartbeat_pulse') {
                setHeartbeatStats(msg.stats);
            } else if (msg.type === 'relationship_update') {
                // Update relationships specifically 
                setAgents(prev => prev.map(a => a.id === msg.agent_id ? { ...a, relationships: msg.relationships } : a));
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
                    if (item.type === 'user') return { type: 'user', content: item.content };
                    if (item.type === 'agent_post') return { type: 'agent_post', data: item.data };
                    return item;
                });
                setPosts(history);
            } else if (msg.type === 'user_post') {
                setPosts(prev => [...prev, { type: 'user', content: msg.content }]);
            } else if (msg.type === 'agent_post') {
                // Legacy / fallback if non-streaming
                const agentData = msg.data;
                setPosts(prev => [...prev, { type: 'agent_post', data: agentData }]);
                setAgents(prev => prev.map(a => a.id === agentData.id ? { ...a, stats: agentData.stats, relationships: agentData.relationships } : a));

            } else if (msg.type === 'stream_start') {
                if (msg.is_dream) {
                    // Initialize a dream placeholder
                    setPosts(prev => [...prev, {
                        type: 'dream_stream',
                        isStreaming: true,
                        streamId: msg.id,
                        agentName: msg.name,
                        content: ""
                    }]);
                } else {
                    // Initialize a new agent placeholder post
                    setPosts(prev => [...prev, {
                        type: 'agent_post',
                        isStreaming: true,
                        streamId: msg.id,
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
                // Find the streaming post and append text
                setPosts(prev => {
                    const newPosts = [...prev];
                    const lastIdx = newPosts.findIndex(p => p.streamId === msg.id);
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
                // Finalize the post with the full authoritative data
                setPosts(prev => {
                    const newPosts = [...prev];
                    const lastIdx = newPosts.findIndex(p => p.streamId === msg.id);
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
                                type: 'agent_post',
                                data: msg.full_data
                            };
                            // Update stats and relationships globally when stream finishes
                            setAgents(prev => prev.map(a => a.id === msg.full_data.id ? {
                                ...a,
                                stats: msg.full_data.stats,
                                relationships: msg.full_data.relationships
                            } : a));
                        }
                    }
                    return newPosts;
                });


            } else if (msg.type === 'system') {
                if (msg.content === "SESSION ENDED. DREAMING...") {
                    document.body.classList.add('dream-mode');
                }
                setPosts(prev => [...prev, { type: 'system', content: msg.content }]);
            } else if (msg.type === 'dream') {
                setPosts(prev => [...prev, { type: 'dream', data: msg.data }]);
                // Auto-wakeup: Remove dream mode after 8 seconds (enough to read)
                setTimeout(() => {
                    document.body.classList.remove('dream-mode');
                }, 8000);
            }
        };

        ws.onclose = () => setConnected(false);

        return () => ws.close();
    }, []);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [posts]);

    const handleSubmit = (e) => {
        e.preventDefault();
        if (!input.trim() || !wsRef.current) return;

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

                {/* Scrollable Thread View */}
                <div className="flex-1 overflow-y-auto p-4 pb-32 scrollbar-hide">
                    <div className="max-w-3xl mx-auto">
                        {/* Thread Title */}
                        <div className="text-xl font-bold text-[#af0a0f] mb-6 text-center tracking-tight border-b-2 border-[#af0a0f] pb-2">
                            /ic/ - Iron Council Simulation <span className="text-xs font-normal text-gray-500">[Thread #849102]</span>
                        </div>

                        {/* Posts Container */}
                        <div className="space-y-4 post-container">
                            {posts.map((post, idx) => {
                                // Skip dream posts in the main chat as they are now in the sidebar
                                if (post.type === 'dream' || post.type === 'dream_stream') return null;
                                return <Post key={idx} post={post} />;
                            })}
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
