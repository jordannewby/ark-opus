import re

file_path = r'd:\\Ares Engine\\static\\js\\console.js'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update Agent Nodes visualization to use the Mobile Toast Notification
js_agent_update = """
function updateAgentUI(activeNode) {
    // Desktop / Static nodes
    Object.values(els.agentNodes).forEach(node => node.classList.remove('agent-node-active'));
    if (activeNode && els.agentNodes[activeNode]) {
        els.agentNodes[activeNode].classList.add('agent-node-active');
    }
    
    // Mobile Toast Node
    const mobileToast = document.getElementById('mobile-agent-toast');
    const mobileText = document.getElementById('mobile-agent-text');
    
    if (mobileToast && mobileText) {
        if (!activeNode) {
            mobileToast.classList.add('opacity-0');
            mobileToast.classList.remove('opacity-100');
            mobileText.textContent = 'Standby';
        } else {
            let label = 'Working...';
            if (activeNode === 'research') label = 'Agent: Researching';
            if (activeNode === 'psychology') label = 'Agent: Strategizing';
            if (activeNode === 'writer') label = 'Agent: Writing Article';
            
            mobileText.textContent = label;
            mobileToast.classList.remove('opacity-0');
            mobileToast.classList.add('opacity-100');
        }
    }
}
"""
content = re.sub(r'function updateAgentUI\(activeNode\) \{[\s\S]*?\}', js_agent_update.strip(), content, count=1)

# 2. Update Sidebar Toggle Logic for Mobile Responsiveness
sidebar_logic_pattern = r'// SIDEBAR TOGGLE LOGIC[\s\S]*'
new_sidebar_logic = """// SIDEBAR TOGGLE LOGIC
const toggleSidebarBtn = document.getElementById('toggle-sidebar-btn');
const leftSidebar = document.getElementById('left-sidebar');
const sidebarBackdrop = document.getElementById('sidebar-backdrop');

function toggleSidebar() {
    if (!leftSidebar) return;
    
    const isMobile = window.innerWidth < 768; // Tailwind md breakpoint
    
    if (isMobile) {
        // Mobile execution: toggle slide-in active class and backdrop
        const isActive = leftSidebar.classList.contains('sidebar-mobile-active');
        if (isActive) {
            leftSidebar.classList.remove('sidebar-mobile-active');
            if (sidebarBackdrop) {
                sidebarBackdrop.classList.remove('opacity-100');
                sidebarBackdrop.classList.add('pointer-events-none');
            }
        } else {
            leftSidebar.classList.add('sidebar-mobile-active');
            if (sidebarBackdrop) {
                sidebarBackdrop.classList.remove('pointer-events-none');
                sidebarBackdrop.classList.add('opacity-100');
            }
        }
    } else {
        // Desktop execution: toggle width collapse
        leftSidebar.classList.toggle('sidebar-collapsed');
        if (leftSidebar.classList.contains('sidebar-collapsed')) {
            if (toggleSidebarBtn) {
                toggleSidebarBtn.classList.add('bg-[rgba(255,255,255,0.08)]');
                toggleSidebarBtn.classList.remove('bg-[rgba(255,255,255,0.03)]');
            }
        } else {
            if (toggleSidebarBtn) {
                toggleSidebarBtn.classList.add('bg-[rgba(255,255,255,0.03)]');
                toggleSidebarBtn.classList.remove('bg-[rgba(255,255,255,0.08)]');
            }
        }
    }
}

if (toggleSidebarBtn) toggleSidebarBtn.addEventListener('click', toggleSidebar);
if (sidebarBackdrop) sidebarBackdrop.addEventListener('click', toggleSidebar);

// Ensure sidebar reset on resize crossing the breakpoint
window.addEventListener('resize', () => {
    if (window.innerWidth >= 768 && leftSidebar && leftSidebar.classList.contains('sidebar-mobile-active')) {
        leftSidebar.classList.remove('sidebar-mobile-active');
        if (sidebarBackdrop) {
            sidebarBackdrop.classList.remove('opacity-100');
            sidebarBackdrop.classList.add('pointer-events-none');
        }
    }
});
"""

if '// SIDEBAR TOGGLE LOGIC' in content:
    content = re.sub(sidebar_logic_pattern, new_sidebar_logic, content)
else:
    content += '\\n\\n' + new_sidebar_logic

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("console.js patching successful.")
