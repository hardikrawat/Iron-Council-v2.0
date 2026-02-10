
import React, { useState, useEffect, useRef } from 'react';
import BoardHeader from './components/BoardHeader';
import Post from './components/Post';
import ThreadActivityBar from './components/ThreadActivityBar';
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
            } else if (msg.type === 'system_log') {
                const content = msg.content;
                const match = content.match(/\[(.*?)\] \[(.*?)\] > (.*)/);
                if (match) {
                    const module = match[2];
                    const message = match[3];

                    if (module === 'SIMULATION') {
                        if (message.includes("Processing turn") || message.includes("Entering dream phase")) {
                            setStatusText("");
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
                setAgents(prev => prev.map(a => a.id === agentData.id ? { ...a, stats: agentData.stats } : a));

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
                            hidden_text: "..."
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
        <div className="min-h-screen bg-claw-bg font-sans text-sm selection:bg-red-900 selection:text-white pb-24 relative">
            {/* CRT & Vignette Overlays */}
            <div className="crt-overlay"></div>
            <div className="mic-vignette"></div>

            {/* Top Bar: Board List / Stats */}
            <BoardHeader agents={agents} onOpenGraph={handleOpenGraph} />

            {/* Modals */}
            <SyndicateGraphModal
                isOpen={showGraphModal}
                onClose={() => setShowGraphModal(false)}
                agents={agents}
                focusedAgentId={selectedAgentId}
            />

            {/* Main Content Area */}
            <div className="max-w-4xl mx-auto mt-2 p-2 sm:p-4">

                {/* Thread Title */}
                <div className="text-xl font-bold text-[#af0a0f] mb-4 text-center tracking-tight">
                    /ic/ - Iron Council Simulation <span className="text-xs font-normal text-gray-500">[Thread #849102]</span>
                </div>

                {/* Posts Container */}
                <div className="space-y-3 post-container">
                    {posts.map((post, idx) => {
                        if (post.type === 'dream') {
                            return (
                                <div key={idx} className="dream-card">
                                    <div className="dream-card-header">
                                        <span>&gt;&gt; SUBCONSCIOUS_DUMP // BATCH_LOG</span>
                                        <div className="dream-pulse"></div>
                                    </div>
                                    {post.data.map((entry, i) => (
                                        <div key={i} className="mb-4 last:mb-0">
                                            <div className="font-bold text-xs uppercase tracking-wider text-indigo-900 mb-1">{entry.agent_name}</div>
                                            <div className="text-base leading-relaxed text-gray-800 italic border-l-2 border-indigo-100 pl-3">
                                                "{entry.entry}"
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            );
                        }
                        if (post.type === 'dream_stream') {
                            return (
                                <div key={idx} className="dream-card">
                                    <div className="dream-card-header">
                                        <span>&gt;&gt; PSYCH_REPORT // {post.agentName.toUpperCase()}</span>
                                        {post.isStreaming && <div className="dream-pulse"></div>}
                                    </div>
                                    <div className="text-base leading-relaxed text-gray-800 italic pl-2">
                                        {post.content}
                                    </div>
                                </div>
                            );
                        }
                        return <Post key={idx} post={post} />;
                    })}

                    <div ref={bottomRef} />
                </div>
            </div>

            {/* Footer Container: Activity Bar + Input */}
            <div className="fixed bottom-0 left-0 w-full z-40">
                {/* 1. Activity Bar */}
                <ThreadActivityBar statusText={statusText} activeAgents={activeAgents} />


                {/* 2. Input Bar */}
                <div className="bg-[#d6daf0] border-t border-claw-border p-2 shadow-lg">
                    <div className="max-w-4xl mx-auto flex gap-2">
                        <div className="text-[10px] self-center hidden sm:block font-bold text-gray-600 uppercase tracking-widest">
                            [CHAIRMAN]
                        </div>
                        <form onSubmit={handleSubmit} className="flex-1 flex gap-2">
                            <input
                                type="text"
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                className="flex-1 border border-gray-600 p-1 px-2 text-[13px] focus:border-blue-900 outline-none shadow-inner font-sans rounded-none"
                                placeholder={connected ? ">> Issue command" : "Connecting..."}
                                disabled={!connected}
                            />
                            <button
                                type="submit"
                                disabled={!connected}
                                className="px-4 py-1 bg-[#EEF2FF] border border-gray-600 font-bold hover:bg-white disabled:opacity-50 text-[10px] uppercase tracking-wide shadow-sharp"
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
