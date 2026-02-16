
/**
 * Formats chat history including hidden thoughts for export.
 */
export const formatChatHistory = (posts) => {
    let output = "IRON_COUNCIL // CHAT_LOG_EXPORT\n";
    output += "===============================\n\n";

    posts.forEach(post => {
        const timestamp = post.timestamp ? new Date(post.timestamp).toLocaleString() : "N/A";

        if (post.type === 'user') {
            output += `[${timestamp}] [USER] > ${post.content}\n\n`;
        } else if (post.type === 'agent_post') {
            const data = post.data || {};
            output += `[${timestamp}] [${data.name || 'UNKNOWN_AGENT'}]\n`;
            if (data.hidden_text) {
                output += `THOUGHTS: ${data.hidden_text}\n`;
            }
            output += `MESSAGE: ${data.public_text || data.content || ""}\n\n`;
        } else if (post.type === 'system') {
            output += `[${timestamp}] [SYSTEM] !! ${post.content}\n\n`;
        }
    });

    return output;
};

/**
 * Formats dream diary entries for export.
 */
export const formatDreamDiary = (posts) => {
    let output = "IRON_COUNCIL // NEURAL_LINK_DIARY_EXPORT\n";
    output += "===============================\n\n";

    const dreamPosts = posts.filter(p => p.type === 'dream' || p.type === 'dream_stream' || p.type === 'dream_session_marker');

    dreamPosts.forEach(post => {
        if (post.type === 'dream_session_marker') {
            const timestamp = new Date(post.timestamp).toLocaleString();
            output += `\n--- SESSION START: ${timestamp} ---\n\n`;
        } else if (post.type === 'dream') {
            const entries = Array.isArray(post.data) ? post.data : [post.data];
            entries.forEach(entry => {
                output += `[${entry.agent_name}] : "${entry.entry}"\n`;
            });
            output += "\n";
        } else if (post.type === 'dream_stream') {
            output += `[${post.agentName || "Unknown"}] : "${post.content}"\n\n`;
        }
    });

    return output;
};

/**
 * Triggers a file download in the browser.
 */
export const downloadTxtFile = (content, filename) => {
    const element = document.createElement("a");
    const file = new Blob([content], { type: 'text/plain' });
    element.href = URL.createObjectURL(file);
    element.download = filename;
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
};
