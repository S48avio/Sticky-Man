
<img src="logo.png" width="45" valign="middle" alt="StickyMan Logo">
 StickyMan

A lightweight, customizable, always-on-top AI assistant overlay built
specifically for Linux environments. It runs as a frameless, non-intrusive
floating window anchored to your workspace, providing instant access to
OpenRouter's free conversational engines.

💡 What is StickyMan?

StickyMan is designed to eliminate context-switching during your daily workflow.
Instead of leaving your code editor, browser, or terminal to interact with an AI
model, StickyMan lets you invoke an overlay instantly using a global system
shortcut.

It runs on a high-speed, single-instance architecture that minimizes startup
latency, stays out of your way when you are inactive, and formats its outputs
cleanly for developers.

🚀 Key Features

  - Dynamic Startup Handover (under 15ms latency): Uses a lightweight,
    pure-Python socket listener. When you invoke the keyboard shortcut, the
    command handsoff your current clipboard selection directly to the running
    window and exits immediately, bypassing heavy GUI framework initialization
    overhead.
  - Real-Time Token Streaming: Supports real-time text generation directly
    inside the chat interface with a smooth typing effect and an active
    auto-scroll tracker.
  - Collapsible Deep Thinking (Reasoning): Dynamically isolates model reasoning
    steps (<thought> blocks) into a dedicated, collapsed-by-default panel
    labeled ▶ Thinking Process to save screen space.
  - Automatic 2-Day History Purge: Saves conversations locally in a lightweight
    SQLite database and automatically deletes records older than 48 hours on
    startup to prevent database bloat.
  - Context-Bounded Memory: Maintains conversational coherence in follow-up
    chats by automatically sending only the last 5 messages in active threads to
    optimize token usage.
  - Wayland-Aware Absolute Draggability: Operates as a borderless window that
    can be dragged anywhere on your screen. It remembers its coordinate layout
    and auto-hides itself to your custom position.
  - Adjustable Inactivity Timer: Monitor actions over the window; if no activity
    is detected for the configured duration (e.g., 20 seconds), StickyMan slides
    down and hides automatically.
  - Dynamic Config Panel: Switch models, update your masked API key, adjust
    inactivity timeouts, and customize your system prompt directly from the
    settings interface.

🛠️ Installation & Setup (Linux)

1. Prerequisites

Ensure your Linux distribution has the required system clipboard tools
installed:

  - Ubuntu / Debian / Pop!_OS:
    sudo apt install xclip wl-clipboard
  - Arch Linux:
    sudo pacman -S xclip wl-clipboard
  - Fedora:
    sudo dnf install xclip wl-clipboard

2. Project Directory Setup

Run the following commands to initialize your environment using the fast uv
package manager:

# Navigate to the project directory
cd /home/savio/Desktop/Aonz.AI/linux-ai-plugin

# Initialize virtual environment
uv venv

# Activate virtual environment
source .venv/bin/activate

# Install required python packages
uv pip install openai pyqt6 python-dotenv

3. Placing Assets & Configurations

1.  Ensure your logo.png image file is saved inside the
    /home/savio/Desktop/Aonz.AI/linux-ai-plugin/ directory.
2.  Create a .env file in the same directory and paste your API key:
    OPENROUTER_API_KEY=your_openrouter_api_key_here

⌨️ Configuring Linux Global Shortcuts

To invoke StickyMan from anywhere in your operating system, open your desktop
settings (Settings -> Keyboard -> Custom Shortcuts) and map these exact absolute
paths:

| Shortcut Name      | Key Binding      | Command                                                                                                                        | Description                                                                                               |
| :----------------- | :--------------: | :----------------------------------------------------------------------------------------------------------------------------- | :-------------------------------------------------------------------------------------------------------- |
| **StickyMan Text** | `Ctrl + Alt + A` | `/home/savio/Desktop/Aonz.AI/linux-ai-plugin/.venv/bin/python /home/savio/Desktop/Aonz.AI/linux-ai-plugin/main.py --mode text` | Grabs highlighted text from your cursor and opens StickyMan with an answer.                               |
| **StickyMan Open** | `Ctrl + Alt + O` | `/home/savio/Desktop/Aonz.AI/linux-ai-plugin/.venv/bin/python /home/savio/Desktop/Aonz.AI/linux-ai-plugin/main.py --mode open` | Acts as a toggle. If the window is open, it hides it. If closed, it slides up and loads your latest chat. |

🔧 Maintenance & Troubleshooting

Resetting the Database

If you modify the default settings, update column schemas, or want to wipe your
local conversation logs, delete your local database file:

rm /home/savio/Desktop/Aonz.AI/linux-ai-plugin/history.db

Cleaning Up Hung Background Processes

If StickyMan ever becomes unresponsive to keyboard shortcuts, run this command
to force-close any orphaned backend listener threads:

pkill -f main.py
